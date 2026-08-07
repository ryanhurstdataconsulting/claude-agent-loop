#!/bin/bash
# loop-close.sh — SessionEnd hook: close the loop without anyone watching.
#
# This is the half of the loop that must never require a human. It runs after
# the session ends and does, unattended, everything that was previously somebody
# noticing a file had appeared:
#
# Step 1 runs `loop_close.py --all`. That links each part to its subagent
# transcript, assesses it objectively, emits one kind:"task" record per part
# tagged resources_source "workorder", and stamps the work order closed.
#
# Step 2 runs `heuristics_eval.py`, which evaluates the rulebook over the
# metrics store now that it holds that precise evidence.
#
# It does NOT act on what fires. Acting means patching a resource and committing
# it through loop_autocommit.sh, and an unattended hook is the wrong place to
# decide that — a bad auto-patch at 2am is worse than a late one. Instead it
# writes the firing to
#   $METRICS_DIR/state/loop-close/<session>.json
# and the SessionStart nudge surfaces it next time, where a human is present.
#
# ADDITIVE-ONLY: always exits 0, never blocks session teardown, and swallows
# every failure. A ~25s wall-clock guard bounds the work.
# Kill switch: LOOP_CLOSE_DISABLE=1.
set -u

_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="loop-close.sh" \
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

[ "${LOOP_CLOSE_DISABLE:-0}" = "1" ] && exit 0

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
TOOLS_DIR="${TOOLS_DIR:-$CLAUDE_DIR/tools}"
METRICS_DIR="${METRICS_DIR:-$CLAUDE_DIR/metrics}"
PROJECTS_DIR="${PROJECTS_DIR:-$CLAUDE_DIR/projects}"
BASE_DIR="${BASE_DIR:-$CLAUDE_DIR/plans}"
INPUT="$(cat 2>/dev/null || true)"

HOOK_JSON="$INPUT" \
TOOLS_DIR="$TOOLS_DIR" \
METRICS_DIR="$METRICS_DIR" \
PROJECTS_DIR="$PROJECTS_DIR" \
BASE_DIR="$BASE_DIR" \
python3 >/dev/null 2>&1 <<'PY' || true
import json
import os
import signal
import sys

sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))


def _bail(signum, frame):
    os._exit(0)


try:
    signal.signal(signal.SIGALRM, _bail)
    signal.alarm(25)
except Exception:
    pass

try:
    data = json.loads(os.environ.get("HOOK_JSON", "") or "{}")
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}
session_id = data.get("session_id") or "unknown"

metrics = os.environ.get("METRICS_DIR", "")
base = os.environ.get("BASE_DIR", "")
projects = os.environ.get("PROJECTS_DIR", "")

# --- 1. close every ready plan ------------------------------------------------
summaries = []
try:
    import loop_close
    for wo in loop_close.ready_plans(base):
        try:
            s = loop_close.close_one(wo, metrics, projects)
            import plan_task
            plan_task.save(base, wo)
            summaries.append({k: v for k, v in s.items() if k != "records"})
        except Exception:
            continue
except Exception:
    pass

# Nothing closed means nothing new to learn from. Stop rather than re-evaluate
# the same history on every session teardown.
if not summaries:
    os._exit(0)

# --- 2. evaluate the rulebook over the evidence just written -----------------
# Run the engine as a subprocess against its documented CLI rather than reaching
# into its internals, so a refactor there cannot silently break this hook.
firings = None
try:
    import subprocess
    proc = subprocess.run(
        [sys.executable, os.path.join(os.environ.get("TOOLS_DIR", ""),
                                      "heuristics_eval.py"),
         "--task-id", "session-%s" % session_id,
         "--session-id", str(session_id),
         "--metrics-dir", metrics, "--json"],
        capture_output=True, text=True, timeout=15)
    if proc.returncode == 0 and proc.stdout.strip():
        try:
            firings = json.loads(proc.stdout)
        except Exception:
            firings = proc.stdout.strip()[:4000]
except Exception:
    firings = None

# --- 3. leave the result where SessionStart will surface it -------------------
try:
    out_dir = os.path.join(metrics, "state", "loop-close")
    os.makedirs(out_dir, exist_ok=True)
    safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_")[:80] or "unknown"
    path = os.path.join(out_dir, "%s.json" % safe)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump({"session_id": session_id, "closed": summaries,
                   "firings": firings}, fh, sort_keys=True)
    os.replace(tmp, path)
except Exception:
    pass

os._exit(0)
PY

exit 0
