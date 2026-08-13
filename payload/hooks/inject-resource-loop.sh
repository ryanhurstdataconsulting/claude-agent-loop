#!/bin/bash
# SessionStart hook — emit PENDING WORK ONLY.
#
# This hook used to inject the full Resource Loop directive plus the entire
# REGISTRY.md index (~7,700 chars, ~1,900 tokens) into every single session.
# Both are static text. The hooks reference is explicit about that case:
#
#   "For static context that doesn't require a script, use CLAUDE.md instead."
#
# So the directive now lives in ~/.claude/CLAUDE.md section 3, where it is part
# of the cached prompt prefix and costs nothing per session, and the registry is
# PULLED on demand (the harness already surfaces skills by description; the
# index is only worth reading when a task looks unfamiliar).
#
# What is left here is the only genuinely dynamic part: state that changed since
# last session and that the agent cannot know without running something. When
# there is no pending work this hook emits NOTHING AT ALL — silence is the
# correct output, not a per-session reminder that the loop exists.
#
# ADDITIVE-ONLY: always exits 0. A missing python3 or a broken counter tool
# degrades to silence and never fails the session start.
set -u

_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="inject-resource-loop.sh" \
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

NUDGES=""

add_nudge() {
  # $1 = a single line, already validated non-empty by the caller.
  if [ -z "$NUDGES" ]; then NUDGES="$1"; else NUDGES="$NUDGES
$1"; fi
}

# --- 1. unprocessed loop themes ----------------------------------------------
THEME_NUDGE_AT=10
THEMES_TOOL="$HOME/.claude/tools/themes_pending.py"
THEMES_FILE="$HOME/.claude/learning/LOOP_THEMES.md"
if command -v python3 >/dev/null 2>&1 && [ -r "$THEMES_TOOL" ]; then
  pending="$(python3 "$THEMES_TOOL" --file "$THEMES_FILE" 2>/dev/null)"
  case "$pending" in
    '' | *[!0-9]*) : ;;                     # empty or non-numeric — no nudge
    *)
      if [ "$pending" -ge "$THEME_NUDGE_AT" ]; then
        add_nudge "Loop themes: $pending unprocessed — run Skill(theme-assessment)."
      fi
      ;;
  esac
fi

# --- 2. digest due ------------------------------------------------------------
DIGEST_TOOL="$HOME/.claude/tools/loop_digest.py"
if command -v python3 >/dev/null 2>&1 && [ -r "$DIGEST_TOOL" ]; then
  digest_line="$(python3 "$DIGEST_TOOL" --nudge 2>/dev/null)"
  [ -n "$digest_line" ] && add_nudge "$digest_line"
fi

# --- 3. gate-cleared resources ready to contribute upstream -------------------
CONTRIB_TOOL="$HOME/.claude/tools/loop_contribute.py"
if command -v python3 >/dev/null 2>&1 && [ -r "$CONTRIB_TOOL" ]; then
  contrib_line="$(python3 "$CONTRIB_TOOL" --nudge 2>/dev/null)"
  [ -n "$contrib_line" ] && add_nudge "$contrib_line"
fi

# --- 4. work orders closed unattended since last session ----------------------
# loop-close.sh (SessionEnd) links, assesses, and emits precise evidence with
# nobody watching, then leaves its result here. It deliberately does NOT act on
# a firing — patching a resource is a decision that wants a human present. This
# is where that human first appears, and it is one line, not homework.
CLOSE_DIR="$HOME/.claude/metrics/state/loop-close"
if command -v python3 >/dev/null 2>&1 && [ -d "$CLOSE_DIR" ]; then
  close_line="$(python3 - "$CLOSE_DIR" <<'PY' 2>/dev/null
import glob, json, os, sys
parts = firings = 0
plans = []
stale = []
for f in glob.glob(os.path.join(sys.argv[1], "*.json")):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    for c in d.get("closed") or []:
        parts += c.get("parts") or 0
        if c.get("plan_id"):
            plans.append(c["plan_id"])
    fr = d.get("firings")
    if isinstance(fr, list):
        firings += len(fr)
    stale.append(f)
if plans:
    msg = "Loop closed %d work order(s), %d part(s) assessed" % (len(plans), parts)
    if firings:
        msg += "; %d heuristic(s) fired — run Skill(resource-loop) LEARN to act" % firings
    else:
        msg += "; no heuristic fired"
    print(msg + ".")
    for f in stale:
        try:
            os.remove(f)
        except Exception:
            pass
PY
)"
  [ -n "$close_line" ] && add_nudge "$close_line"
fi

# --- 5. repo-security-audit digest ---------------------------------------------
# dispatch/run.sh already interrupts immediately for a Critical or High finding
# (see severity_alert in dispatch/digest.py — the same rule drives its own OS
# notification); everything routine waits here. Self-consuming like section 4
# above: the newest digest is reported once, then silent until the next one
# lands, so a routine night never trains the owner to ignore this line.
AUDIT_DIGEST_TOOL="$HOME/.claude/tools/dispatch/digest.py"
if command -v python3 >/dev/null 2>&1 && [ -r "$AUDIT_DIGEST_TOOL" ]; then
  audit_line="$(python3 "$AUDIT_DIGEST_TOOL" --nudge 2>/dev/null)"
  [ -n "$audit_line" ] && add_nudge "$audit_line"
fi

# --- emit only if there is something to say -----------------------------------
if [ -n "$NUDGES" ]; then
  echo "<resource-loop>"
  printf '%s\n' "$NUDGES"
  echo "(Loop protocol: ~/.claude/CLAUDE.md section 3. Registry index:"
  echo "~/.claude/registry/REGISTRY.md — read it only if the task looks unfamiliar.)"
  echo "</resource-loop>"
fi

exit 0
