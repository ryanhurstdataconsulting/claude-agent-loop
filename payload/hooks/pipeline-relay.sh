#!/bin/bash
# pipeline-relay.sh — PostToolUse (matcher: Skill): keep the design chain from
# terminating early.
#
# The UserPromptSubmit gate (workorder-gate.sh) gets a creative prompt as far as
# brainstorming. Measured on real sessions, that is where the chain broke: a
# session ran brainstorming, wrote a design spec, and then began implementing
# from the spec alone — never reaching writing-plans, and so never reaching a
# work order. A spec is a design, not a decomposition.
#
# This hook fires when either superpowers skill is LAUNCHED and injects the next
# link:
#
#   brainstorming  -> "a spec is not the end; continue to writing-plans, then
#                      create the work order before implementing"
#   writing-plans  -> "when the plan doc exists, run plan_task.py --from-plan
#                      before implementing"
#
# NOTE ON TIMING: the Skill tool returns "Launching skill: <name>" immediately,
# so PostToolUse fires at skill ENTRY, not at completion. The wording reflects
# that — it plants the next step before the work rather than after it.
#
# Re-arm: at most one relay per (session, link) per PIPELINE_RELAY_REARM_MINUTES
# (default 60), so a session that re-enters a skill is not nagged, while a
# genuinely new task later in the same session still gets relayed.
#
# ADDITIVE-ONLY: always exits 0, never blocks a tool call, and degrades to
# silence on any failure. Every other skill passes in silence.
# Kill switch: PIPELINE_RELAY_DISABLE=1.
set -u

_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="pipeline-relay.sh" \
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

[ "${PIPELINE_RELAY_DISABLE:-0}" = "1" ] && exit 0

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
METRICS_DIR="${METRICS_DIR:-$CLAUDE_DIR/metrics}"
TOOLS_DIR="${TOOLS_DIR:-$CLAUDE_DIR/tools}"
INPUT="$(cat 2>/dev/null || true)"

HOOK_JSON="$INPUT" \
TOOLS_DIR="$TOOLS_DIR" \
METRICS_DIR="$METRICS_DIR" \
PIPELINE_RELAY_REARM_MINUTES="${PIPELINE_RELAY_REARM_MINUTES:-60}" \
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


def bail():
    """Silence is a valid answer. The hook never blocks a tool call."""
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

if data.get("tool_name") != "Skill":
    bail()

tool_input = data.get("tool_input")
if not isinstance(tool_input, dict):
    bail()

# Plugin skills arrive as "<plugin>:<skill>"; match on the skill half so the
# relay survives a plugin rename.
skill = str(tool_input.get("skill") or "").strip().lower()
leaf = skill.rsplit(":", 1)[-1]
session_id = data.get("session_id") or "unknown"

if obs_emit is not None:
    try:
        obs_emit.emit("skill.invoked", session_id=session_id, skill_name=leaf)
    except Exception:
        pass

RELAYS = {
    "brainstorming": (
        "PIPELINE RELAY: brainstorming settles the DESIGN. Its output is a spec, "
        "and a spec is not a decomposition — do not start implementing from it.\n"
        "The chain continues:\n"
        "  next  Skill(superpowers:writing-plans) — break the design into tasks\n"
        "  then  python3 ~/.claude/tools/plan_task.py --from-plan <plan-doc> "
        "--task \"<the request>\"\n"
        "The work order is what makes the work measurable. Without it, nothing "
        "downstream can attribute or assess this task."
    ),
    "writing-plans": (
        "PIPELINE RELAY: once this plan document is written, create the work "
        "order BEFORE implementing:\n"
        "  python3 ~/.claude/tools/plan_task.py --from-plan <plan-doc> "
        "--task \"<the request>\"\n"
        "Then per part: make_brief.py <plan-id> <part-id> to dispatch, "
        "plan_task.py --log <plan-id> --part <id> --json <file> to record each "
        "return, and assess_task.py <plan-id> --repo . at the end."
    ),
}

directive = RELAYS.get(leaf)
if not directive:
    bail()

# --- re-arm window ------------------------------------------------------------
try:
    rearm_min = int(os.environ.get("PIPELINE_RELAY_REARM_MINUTES", "60"))
except Exception:
    rearm_min = 60

state_path = None
try:
    state_dir = os.path.join(os.environ.get("METRICS_DIR", ""), "state", "pipeline-relay")
    os.makedirs(state_dir, exist_ok=True)
    safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_")[:80] or "unknown"
    state_path = os.path.join(state_dir, "%s.%s.json" % (safe, leaf))
    if os.path.isfile(state_path):
        with open(state_path) as fh:
            last = float(json.load(fh).get("last_relay") or 0)
        if rearm_min > 0 and (time.time() - last) < rearm_min * 60:
            bail()
except Exception:
    state_path = None  # cannot track -> relay anyway, never silently suppress

try:
    if state_path:
        tmp = state_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"last_relay": time.time(), "link": leaf}, fh)
        os.replace(tmp, state_path)
except Exception:
    pass

sys.stdout.write(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": directive,
    }
}))
bail()
PY

exit 0
