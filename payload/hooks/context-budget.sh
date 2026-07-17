#!/bin/bash
# context-budget.sh — PostToolUse hook: watch the session's context-window
# occupancy and force a durable pause point before auto-compaction.
#
# After every tool call, reads the newest main-loop assistant usage record from
# the session transcript (256 KB tail) and compares occupancy
# (input_tokens + cache_read_input_tokens + cache_creation_input_tokens)
# against CONTEXT_BUDGET_TOKENS (default 150000):
#   - at CONTEXT_BUDGET_WARN_PCT (70%): one warning per cycle — steer the agent
#     toward a safe pause point;
#   - at CONTEXT_BUDGET_CRIT_PCT (85%): a checkpoint directive that repeats on
#     EVERY tool call until a resume brief exists at
#     $METRICS_DIR/state/budget/checkpoints/<session>.md with
#     mtime >= int(crit_since).
# Dropping back below the warn threshold (e.g. after a compaction) re-arms both
# tiers. Fail-open: any internal failure degrades to silence, and the hook
# always exits 0. Kill switch: CONTEXT_BUDGET_DISABLE=1.
set -u

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
METRICS_DIR="${METRICS_DIR:-$CLAUDE_DIR/metrics}"

if [ "${CONTEXT_BUDGET_DISABLE:-0}" = "1" ]; then
  exit 0
fi

INPUT="$(cat 2>/dev/null || true)"

HOOK_JSON="$INPUT" METRICS_DIR="$METRICS_DIR" python3 <<'PY' || true
import json
import os
import re
import sys
import tempfile
import time


def bail():
    """Flush stdout and exit 0 — the hook never blocks a tool call."""
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(0)


try:
    raw = os.environ.get("HOOK_JSON", "")
    try:
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

    session_id = data.get("session_id")
    transcript_path = data.get("transcript_path")
    if not session_id or not transcript_path:
        bail()

    metrics_dir = os.environ.get("METRICS_DIR", "")

    def int_env(name, default):
        try:
            return int(os.environ.get(name, ""))
        except Exception:
            return default

    budget = int_env("CONTEXT_BUDGET_TOKENS", 150000)
    if budget < 1000:
        budget = 150000
    warn_pct = int_env("CONTEXT_BUDGET_WARN_PCT", 70)
    crit_pct = int_env("CONTEXT_BUDGET_CRIT_PCT", 85)
    if warn_pct >= crit_pct:
        warn_pct, crit_pct = 70, 85
    check_secs = int_env("CONTEXT_BUDGET_CHECK_SECS", 30)
    if check_secs < 0:
        check_secs = 30

    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id))[:128]
    state_dir = os.path.join(metrics_dir, "state", "budget")
    ckpt_dir = os.path.join(state_dir, "checkpoints")
    os.makedirs(ckpt_dir, exist_ok=True)
    state_path = os.path.join(state_dir, safe + ".json")
    ckpt_path = os.path.join(ckpt_dir, safe + ".md")

    state = {"last_check_ts": 0.0, "warn_fired": False,
             "crit_since": None, "checkpoint_ack": False}
    try:
        with open(state_path) as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            if isinstance(loaded.get("last_check_ts"), (int, float)):
                state["last_check_ts"] = float(loaded["last_check_ts"])
            if isinstance(loaded.get("warn_fired"), bool):
                state["warn_fired"] = loaded["warn_fired"]
            if isinstance(loaded.get("crit_since"), (int, float)):
                state["crit_since"] = float(loaded["crit_since"])
            if isinstance(loaded.get("checkpoint_ack"), bool):
                state["checkpoint_ack"] = loaded["checkpoint_ack"]
    except Exception:
        pass

    def save_state():
        fd, tmp = tempfile.mkstemp(dir=state_dir, prefix=safe + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(state, fh)
            os.replace(tmp, state_path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except Exception:
                    pass

    def reset_state():
        state["last_check_ts"] = 0.0
        state["warn_fired"] = False
        state["crit_since"] = None
        state["checkpoint_ack"] = False

    def measure():
        """Newest main-loop assistant usage record in the transcript tail, or 0."""
        try:
            size = os.path.getsize(transcript_path)
            with open(transcript_path, "rb") as fh:
                offset = max(0, size - 262144)
                fh.seek(offset)
                text = fh.read().decode("utf-8", errors="replace")
        except Exception:
            return 0
        lines = text.split("\n")
        if offset > 0 and lines:
            lines = lines[1:]  # the first line after a mid-file seek is truncated
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if not isinstance(rec, dict) or rec.get("isSidechain") is True:
                continue
            if rec.get("type") != "assistant":
                continue
            message = rec.get("message")
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            return ((usage.get("input_tokens", 0) or 0)
                    + (usage.get("cache_read_input_tokens", 0) or 0)
                    + (usage.get("cache_creation_input_tokens", 0) or 0))
        return 0

    def emit(tier, occupancy):
        percent = occupancy * 100 // budget
        if tier == "warn":
            msg = ("Context budget: %d of %d tokens used (%d%%). "
                   "Steering toward a pause point." % (occupancy, budget, percent))
            ctx = ("Context-budget warning: this session's context window is at "
                   "%d%% of its %d-token budget (%d tokens). Begin steering "
                   "toward a safe pause point: finish the current step, commit "
                   "and push work in progress, and update your ledger and todos. "
                   "A critical reminder will fire at %d%% and will repeat until "
                   "you write a checkpoint file."
                   % (percent, budget, occupancy, crit_pct))
        else:
            msg = ("Context budget CRITICAL: %d of %d tokens used (%d%%). "
                   "Checkpoint required." % (occupancy, budget, percent))
            ctx = ("Context-budget CRITICAL: this session's context window is at "
                   "%d%% of its %d-token budget (%d tokens). Reach a safe pause "
                   "point now: (1) commit and push all work in progress; "
                   "(2) update your progress ledger and todos; (3) write a resume "
                   "brief to %s covering task state, branch names, next steps, "
                   "and key file paths. This reminder repeats on every tool call "
                   "until that file exists."
                   % (percent, budget, occupancy, ckpt_path))
        out = {
            "systemMessage": msg,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": ctx,
            },
        }
        sys.stdout.write(json.dumps(out))

    now = time.time()

    # Critical tier active and unacknowledged: verify the checkpoint, re-arm,
    # or repeat the directive. No throttle at this tier.
    if state["crit_since"] is not None and not state["checkpoint_ack"]:
        try:
            ck_mtime = os.path.getmtime(ckpt_path)
        except Exception:
            ck_mtime = None
        if ck_mtime is not None and ck_mtime >= int(state["crit_since"]):
            state["checkpoint_ack"] = True
            save_state()
            bail()
        occupancy = measure()
        if occupancy <= 0:
            bail()  # fail-open: no reading, no nag this call
        percent = occupancy * 100 // budget
        if percent < warn_pct:
            reset_state()  # compaction (or a new task) dropped occupancy: re-arm
            save_state()
            bail()
        emit("crit", occupancy)
        bail()

    # Normal path: throttled measurement.
    if now - state["last_check_ts"] < check_secs:
        bail()
    state["last_check_ts"] = now
    occupancy = measure()
    if occupancy <= 0:
        save_state()
        bail()
    percent = occupancy * 100 // budget
    if percent >= crit_pct:
        if state["crit_since"] is None:
            state["crit_since"] = now
            save_state()
            emit("crit", occupancy)
        else:
            # crit_since set with checkpoint_ack true: the acknowledgment
            # holds until occupancy drops below the warn threshold.
            save_state()
        bail()
    if percent >= warn_pct:
        if not state["warn_fired"]:
            state["warn_fired"] = True
            save_state()
            emit("warn", occupancy)
        else:
            save_state()
        bail()
    if state["warn_fired"] or state["crit_since"] is not None or state["checkpoint_ack"]:
        reset_state()
    save_state()
    bail()
except Exception:
    pass
os._exit(0)
PY

exit 0
