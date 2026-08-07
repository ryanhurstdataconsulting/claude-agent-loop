#!/bin/bash
# test_pipeline_relay.sh — PostToolUse relay that keeps the design chain going.
#
# The hook must relay ONLY on the two superpowers design skills, stay silent on
# every other skill and every other tool, survive a plugin-prefix rename, re-arm
# rather than nag, and fail open on every malformed input. It ALWAYS exits 0 and
# signals only through hookSpecificOutput JSON. macOS bash-3.2 portable.
# Modeled on test_workorder_gate.sh.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$(cd "$HERE/../../hooks" && pwd)/pipeline-relay.sh"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# run <session-id> <tool-name> <skill> [env...]
run() {
  sid="$1"; tool="$2"; skill="$3"; shift 3
  payload="$(python3 -c "
import json,sys
print(json.dumps({'session_id': sys.argv[1], 'tool_name': sys.argv[2],
                  'tool_input': {'skill': sys.argv[3]},
                  'hook_event_name': 'PostToolUse'}))" "$sid" "$tool" "$skill")"
  printf '%s' "$payload" | env METRICS_DIR="$TMP/metrics" CLAUDE_DIR="$TMP/claude" "$@" bash "$HOOK"
}

# contains <stdout> <needle>
contains() {
  echo "$1" | python3 -c "
import json,sys
d=json.load(sys.stdin)
h=d['hookSpecificOutput']
assert h['hookEventName']=='PostToolUse', 'wrong hookEventName'
assert sys.argv[1] in h['additionalContext'], 'missing: '+sys.argv[1]
" "$2" >/dev/null 2>&1
}

# absent <stdout> <needle> — asserts substring is NOT present
absent() {
  echo "$1" | python3 -c "
import json,sys
d=json.load(sys.stdin)
h=d['hookSpecificOutput']
assert h['hookEventName']=='PostToolUse', 'wrong hookEventName'
assert sys.argv[1] not in h['additionalContext'], 'should be absent: '+sys.argv[1]
" "$2" >/dev/null 2>&1
}

# 1. brainstorming -> relay naming writing-plans as the next link.
out="$(run s1 Skill superpowers:brainstorming)"; rc=$?
[ $rc -eq 0 ] && pass "1 brainstorming: exit 0" || die "1 exit $rc"
if contains "$out" "superpowers:writing-plans"; then
  pass "1 brainstorming: points at writing-plans"
else die "1 brainstorming: no next link (got: $out)"; fi
if contains "$out" "spec is not a decomposition"; then
  pass "1 brainstorming: names the observed failure"
else die "1 brainstorming: missing the spec/decomposition warning"; fi

# 2. writing-plans -> relay naming plan_task.py --from-plan.
out="$(run s2 Skill superpowers:writing-plans)"
if contains "$out" "plan_task.py --from-plan"; then
  pass "2 writing-plans: points at plan_task.py --from-plan"
else die "2 writing-plans: no work-order step (got: $out)"; fi
if contains "$out" "plan_task.py --record"; then
  pass "2 writing-plans: uses --record for recording"
else die "2 writing-plans: missing --record step"; fi
if contains "$out" "score_task.py --auto"; then
  pass "2 writing-plans: uses score_task.py --auto"
else die "2 writing-plans: missing score_task.py --auto"; fi
if absent "$out" "make_brief.py"; then
  pass "2 writing-plans: make_brief.py not present"
else die "2 writing-plans: make_brief.py should be absent"; fi
if absent "$out" "assess_task.py"; then
  pass "2 writing-plans: assess_task.py not present"
else die "2 writing-plans: assess_task.py should be absent"; fi

# 3. An unrelated skill is silent.
out="$(run s3 Skill sports-analyst)"
[ -z "$out" ] && pass "3 unrelated skill: silent" || die "3 not silent (got: $out)"

# 4. A non-Skill tool is silent.
out="$(run s4 Bash superpowers:brainstorming)"
[ -z "$out" ] && pass "4 non-Skill tool: silent" || die "4 not silent (got: $out)"

# 5. Plugin-prefix independence: a bare name still relays.
out="$(run s5 Skill brainstorming)"
if contains "$out" "superpowers:writing-plans"; then
  pass "5 bare skill name: still relays"
else die "5 bare skill name: missed"; fi

# 6. Case independence.
out="$(run s6 Skill SuperPowers:Writing-Plans)"
if contains "$out" "plan_task.py --from-plan"; then
  pass "6 mixed case: still relays"
else die "6 mixed case: missed"; fi

# 7. Re-arm: same session, same link, twice -> only the first relays.
out1="$(run s7 Skill superpowers:brainstorming)"
out2="$(run s7 Skill superpowers:brainstorming)"
if contains "$out1" "writing-plans"; then pass "7 re-arm: first fires"
else die "7 re-arm: first missing"; fi
[ -z "$out2" ] && pass "7 re-arm: second suppressed" || die "7 second not suppressed"

# 8. The two links are tracked independently within one session.
out="$(run s7 Skill superpowers:writing-plans)"
if contains "$out" "plan_task.py --from-plan"; then
  pass "8 links independent: writing-plans still relays"
else die "8 links independent: wrongly suppressed"; fi

# 9. A different session is unaffected by another's state.
out="$(run s9 Skill superpowers:brainstorming)"
if contains "$out" "writing-plans"; then pass "9 per-session state: independent"
else die "9 per-session state: wrongly suppressed"; fi

# 10. rearm=0 disables suppression.
out1="$(run s10 Skill superpowers:brainstorming PIPELINE_RELAY_REARM_MINUTES=0)"
out2="$(run s10 Skill superpowers:brainstorming PIPELINE_RELAY_REARM_MINUTES=0)"
if contains "$out1" "writing-plans" && contains "$out2" "writing-plans"; then
  pass "10 rearm=0: both relay"
else die "10 rearm=0: suppression still applied"; fi

# 11. Kill switch.
out="$(run s11 Skill superpowers:brainstorming PIPELINE_RELAY_DISABLE=1)"; rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && pass "11 kill switch: silent, exit 0" \
  || die "11 kill switch failed (rc=$rc out=$out)"

# 12. Malformed JSON -> fails open.
out="$(printf '{not json' | env METRICS_DIR="$TMP/metrics" CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && pass "12 malformed JSON: fails open" \
  || die "12 malformed JSON (rc=$rc out=$out)"

# 13. Empty stdin -> fails open.
out="$(printf '' | env METRICS_DIR="$TMP/metrics" CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && pass "13 empty stdin: fails open" \
  || die "13 empty stdin (rc=$rc out=$out)"

# 14. Missing tool_input -> fails open, no crash.
out="$(printf '{"tool_name":"Skill","session_id":"s14"}' \
  | env METRICS_DIR="$TMP/metrics" CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && pass "14 missing tool_input: fails open" \
  || die "14 missing tool_input (rc=$rc out=$out)"

# 15. An unwritable state path still relays rather than silently suppressing.
BLOCKED="$TMP/blocked"
printf 'not a directory' > "$BLOCKED"
out="$(run s15 Skill superpowers:brainstorming METRICS_DIR="$BLOCKED")"
if contains "$out" "writing-plans"; then pass "15 unwritable state: relays anyway"
else die "15 unwritable state: wrongly silent"; fi

if [ "$fail" -eq 0 ]; then
  echo "test_pipeline_relay: PASS"
  exit 0
fi
echo "test_pipeline_relay: FAIL"
exit 1
