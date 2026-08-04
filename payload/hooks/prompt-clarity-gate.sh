#!/bin/bash
# prompt-clarity-gate.sh — UserPromptSubmit hook. Cheap heuristic pre-filter
# (word/paragraph count, or an explicit clean:/raw: override) decides whether
# to bother; when triggered, a single Haiku API call classifies the prompt as
# clarify / normalize / none and this script acts on that classification.
#
# Behaviour:
#   heuristic says "fine as-is", no override -> SILENT, no API call at all.
#   flagged (or "clean:" override)           -> one Haiku call:
#     mode=clarify   -> {"decision":"block","reason":"<question>"}
#     mode=normalize -> hookSpecificOutput.additionalContext = "<structured spec>"
#     mode=none      -> SILENT (false positive, no action)
#   "raw:" override -> SILENT unconditionally, heuristic never runs.
#
# ADDITIVE-ONLY / FAIL-OPEN: always exits 0. Any failure (missing API key,
# network, malformed JSON, missing jq/python3, missing curl) degrades to
# silence — never blocks a real prompt over infrastructure trouble.
# Kill switch: PROMPT_CLARITY_GATE_DISABLE=1.
set -u

[ "${PROMPT_CLARITY_GATE_DISABLE:-0}" = "1" ] && exit 0

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
SECRETS_ENV="${SECRETS_ENV:-$CLAUDE_DIR/secrets.env}"
STATE_DIR="${STATE_DIR:-$CLAUDE_DIR/metrics/state/prompt-clarity-gate}"

# Defensible defaults, not empirically sampled (no raw prompt text exists in
# this environment's metrics — confirmed 0 records had one). Env-overridable,
# same convention as workorder-gate.sh's WORKORDER_GATE_REARM_MINUTES.
MIN_WORDS="${PROMPT_CLARITY_GATE_MIN_WORDS:-120}"
MIN_PARAGRAPHS="${PROMPT_CLARITY_GATE_MIN_PARAGRAPHS:-4}"
BLOCK_STREAK_LIMIT="${PROMPT_CLARITY_GATE_BLOCK_STREAK_LIMIT:-2}"
BLOCK_STREAK_WINDOW_MIN="${PROMPT_CLARITY_GATE_BLOCK_STREAK_WINDOW_MIN:-10}"

INPUT="$(cat 2>/dev/null || true)"

HOOK_JSON="$INPUT" \
SECRETS_ENV="$SECRETS_ENV" \
STATE_DIR="$STATE_DIR" \
MIN_WORDS="$MIN_WORDS" \
MIN_PARAGRAPHS="$MIN_PARAGRAPHS" \
BLOCK_STREAK_LIMIT="$BLOCK_STREAK_LIMIT" \
BLOCK_STREAK_WINDOW_MIN="$BLOCK_STREAK_WINDOW_MIN" \
python3 <<'PY' || true
import json
import os
import sys

def bail():
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(0)

def emit_block(reason):
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    bail()

def emit_context(text):
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": text,
        }
    }))
    bail()

try:
    raw = os.environ.get("HOOK_JSON", "")
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}

prompt = (data.get("prompt") or "").strip()
session_id = data.get("session_id") or "unknown"

if not prompt or prompt.startswith("/"):
    bail()

force_on = False
force_off = False
if prompt.startswith("raw:"):
    force_off = True
    prompt_for_model = prompt[len("raw:"):].strip()
elif prompt.startswith("clean:"):
    force_on = True
    prompt_for_model = prompt[len("clean:"):].strip()
else:
    prompt_for_model = prompt

if force_off:
    bail()

words = len(prompt_for_model.split())
paragraphs = prompt_for_model.count("\n\n") + 1
min_words = int(os.environ.get("MIN_WORDS", "120"))
min_paragraphs = int(os.environ.get("MIN_PARAGRAPHS", "4"))

heuristic_flagged = words >= min_words or paragraphs >= min_paragraphs

if not (heuristic_flagged or force_on):
    bail()

def load_api_key():
    path = os.environ.get("SECRETS_ENV", "")
    if not path or not os.path.isfile(path):
        return None
    for line in open(path):
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
    return None

def call_model(prompt_text):
    import subprocess
    api_key = load_api_key()
    if not api_key or api_key == "x":
        return None
    schema = {
        "type": "object",
        "properties": {
            "needs_action": {"type": "boolean"},
            "mode": {"type": "string", "enum": ["clarify", "normalize", "none"]},
            "output": {"type": "string"},
        },
        "required": ["needs_action", "mode", "output"],
        "additionalProperties": False,
    }
    body = {
        "model": "claude-haiku-4-5",
        "max_tokens": 1024,
        "system": (
            "You classify a user's prompt to a coding agent for a preprocessing "
            "hook. mode=clarify when the request is genuinely ambiguous and a "
            "targeted question is needed before proceeding; output is that "
            "question. mode=normalize when the request is long or noisy but the "
            "intent is clear; output is a structured breakdown (Goals / "
            "Constraints / Steps / Priorities). mode=none when the prompt needs "
            "no help; output is an empty string. Never do cosmetic grammar-only "
            "correction — only disambiguate or structure."
        ),
        "messages": [{"role": "user", "content": prompt_text}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }
    try:
        proc = subprocess.run(
            [
                "curl", "-sS", "--max-time", "20",
                "https://api.anthropic.com/v1/messages",
                "-H", "x-api-key: %s" % api_key,
                "-H", "anthropic-version: 2023-06-01",
                "-H", "content-type: application/json",
                "-d", json.dumps(body),
            ],
            capture_output=True, text=True, timeout=25,
        )
        if proc.returncode != 0:
            return None
        resp = json.loads(proc.stdout)
        if resp.get("stop_reason") not in ("end_turn", "stop_sequence"):
            return None
        payload_text = resp["content"][0]["text"]
        payload = json.loads(payload_text)
        if not isinstance(payload, dict):
            return None
        if payload.get("mode") not in ("clarify", "normalize", "none"):
            return None
        return payload
    except Exception:
        return None

def _state_path(session_id):
    state_dir = os.environ.get("STATE_DIR", "")
    if not state_dir:
        return None
    try:
        os.makedirs(state_dir, exist_ok=True)
        safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_")[:80] or "unknown"
        return os.path.join(state_dir, "%s.json" % safe)
    except Exception:
        return None

def block_streak_exceeded(session_id):
    import time
    path = _state_path(session_id)
    if not path or not os.path.isfile(path):
        return False
    try:
        with open(path) as fh:
            st = json.load(fh)
        window_min = int(os.environ.get("BLOCK_STREAK_WINDOW_MIN", "10"))
        limit = int(os.environ.get("BLOCK_STREAK_LIMIT", "2"))
        if (time.time() - float(st.get("last_block", 0))) > window_min * 60:
            return False
        return int(st.get("streak", 0)) >= limit
    except Exception:
        return False

def record_block(session_id):
    import time
    path = _state_path(session_id)
    if not path:
        return
    try:
        streak = 1
        if os.path.isfile(path):
            with open(path) as fh:
                prev = json.load(fh)
            window_min = int(os.environ.get("BLOCK_STREAK_WINDOW_MIN", "10"))
            if (time.time() - float(prev.get("last_block", 0))) <= window_min * 60:
                streak = int(prev.get("streak", 0)) + 1
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"last_block": time.time(), "streak": streak}, fh)
        os.replace(tmp, path)
    except Exception:
        pass

def clear_block_streak(session_id):
    path = _state_path(session_id)
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except Exception:
            pass

result = call_model(prompt_for_model)
if result is None:
    bail()

mode = result.get("mode")
output = result.get("output") or ""

if mode == "none" or not result.get("needs_action"):
    clear_block_streak(session_id)
    bail()

if mode == "clarify":
    if block_streak_exceeded(session_id):
        bail()
    record_block(session_id)
    emit_block(output)

if mode == "normalize":
    clear_block_streak(session_id)
    prefix = "prompt-clarity-gate restructured this prompt"
    if force_on:
        prefix += " (explicit clean: override)"
    emit_context("%s:\n\n%s" % (prefix, output))

bail()
PY

exit 0
