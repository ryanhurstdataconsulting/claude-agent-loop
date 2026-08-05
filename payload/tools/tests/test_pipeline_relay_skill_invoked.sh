#!/bin/bash
# test_pipeline_relay_skill_invoked.sh — skill.invoked fires for every Skill
# call, not only the two known RELAYS leaves. macOS bash-3.2 portable.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$(cd "$HERE/../../hooks" && pwd)/pipeline-relay.sh"
TOOLS="$(cd "$HERE/.." && pwd)"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

events_file() { find "$TMP/claude/metrics/events" -name '*.ndjson' 2>/dev/null | head -1; }
last_records() { f="$(events_file)"; [ -n "$f" ] && cat "$f" || true; }

run() {
  printf '%s' "$1" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" METRICS_DIR="$TMP/claude/metrics" bash "$HOOK"
}

# 1. A skill with NO relay directive (e.g. "resource-loop") still emits skill.invoked.
payload="$(python3 -c "import json; print(json.dumps({'session_id':'sk1','tool_name':'Skill','tool_input':{'skill':'resource-loop'}}))")"
run "$payload" >/dev/null
recs="$(last_records)"
echo "$recs" | grep -q '"event":"skill.invoked"' && pass "1 skill.invoked recorded for unmapped skill" || die "1 missing (got: $recs)"
echo "$recs" | grep -q '"skill_name":"resource-loop"' && pass "1 skill_name attr correct" || die "1 wrong skill_name"

# 2. A plugin-qualified skill name ("superpowers:brainstorming") records the leaf.
payload="$(python3 -c "import json; print(json.dumps({'session_id':'sk2','tool_name':'Skill','tool_input':{'skill':'superpowers:brainstorming'}}))")"
run "$payload" >/dev/null
recs="$(last_records)"
echo "$recs" | grep -q '"skill_name":"brainstorming"' && pass "2 leaf extracted from plugin-qualified name" || die "2 wrong skill_name (got: $recs)"

# 3. Non-Skill tool call -> no skill.invoked record.
before="$(last_records | grep -c '"event":"skill.invoked"' || true)"
payload="$(python3 -c "import json; print(json.dumps({'session_id':'sk3','tool_name':'Read','tool_input':{'file_path':'/x'}}))")"
run "$payload" >/dev/null
after="$(last_records | grep -c '"event":"skill.invoked"' || true)"
[ "$before" -eq "$after" ] && pass "3 non-Skill tool: no new skill.invoked" || die "3 unexpected skill.invoked for Read"

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_pipeline_relay_skill_invoked.sh"; exit 0
else
  echo "SOME FAILED - test_pipeline_relay_skill_invoked.sh"; exit 1
fi
