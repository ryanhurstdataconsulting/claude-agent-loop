#!/bin/bash
# test_obs_events_gates.sh — gate.decision emission from read-guard.sh.
# macOS bash-3.2 portable.
#
# Formerly also covered a UserPromptSubmit gate's silent/inject paths; that
# hook's script has since been deleted (no keyword-scored PLAN backstop
# replaces it — see SKILL.md's "PLAN is judgment, not a gate"), so those two
# cases were removed along with it.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOKS_DIR="$(cd "$HERE/../../hooks" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

events_file() { find "$TMP/claude/metrics/events" -name '*.ndjson' 2>/dev/null | head -1; }
last_records() { f="$(events_file)"; [ -n "$f" ] && cat "$f" || true; }

# obs_emit.py serializes with json.dumps(sort_keys=True), which alphabetizes
# the nested attrs object too ("action" < "gate" < "score"), so "gate" never
# precedes "action" on the line. Match each attr independently via chained,
# order-agnostic greps rather than one combined ordered pattern.
assert_gate_action() {
  # assert_gate_action <recs> <gate> <action> <label>
  line="$(echo "$1" | grep "\"gate\":\"$2\"" | grep "\"action\":\"$3\"" | tail -1)"
  [ -n "$line" ] && pass "$4" || die "$4 missing (got: $1)"
}

# assert_one_record <recs> <session_id> <label> — guards against double
# emission (e.g. an explicit emit plus a second, accidental one from a
# shared choke-point function defaulting to another action on the same call).
assert_one_record() {
  count="$(echo "$1" | grep -c "\"session_id\":\"$2\"")"
  [ "$count" -eq 1 ] && pass "$3 (exactly one record)" || die "$3 wrong record count: $count (got: $1)"
}

# --- read-guard.sh: silent allow -> gate.decision action:silent -------------
payload="$(python3 -c "import json; print(json.dumps({'session_id':'g3','tool_input':{'file_path':'/tmp/small.txt'}}))")"
printf '%s' "$payload" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" bash "$HOOKS_DIR/read-guard.sh" >/dev/null
recs="$(last_records)"
assert_gate_action "$recs" "read-guard" "silent" "read-guard silent path recorded"
assert_one_record "$recs" "g3" "read-guard silent path"

# --- read-guard.sh: deny -> gate.decision action:deny -----------------------
payload="$(python3 -c "import json; print(json.dumps({'session_id':'g4','tool_input':{'file_path':'/x/package-lock.json'}}))")"
printf '%s' "$payload" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" bash "$HOOKS_DIR/read-guard.sh" >/dev/null
recs="$(last_records)"
assert_gate_action "$recs" "read-guard" "deny" "read-guard deny path recorded"
assert_one_record "$recs" "g4" "read-guard deny path"

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_obs_events_gates.sh"; exit 0
else
  echo "SOME FAILED - test_obs_events_gates.sh"; exit 1
fi
