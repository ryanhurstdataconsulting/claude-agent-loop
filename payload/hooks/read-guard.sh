#!/bin/bash
# read-guard.sh — PreToolUse hook on the Read tool. A mechanical backstop for
# the machine-global "Autocompact Anti-Thrash" discipline. It inspects every
# Read call before it executes and:
#   - HARD-BLOCKS (deny) whole-file reads of file classes that should never
#     enter the context window whole: lockfiles, minified/bundled assets,
#     source maps, node_modules/dist/build/.vite/coverage paths, JSONL
#     transcripts, .log files, and CSV/Parquet data files.
#   - SOFT-NUDGES (allow + additionalContext) a large file (over 1,000 lines
#     OR 100 KB) read without offset/limit, prompting a narrow re-read or a
#     subagent hand-off.
#   - FAILS OPEN (allow) on every ambiguous or error case.
#
# The hook ALWAYS exits 0 and signals ONLY through the hookSpecificOutput JSON
# on stdout (permissionDecision "allow"/"deny"); it NEVER exits 2 and never
# emits "ask"/"defer". JSON parsing happens in Python inside a try/except that
# defaults to {} on any failure, mirroring precompact-event.sh. No set -e.
# macOS bash-3.2 portable: the bash layer is trivial (cat + exit 0), so it uses
# no declare -A, no mapfile, and no GNU-only flags; all classification and
# sizing run in Python, which is bash-version-independent.
set -u

_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="read-guard.sh" \
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
TOOLS_DIR="${TOOLS_DIR:-$CLAUDE_DIR/tools}"
INPUT="$(cat 2>/dev/null || true)"

READ_GUARD_INPUT="$INPUT" TOOLS_DIR="$TOOLS_DIR" python3 <<'PY' || true
import json
import os
import sys

# --- defensive parse: any failure -> {} (mirrors precompact-event.sh) ---------
raw = os.environ.get("READ_GUARD_INPUT", "")
try:
    payload = json.loads(raw) if raw.strip() else {}
    if not isinstance(payload, dict):
        payload = {}
except Exception:
    payload = {}

session_id = payload.get("session_id") or "unknown"
sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))
try:
    import obs_emit
except Exception:
    obs_emit = None

LINE_CAP = 1000
BYTE_CAP = 100 * 1024  # 100 KB

HARD_LOCKFILES = ("package-lock.json", "poetry.lock", "Cargo.lock")
HARD_SEGMENTS = ("node_modules", "dist", "build", ".vite", "coverage")


def hard_block_label(file_path):
    """Return a noun-phrase label if file_path is a hard-blocked class, else None."""
    base = os.path.basename(file_path)
    lower = base.lower()
    if base in HARD_LOCKFILES:
        return "a lockfile"
    if lower.endswith(".min.js") or lower.endswith(".min.css") or ".bundle." in lower:
        return "a minified or bundled asset"
    if lower.endswith(".map"):
        return "a source map"
    if lower.endswith(".jsonl"):
        return "a JSONL session transcript"
    if lower.endswith(".log"):
        return "a log file"
    if lower.endswith(".csv") or lower.endswith(".parquet"):
        return "a data file (CSV or Parquet)"
    for seg in file_path.replace("\\", "/").split("/"):
        if seg in HARD_SEGMENTS:
            return "inside a %s/ directory" % seg
    return None


def is_large(file_path):
    """True if the file is over the byte OR line cap. Any stat/read failure -> False."""
    try:
        if os.path.getsize(file_path) > BYTE_CAP:
            return True
    except Exception:
        return False
    try:
        lines = 0
        with open(file_path, "rb") as fh:
            for _ in fh:
                lines += 1
                if lines > LINE_CAP:
                    return True
    except Exception:
        return False
    return lines > LINE_CAP


def allow(context=None):
    if obs_emit is not None:
        try:
            obs_emit.emit("gate.decision", session_id=session_id,
                           gate="read-guard", action="inject" if context else "silent")
        except Exception:
            pass
    hook = {"hookEventName": "PreToolUse", "permissionDecision": "allow"}
    if context:
        hook["additionalContext"] = context
    return {"hookSpecificOutput": hook}


def deny(reason):
    if obs_emit is not None:
        try:
            obs_emit.emit("gate.decision", session_id=session_id,
                           gate="read-guard", action="deny")
        except Exception:
            pass
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


# --- decision logic: any exception -> plain allow (fail open) ------------------
result = None
try:
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        result = allow()
    else:
        label = hard_block_label(file_path)
        if label:
            result = deny(
                "Blocked whole-file Read of %s: it is %s; reading such a file "
                "whole floods the context window. Pull a targeted span with "
                "offset/limit, grep it, or delegate the sweep to a subagent."
                % (file_path, label)
            )
        elif (
            "offset" not in tool_input
            and "limit" not in tool_input
            and is_large(file_path)
        ):
            result = allow(
                "read-guard: %s is large (over 1,000 lines or 100 KB) and you "
                "requested it without offset/limit. Re-issue the Read with "
                "offset/limit to pull only the span you need, or delegate the "
                "sweep to a subagent that returns the conclusion." % file_path
            )
        else:
            result = allow()
except Exception:
    result = allow()

if result is None:
    result = allow()

sys.stdout.write(json.dumps(result))
# os._exit does not flush Python's buffered stdout — flush the decision first.
try:
    sys.stdout.flush()
except Exception:
    pass
os._exit(0)
PY

exit 0
