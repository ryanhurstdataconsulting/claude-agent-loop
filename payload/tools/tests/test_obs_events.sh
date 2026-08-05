#!/bin/bash
# test_obs_events.sh — PreToolUse/PostToolUse/Stop structured event hook.
# Modeled on test_workorder_gate.sh. macOS bash-3.2 portable.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$(cd "$HERE/../../hooks" && pwd)/obs-events.sh"
TOOLS="$(cd "$HERE/.." && pwd)"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

events_file() {
  find "$TMP/claude/metrics/events" -name '*.ndjson' 2>/dev/null | head -1
}

last_records() {
  f="$(events_file)"
  [ -n "$f" ] && cat "$f" || true
}

run() {
  # run <json-payload>
  printf '%s' "$1" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" bash "$HOOK"
}

# 1. PreToolUse with tool_use_id -> tool.pre record, exits 0.
payload='{"hook_event_name":"PreToolUse","session_id":"s1","tool_name":"Read","tool_use_id":"tu-1","tool_input":{"file_path":"/x"}}'
run "$payload"; rc=$?
[ $rc -eq 0 ] && pass "1 PreToolUse: exit 0" || die "1 exit $rc"
recs="$(last_records)"
echo "$recs" | grep -q '"event":"tool.pre"' && pass "1 tool.pre recorded" || die "1 no tool.pre (got: $recs)"
echo "$recs" | grep -q '"tool_name":"Read"' && pass "1 tool_name attr present" || die "1 missing tool_name"

# 2. Matching PostToolUse (same tool_use_id) -> tool.post with duration_ms and ok=true.
payload='{"hook_event_name":"PostToolUse","session_id":"s1","tool_name":"Read","tool_use_id":"tu-1","tool_input":{"file_path":"/x"},"tool_response":{"isError":false}}'
run "$payload" >/dev/null; rc=$?
[ $rc -eq 0 ] && pass "2 PostToolUse: exit 0" || die "2 exit $rc"
recs="$(last_records)"
echo "$recs" | grep -q '"event":"tool.post"' && pass "2 tool.post recorded" || die "2 no tool.post"
echo "$recs" | grep -q '"ok":true' && pass "2 ok:true derived" || die "2 ok not true (got: $recs)"
echo "$recs" | grep -q '"duration_ms":' && pass "2 duration_ms present" || die "2 no duration_ms"

# 3. PostToolUse with isError:true -> ok:false, error_class captured.
payload3pre='{"hook_event_name":"PreToolUse","session_id":"s2","tool_name":"Bash","tool_use_id":"tu-2","tool_input":{"command":"false"}}'
run "$payload3pre" >/dev/null
payload3post='{"hook_event_name":"PostToolUse","session_id":"s2","tool_name":"Bash","tool_use_id":"tu-2","tool_input":{"command":"false"},"tool_response":{"isError":true,"error":"exit 1"}}'
run "$payload3post" >/dev/null
recs="$(last_records)"
echo "$recs" | grep -q '"ok":false' && pass "3 ok:false on error" || die "3 ok not false"
echo "$recs" | grep -q '"error_class":"exit 1"' && pass "3 error_class captured" || die "3 error_class missing (got: $recs)"

# 4. Stop -> turn.stop record.
payload4='{"hook_event_name":"Stop","session_id":"s3"}'
run "$payload4" >/dev/null; rc=$?
[ $rc -eq 0 ] && pass "4 Stop: exit 0" || die "4 exit $rc"
recs="$(last_records)"
echo "$recs" | grep -q '"event":"turn.stop"' && pass "4 turn.stop recorded" || die "4 no turn.stop"

# 5. Fallback pairing when tool_use_id is absent: pre then post for same
#    (session, tool_name) still pair via the sequence-counter fallback.
payload5pre='{"hook_event_name":"PreToolUse","session_id":"s4","tool_name":"Grep","tool_input":{}}'
run "$payload5pre" >/dev/null
payload5post='{"hook_event_name":"PostToolUse","session_id":"s4","tool_name":"Grep","tool_input":{},"tool_response":{"isError":false}}'
run "$payload5post" >/dev/null
recs="$(last_records)"
pre_span="$(echo "$recs" | grep '"event":"tool.pre"' | grep '"tool_name":"Grep"' | python3 -c "import json,sys; [print(json.loads(l)['span_id']) for l in sys.stdin if l.strip()]" 2>/dev/null | tail -1)"
post_span="$(echo "$recs" | grep '"event":"tool.post"' | grep '"tool_name":"Grep"' | python3 -c "import json,sys; [print(json.loads(l)['span_id']) for l in sys.stdin if l.strip()]" 2>/dev/null | tail -1)"
if [ -n "$pre_span" ] && [ "$pre_span" = "$post_span" ]; then
  pass "5 fallback pairing: pre/post share span_id"
else
  die "5 fallback pairing failed (pre=$pre_span post=$post_span)"
fi

# 5b. Overlapping fallback pairing: pre1, pre2 (same session/tool_name, no
#     tool_use_id) both fire before either post. FIFO pairing requires
#     post1 -> pre1's span_id and post2 -> pre2's span_id, not "post reads
#     whatever the counter currently holds" (which would wrongly pair
#     post1 with pre2).
payload5bpre1='{"hook_event_name":"PreToolUse","session_id":"s6","tool_name":"Grep","tool_input":{"pattern":"a"}}'
run "$payload5bpre1" >/dev/null
payload5bpre2='{"hook_event_name":"PreToolUse","session_id":"s6","tool_name":"Grep","tool_input":{"pattern":"b"}}'
run "$payload5bpre2" >/dev/null
payload5bpost1='{"hook_event_name":"PostToolUse","session_id":"s6","tool_name":"Grep","tool_input":{"pattern":"a"},"tool_response":{"isError":false}}'
run "$payload5bpost1" >/dev/null
payload5bpost2='{"hook_event_name":"PostToolUse","session_id":"s6","tool_name":"Grep","tool_input":{"pattern":"b"},"tool_response":{"isError":false}}'
run "$payload5bpost2" >/dev/null
recs="$(last_records)"
pre_spans="$(echo "$recs" | grep '"event":"tool.pre"' | grep '"session_id":"s6"' | python3 -c "import json,sys; [print(json.loads(l)['span_id']) for l in sys.stdin if l.strip()]" 2>/dev/null)"
post_spans="$(echo "$recs" | grep '"event":"tool.post"' | grep '"session_id":"s6"' | python3 -c "import json,sys; [print(json.loads(l)['span_id']) for l in sys.stdin if l.strip()]" 2>/dev/null)"
pre1_span="$(echo "$pre_spans" | sed -n '1p')"
pre2_span="$(echo "$pre_spans" | sed -n '2p')"
post1_span="$(echo "$post_spans" | sed -n '1p')"
post2_span="$(echo "$post_spans" | sed -n '2p')"
if [ -n "$pre1_span" ] && [ "$pre1_span" = "$post1_span" ] && [ -n "$pre2_span" ] && [ "$pre2_span" = "$post2_span" ]; then
  pass "5b overlapping fallback pairing: post1->pre1, post2->pre2 (FIFO)"
else
  die "5b overlapping fallback pairing failed (pre1=$pre1_span post1=$post1_span pre2=$pre2_span post2=$post2_span)"
fi

# 6. Malformed stdin JSON -> silent, still exits 0.
out="$(printf '%s' '{not json' | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "6 malformed input: exit 0" || die "6 exit $rc"

# 7. OBS_EVENTS_DISABLE=1 -> no record written, exit 0.
before="$(last_records | wc -l)"
payload7='{"hook_event_name":"Stop","session_id":"s5"}'
printf '%s' "$payload7" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" OBS_EVENTS_DISABLE=1 bash "$HOOK"; rc=$?
after="$(last_records | wc -l)"
[ $rc -eq 0 ] && pass "7 kill switch: exit 0" || die "7 exit $rc"
[ "$before" -eq "$after" ] && pass "7 kill switch: no new record" || die "7 record written despite kill switch"

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_obs_events.sh"
  exit 0
else
  echo "SOME FAILED - test_obs_events.sh"
  exit 1
fi
