#!/bin/bash
# PreCompact hook — records one compaction event, and escalates to TOKEN MINIMIZER
# EXTREME when a session compacts repeatedly.
#
# Two jobs, both additive and both fail-open:
#   1. Append one compaction record to the current month shard (unchanged).
#   2. Count compactions per session; on the Nth (threshold, default 2), emit a
#      hook JSON object on stdout — systemMessage (shown to the user) plus
#      hookSpecificOutput.additionalContext (nudges the agent) — proposing the
#      opt-in TOKEN MINIMIZER EXTREME rule set. It NEVER activates the rule set
#      itself; the agent must ask the user for approval (see the token-efficiency
#      skill). It prompts exactly once per session.
#
# The hook ALWAYS exits 0 and never blocks compaction. Below threshold it writes
# nothing to stdout. Override the trigger with TOKEN_MINIMIZER_THRESHOLD.
# The hook JSON arrives on stdin (session_id, hook_event_name); parsed defensively.
set -u

_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="precompact-event.sh" \
    python3 -c '
import os, sys
sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))
try:
    import obs_emit
    obs_emit.emit("hook.error", hook=os.environ.get("HOOK_NAME"), stage="trap")
except Exception:
    pass
' >/dev/null 2>&1 || true
}
trap _obs_hook_error ERR

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
METRICS_DIR="${METRICS_DIR:-$CLAUDE_DIR/metrics}"
INPUT="$(cat 2>/dev/null || true)"

HOOK_JSON="$INPUT" METRICS_DIR="$METRICS_DIR" python3 <<'PY' || true
import datetime
import json
import os
import re
import sys

raw = os.environ.get("HOOK_JSON", "")
try:
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}

session_id = data.get("session_id")
now = datetime.datetime.now(datetime.timezone.utc)
metrics_dir = os.environ.get("METRICS_DIR")

# --- job 1: append the compaction record (unchanged) --------------------------
record = {
    "schema": 1,
    "kind": "compaction",
    "session_id": session_id,
    "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
}
try:
    os.makedirs(metrics_dir, exist_ok=True)
    shard = os.path.join(metrics_dir, now.strftime("%Y-%m") + ".jsonl")
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    # One os.write(2) of the whole line to an O_APPEND fd. A single write to an
    # O_APPEND regular file on a local filesystem does not interleave with other
    # single-write appenders, so concurrent hooks never tear a record. (PIPE_BUF
    # governs atomic writes to pipes, not this property of regular files.)
    fd = os.open(shard, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
except Exception as exc:
    sys.stderr.write("precompact-event: %s\n" % exc)

# --- job 2: TOKEN MINIMIZER EXTREME escalation (prompt once at threshold) ------
# We need a durable per-session counter because the agent's own memory resets on
# every compaction — it cannot count its own compactions. A tiny state file does.
try:
    if session_id:
        try:
            threshold = int(os.environ.get("TOKEN_MINIMIZER_THRESHOLD", "2"))
        except Exception:
            threshold = 2
        if threshold < 1:
            threshold = 2
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id))[:128]
        state_dir = os.path.join(metrics_dir, "state", "tmx")
        os.makedirs(state_dir, exist_ok=True)
        counter = os.path.join(state_dir, safe + ".count")
        try:
            with open(counter) as fh:
                n = int((fh.read() or "0").strip() or "0")
        except Exception:
            n = 0
        n += 1
        try:
            with open(counter, "w") as fh:
                fh.write(str(n))
        except Exception:
            pass
        # Prompt exactly once, when the count first reaches the threshold.
        if n == threshold:
            msg = (
                "TOKEN MINIMIZER EXTREME — this session has compacted %d times "
                "(repeated context exhaustion). An opt-in hard-clamp rule set for "
                "exactly this situation lives in the token-efficiency skill. To turn "
                "it on for the rest of THIS session, approve when the agent asks (or "
                "say \"enable token minimizer extreme\"). It never activates without "
                "your approval, and it resets to normal in a fresh session." % n
            )
            ctx = (
                "SIGNAL: this session has compacted %d times (threshold %d) — it "
                "keeps running out of context. Per the token-efficiency skill, STOP and "
                "propose the TOKEN MINIMIZER EXTREME rule set to the user for approval "
                "via AskUserQuestion (a single yes/no), showing its five hard rules. "
                "Apply those rules for the rest of THIS session ONLY if the user "
                "approves; never enable them silently, and do not carry them into a new "
                "session." % (n, threshold)
            )
            out = {
                "systemMessage": msg,
                "hookSpecificOutput": {
                    "hookEventName": "PreCompact",
                    "additionalContext": ctx,
                },
            }
            sys.stdout.write(json.dumps(out))
except Exception as exc:
    sys.stderr.write("precompact-event(tmx): %s\n" % exc)

# os._exit does not flush Python's buffered stdout — flush the escalation JSON first.
try:
    sys.stdout.flush()
except Exception:
    pass
os._exit(0)
PY

exit 0
