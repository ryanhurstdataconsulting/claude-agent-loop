#!/bin/bash
# test_workorder_gate.sh — UserPromptSubmit work-order gate.
#
# The hook scores the prompt on plan_task.py's creativity gate and injects a
# decomposition directive only when it trips. It must stay SILENT on
# conversational prompts, on slash commands, and on every failure path, and it
# must re-arm rather than nudge on every turn of a long session. It ALWAYS exits
# 0 and signals only through hookSpecificOutput JSON. macOS bash-3.2 portable.
# Modeled on test_read_guard.sh.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$(cd "$HERE/../../hooks" && pwd)/workorder-gate.sh"
TOOLS="$(cd "$HERE/.." && pwd)"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Every run gets its own METRICS_DIR so the re-arm state never leaks between
# cases, and TOOLS_DIR points at the repo copy rather than the installed one.
run() {
  # run <session-id> <prompt-json-safe-text> [extra env assignments...]
  sid="$1"; prompt="$2"; shift 2
  payload="$(python3 -c "import json,sys; print(json.dumps({'session_id': sys.argv[1], 'prompt': sys.argv[2], 'hook_event_name': 'UserPromptSubmit'}))" "$sid" "$prompt")"
  printf '%s' "$payload" | env TOOLS_DIR="$TOOLS" METRICS_DIR="$TMP/metrics" "$@" bash "$HOOK"
}

has_directive() {
  echo "$1" | python3 -c "import json,sys
d=json.load(sys.stdin)
h=d['hookSpecificOutput']
assert h['hookEventName']=='UserPromptSubmit', 'wrong hookEventName'
assert 'WORK-ORDER GATE' in h['additionalContext'], 'no gate directive'
assert 'superpowers:brainstorming' in h['additionalContext'], 'brainstorming missing'
assert 'superpowers:writing-plans' in h['additionalContext'], 'writing-plans missing'
" >/dev/null 2>&1
}

# 1. Creative prompt -> directive injected, exit 0.
out="$(run s1 "build a new coach dashboard with rankings")"; rc=$?
[ $rc -eq 0 ] && pass "1 creative prompt: exit 0" || die "1 exit $rc"
if has_directive "$out"; then pass "1 creative prompt: directive injected"
else die "1 creative prompt: no directive (got: $out)"; fi

# 2. Conversational prompt -> completely silent.
out="$(run s2 "what did that error message mean")"; rc=$?
[ $rc -eq 0 ] && pass "2 conversational: exit 0" || die "2 exit $rc"
[ -z "$out" ] && pass "2 conversational: silent" || die "2 not silent (got: $out)"

# 3. Slash command -> silent even though it scores creative.
out="$(run s3 "/build a new thing")"
[ -z "$out" ] && pass "3 slash command: silent" || die "3 not silent (got: $out)"

# 4. Empty prompt -> silent.
out="$(run s4 "")"
[ -z "$out" ] && pass "4 empty prompt: silent" || die "4 not silent (got: $out)"

# 5. Re-arm: the same session nudged twice in a row only nudges once.
out1="$(run s5 "build a new dashboard")"
out2="$(run s5 "design a new report layout")"
if has_directive "$out1"; then pass "5 re-arm: first nudge fires"
else die "5 re-arm: first nudge missing"; fi
[ -z "$out2" ] && pass "5 re-arm: second suppressed" || die "5 second not suppressed"

# 6. A different session is not suppressed by another session's state.
out="$(run s6 "build a new dashboard")"
if has_directive "$out"; then pass "6 per-session state: independent"
else die "6 per-session state: wrongly suppressed"; fi

# 7. Re-arm window of 0 minutes disables suppression.
out1="$(run s7 "build a new dashboard" WORKORDER_GATE_REARM_MINUTES=0)"
out2="$(run s7 "build a new dashboard" WORKORDER_GATE_REARM_MINUTES=0)"
if has_directive "$out1" && has_directive "$out2"; then
  pass "7 rearm=0: both nudge"
else die "7 rearm=0: suppression still applied"; fi

# 8. Kill switch.
out="$(run s8 "build a new dashboard" WORKORDER_GATE_DISABLE=1)"; rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && pass "8 kill switch: silent, exit 0" \
  || die "8 kill switch failed (rc=$rc out=$out)"

# 9. Malformed hook JSON -> fails open, silent, exit 0.
out="$(printf '{not json' | env TOOLS_DIR="$TOOLS" METRICS_DIR="$TMP/metrics" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && pass "9 malformed JSON: fails open" \
  || die "9 malformed JSON (rc=$rc out=$out)"

# 10. Empty stdin -> fails open, silent, exit 0.
out="$(printf '' | env TOOLS_DIR="$TOOLS" METRICS_DIR="$TMP/metrics" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && pass "10 empty stdin: fails open" \
  || die "10 empty stdin (rc=$rc out=$out)"

# 11. Unimportable plan_task.py -> fails open rather than erroring.
out="$(run s11 "build a new dashboard" TOOLS_DIR="$TMP/nonexistent")"; rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && pass "11 missing tool: fails open" \
  || die "11 missing tool (rc=$rc out=$out)"

# 12. The directive tells the agent it may overrule a misjudged score.
out="$(run s12 "build a new dashboard")"
if echo "$out" | python3 -c "import json,sys
c=json.load(sys.stdin)['hookSpecificOutput']['additionalContext']
assert 'can misjudge' in c, 'no override affordance'" >/dev/null 2>&1; then
  pass "12 directive offers an override"
else die "12 directive has no override affordance"; fi

# 13. An unreadable state directory still nudges (never silently suppresses).
BLOCKED="$TMP/blocked"
printf 'not a directory' > "$BLOCKED"
out="$(run s13 "build a new dashboard" METRICS_DIR="$BLOCKED")"
if has_directive "$out"; then pass "13 unwritable state: nudges anyway"
else die "13 unwritable state: wrongly silent"; fi

if [ "$fail" -eq 0 ]; then
  echo "test_workorder_gate: PASS"
  exit 0
fi
echo "test_workorder_gate: FAIL"
exit 1
