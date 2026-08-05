#!/bin/bash
# workorder-gate.sh — UserPromptSubmit hook: score the prompt on the creativity
# gate and, when it trips, inject the decomposition directive before the agent
# answers.
#
# This is the mechanical half of the work-order pipeline. The contractual half
# (make_brief.py embedding ids and a return schema) only helps once a work order
# exists; something has to notice that a prompt DESERVES one. Measured over two
# months, the instruction-following equivalent — "announce what you deployed" —
# was honoured on 21.7% of subagent tasks, so this does not rely on the agent
# remembering.
#
# Behaviour on each prompt:
#   score < threshold   -> SILENT. Conversational turns are never touched, and
#                          silence is the correct output, not a reminder that
#                          the gate exists.
#   score >= threshold  -> emit hookSpecificOutput.additionalContext naming the
#                          score and the three-step decomposition path.
#
# Re-arm: at most one nudge per WORKORDER_GATE_REARM_MINUTES (default 60) per
# session, so a long creative session is prompted once rather than on every
# turn, and a genuinely new task later in the same session still gets caught.
#
# Slash commands (a prompt starting with "/") are skipped outright — those are
# harness commands, not task descriptions.
#
# ADDITIVE-ONLY: always exits 0, never blocks a prompt, and degrades to silence
# on any failure (missing python3, missing plan_task.py, malformed hook JSON).
# Kill switch: WORKORDER_GATE_DISABLE=1. All thresholds env-overridable.
set -u

_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="workorder-gate.sh" \
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

[ "${WORKORDER_GATE_DISABLE:-0}" = "1" ] && exit 0

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
METRICS_DIR="${METRICS_DIR:-$CLAUDE_DIR/metrics}"
TOOLS_DIR="${TOOLS_DIR:-$CLAUDE_DIR/tools}"
INPUT="$(cat 2>/dev/null || true)"

HOOK_JSON="$INPUT" \
TOOLS_DIR="$TOOLS_DIR" \
METRICS_DIR="$METRICS_DIR" \
WORKORDER_GATE_REARM_MINUTES="${WORKORDER_GATE_REARM_MINUTES:-60}" \
python3 <<'PY' || true
import json
import os
import sys
import time

sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))
try:
    import obs_emit
except Exception:
    obs_emit = None


def bail(action="silent", score=None):
    """Silence is a valid answer. The hook never blocks a prompt."""
    if obs_emit is not None:
        try:
            obs_emit.emit("gate.decision", session_id=session_id,
                           gate="workorder", action=action, score=score)
        except Exception:
            pass
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(0)


try:
    raw = os.environ.get("HOOK_JSON", "")
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}

prompt = (data.get("prompt") or "").strip()
session_id = data.get("session_id") or "unknown"

# Nothing to score, or a harness command rather than a task description.
if not prompt or prompt.startswith("/"):
    bail()

try:
    import plan_task
except Exception:
    bail()

try:
    score = plan_task.creative_score(prompt)
    threshold = plan_task.MIN_CREATIVE
except Exception:
    bail()

if score < threshold:
    bail()

# --- re-arm window ------------------------------------------------------------
try:
    rearm_min = int(os.environ.get("WORKORDER_GATE_REARM_MINUTES", "60"))
except Exception:
    rearm_min = 60

state_path = None
try:
    state_dir = os.path.join(os.environ.get("METRICS_DIR", ""), "state", "workorder-gate")
    os.makedirs(state_dir, exist_ok=True)
    safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_")[:80] or "unknown"
    state_path = os.path.join(state_dir, "%s.json" % safe)
    if os.path.isfile(state_path):
        with open(state_path) as fh:
            last = float(json.load(fh).get("last_nudge") or 0)
        if rearm_min > 0 and (time.time() - last) < rearm_min * 60:
            bail()
except Exception:
    state_path = None  # cannot track -> nudge anyway, never suppress silently

directive = (
    "WORK-ORDER GATE: this prompt scores %d on the creativity gate "
    "(threshold %d), so it is a task with parts, not a question.\n"
    "Do not start implementing it. Decompose it first:\n"
    "  1. Skill(superpowers:brainstorming) — settle the design with the user\n"
    "  2. Skill(superpowers:writing-plans) — produce the task breakdown\n"
    "  3. python3 ~/.claude/tools/plan_task.py --from-plan <plan-doc> "
    "--task \"<the request>\"\n"
    "Then, per part: make_brief.py <plan-id> <part-id> to dispatch, "
    "plan_task.py --log to record each return, and assess_task.py at the end.\n"
    "If this prompt genuinely is a question or a one-line fix, say so in one "
    "sentence and carry on — the gate is keyword arithmetic and can misjudge."
    % (score, threshold)
)

try:
    if state_path:
        tmp = state_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"last_nudge": time.time(), "score": score}, fh)
        os.replace(tmp, state_path)
except Exception:
    pass

sys.stdout.write(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": directive,
    }
}))
bail(action="inject", score=score)
PY

exit 0
