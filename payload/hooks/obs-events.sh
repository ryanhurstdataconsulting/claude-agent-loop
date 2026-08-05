#!/bin/bash
# obs-events.sh — PreToolUse/PostToolUse/Stop hook: emits obs.v1 tool.pre,
# tool.post, and turn.stop records via obs_emit.py. Same shape as
# harvest-metrics.sh: bash wrapper -> python heredoc, 10s SIGALRM guard,
# always exits 0. Kill switch: OBS_EVENTS_DISABLE=1.
#
# tool.pre/tool.post pairing: prefers tool_use_id (confirmed present on both
# PreToolUse and PostToolUse payloads). Falls back to a per-session
# (tool_name, sequence) counter, stored in
# $CLAUDE_DIR/metrics/state/obs-events/<session>.json, when tool_use_id is
# ever absent.
set -u

[ "${OBS_EVENTS_DISABLE:-0}" = "1" ] && exit 0

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
TOOLS_DIR="${TOOLS_DIR:-$CLAUDE_DIR/tools}"
INPUT="$(cat 2>/dev/null || true)"

HOOK_JSON="$INPUT" CLAUDE_DIR="$CLAUDE_DIR" TOOLS_DIR="$TOOLS_DIR" \
  python3 >/dev/null <<'PY' || true
import datetime
import hashlib
import json
import os
import signal
import sys


def _bail(signum, frame):
    os._exit(0)


try:
    signal.signal(signal.SIGALRM, _bail)
    signal.alarm(10)
except Exception:
    pass

sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))

try:
    raw = os.environ.get("HOOK_JSON", "")
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}

try:
    import obs_emit
except Exception:
    os._exit(0)

event_name = data.get("hook_event_name") or ""
session_id = data.get("session_id") or "unknown"
tool_name = data.get("tool_name") or ""
_tool_input = data.get("tool_input")
tool_input = _tool_input if isinstance(_tool_input, dict) else {}
tool_use_id = data.get("tool_use_id")


def _args_hash(obj):
    try:
        blob = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    except Exception:
        blob = str(obj)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _safe(sid):
    return "".join(c for c in str(sid) if c.isalnum() or c in "-_")[:80] or "unknown"


def _state_path():
    state_dir = os.path.join(
        os.environ.get("CLAUDE_DIR", ""), "metrics", "state", "obs-events")
    try:
        os.makedirs(state_dir, exist_ok=True)
    except Exception:
        return None
    return os.path.join(state_dir, "%s.json" % _safe(session_id))


def _load_state(path):
    default = {"seq": {}, "pending": {}}
    if not path:
        return default
    try:
        with open(path) as fh:
            st = json.load(fh)
        if not isinstance(st, dict):
            return default
        st.setdefault("seq", {})
        st.setdefault("pending", {})
        return st
    except Exception:
        return default


def _save_state(path, state):
    if not path:
        return
    try:
        tmp = path + ".tmp.%d" % os.getpid()
        with open(tmp, "w") as fh:
            json.dump(state, fh)
        os.replace(tmp, path)
    except Exception:
        pass


try:
    if event_name == "PreToolUse":
        state_path = _state_path()
        state = _load_state(state_path)
        if tool_use_id:
            pairing_key = str(tool_use_id)
        else:
            seq = int(state["seq"].get(tool_name, 0)) + 1
            state["seq"][tool_name] = seq
            pairing_key = "%s:%s:%d" % (session_id, tool_name, seq)
        state["pending"][pairing_key] = datetime.datetime.now(
            datetime.timezone.utc).isoformat()
        _save_state(state_path, state)
        obs_emit.emit(
            "tool.pre", session_id=session_id, component_key=pairing_key,
            tool_name=tool_name, args_hash=_args_hash(tool_input),
        )
    elif event_name == "PostToolUse":
        state_path = _state_path()
        state = _load_state(state_path)
        if tool_use_id:
            pairing_key = str(tool_use_id)
        else:
            seq = int(state["seq"].get(tool_name, 0))
            pairing_key = "%s:%s:%d" % (session_id, tool_name, seq)
        pre_ts = state["pending"].pop(pairing_key, None)
        _save_state(state_path, state)
        duration_ms = None
        if pre_ts:
            try:
                started = datetime.datetime.fromisoformat(pre_ts)
                now = datetime.datetime.now(datetime.timezone.utc)
                duration_ms = int((now - started).total_seconds() * 1000)
            except Exception:
                duration_ms = None
        _tool_response = data.get("tool_response")
        tool_response = _tool_response if isinstance(_tool_response, dict) else {}
        ok = not bool(tool_response.get("isError"))
        error_class = None if ok else tool_response.get("error")
        obs_emit.emit(
            "tool.post", session_id=session_id, component_key=pairing_key,
            tool_name=tool_name, tool_use_id=tool_use_id, ok=ok,
            error_class=error_class, duration_ms=duration_ms,
            args_hash=_args_hash(tool_input),
        )
    elif event_name == "Stop":
        obs_emit.emit("turn.stop", session_id=session_id)
except Exception:
    pass

os._exit(0)
PY

exit 0
