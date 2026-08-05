#!/bin/bash
# SubagentStop / SessionEnd hook — harvests objective task/session metrics.
#
# ADDITIVE-ONLY, exactly like inject-resource-loop.sh: this hook ALWAYS exits 0.
# A broken harvest must never break a session, so every failure is swallowed and
# logged to stderr only. The hook JSON arrives on stdin (session_id,
# transcript_path, hook_event_name); we parse it defensively in python and
# tolerate absent or malformed input.
#
# A ~10s wall-clock guard bounds the work (macOS has no timeout(1), so the guard
# is a python-side SIGALRM).
set -u

_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="harvest-metrics.sh" \
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
METRICS_DIR="${METRICS_DIR:-$CLAUDE_DIR/metrics}"
INPUT="$(cat 2>/dev/null || true)"

HOOK_JSON="$INPUT" TOOLS_DIR="$TOOLS_DIR" METRICS_DIR="$METRICS_DIR" \
  python3 >/dev/null <<'PY' || true
import glob
import json
import os
import signal
import sys

sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))


def log(msg):
    sys.stderr.write("harvest-metrics: %s\n" % msg)


# 10s wall-clock guard. macOS ships no timeout(1); SIGALRM bounds us instead.
def _bail(signum, frame):
    log("timed out (10s) — skipping")
    os._exit(0)


try:
    signal.signal(signal.SIGALRM, _bail)
    signal.alarm(10)
except Exception:
    pass

raw = os.environ.get("HOOK_JSON", "")
try:
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}

event = data.get("hook_event_name") or "SubagentStop"
event = "SessionEnd" if event == "SessionEnd" else "SubagentStop"
transcript = data.get("transcript_path") or ""
session_id = data.get("session_id") or None
metrics_dir = os.environ.get("METRICS_DIR")

if not transcript:
    log("no transcript_path in hook input — nothing to harvest")
    os._exit(0)

# Resolve the transcript to harvest. If SubagentStop points at a main session
# file (not an agent-*.jsonl), pick the newest agent-*.jsonl beside it; the
# cursor keeps already-harvested subagents from being re-emitted.
#
# NOTE (accepted, M4): under parallel subagents finishing near-simultaneously,
# "newest by mtime" can transiently mis-attribute one SubagentStop to the wrong
# agent file. This self-corrects at SessionEnd, where the cursor catch-up
# harvests every un-cursored subagent and the session-backfill re-attributes
# resources — so the terminal record set is correct regardless of the race.
resolved = transcript
base = os.path.basename(transcript)
if (not base.startswith("agent-")
        and event == "SubagentStop"
        and transcript.endswith(".jsonl")):
    subdir = os.path.join(transcript[:-len(".jsonl")], "subagents")
    cands = [p for p in glob.glob(os.path.join(subdir, "agent-*.jsonl"))
             if os.path.isfile(p)]
    cands.sort(key=lambda p: os.path.getmtime(p))
    if cands:
        resolved = cands[-1]

try:
    import harvest_metrics
    emitted = harvest_metrics.harvest(resolved, event, metrics_dir, session_id)
    log("emitted %d record(s) from %s"
        % (len(emitted), os.path.basename(resolved)))
except Exception as exc:
    log("error: %s" % exc)

os._exit(0)
PY

exit 0
