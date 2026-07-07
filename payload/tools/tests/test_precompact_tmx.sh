#!/bin/bash
# test_precompact_tmx.sh — PreCompact hook: TOKEN MINIMIZER EXTREME escalation.
#
# The hook records each compaction (existing behavior) AND counts compactions
# per session; on the Nth compaction (threshold, default 2) it emits a hook JSON
# object (systemMessage + hookSpecificOutput.additionalContext) that prompts the
# user to approve the TOKEN MINIMIZER EXTREME rule set. It prompts exactly once
# per session and always exits 0. macOS bash-3.2 portable.
set -u

HOOK="$(cd "$(dirname "$0")/../../hooks" && pwd)/precompact-event.sh"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CLAUDE_DIR="$TMP/claude"
export METRICS_DIR="$TMP/metrics"
SID="sess-abc-123"
PAYLOAD="{\"session_id\":\"$SID\",\"hook_event_name\":\"PreCompact\"}"

# 1. First compaction: exit 0, empty stdout (no escalation yet).
out1="$(printf '%s' "$PAYLOAD" | bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "1st compaction exits 0" || die "1st compaction exit $rc"
[ -z "$out1" ] && pass "1st compaction: silent (no escalation)" || die "1st emitted: $out1"

# 2. Second compaction: escalation JSON on stdout.
out2="$(printf '%s' "$PAYLOAD" | bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "2nd compaction exits 0" || die "2nd compaction exit $rc"
echo "$out2" | grep -q "TOKEN MINIMIZER EXTREME" \
  && pass "2nd compaction prompts TOKEN MINIMIZER EXTREME" || die "2nd no TMX prompt: $out2"
echo "$out2" | python3 -c 'import json,sys
d=json.load(sys.stdin)
assert isinstance(d.get("systemMessage"),str) and d["systemMessage"].strip(), "no systemMessage"
h=d["hookSpecificOutput"]
assert h["hookEventName"]=="PreCompact", "wrong hookEventName"
assert isinstance(h["additionalContext"],str) and h["additionalContext"].strip(), "no additionalContext"
assert "approv" in h["additionalContext"].lower(), "context must require approval"
' >/dev/null 2>&1 \
  && pass "2nd compaction: valid hook JSON (systemMessage + approval-gated additionalContext)" \
  || die "2nd invalid hook JSON: $out2"

# 3. Third compaction: silent (prompted exactly once per session).
out3="$(printf '%s' "$PAYLOAD" | bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "3rd compaction exits 0" || die "3rd compaction exit $rc"
[ -z "$out3" ] && pass "3rd compaction: silent (prompted once already)" || die "3rd re-prompted: $out3"

# 4. All three compaction records were still written to the shard.
n="$(cat "$METRICS_DIR"/*.jsonl 2>/dev/null | grep -c '"kind":"compaction"')"
[ "$n" -ge 3 ] && pass "compaction records written ($n)" || die "expected >=3 records, got $n"

# 5. Missing session_id: exit 0, empty stdout, no crash (cannot count -> no escalation).
out5="$(printf '%s' '{}' | bash "$HOOK")"; rc=$?
{ [ $rc -eq 0 ] && [ -z "$out5" ]; } && pass "missing session_id: exit 0, silent" \
  || die "missing session_id rc=$rc out=$out5"

# 6. Malformed stdin: exit 0, no crash.
printf '%s' 'not json at all' | bash "$HOOK" >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && pass "malformed stdin: exit 0" || die "malformed stdin exit $rc"

# 7. Threshold override via env: THRESHOLD=1 prompts on the first compaction of a new session.
SID2="sess-override"
out7="$(printf '%s' "{\"session_id\":\"$SID2\"}" | TOKEN_MINIMIZER_THRESHOLD=1 bash "$HOOK")"
echo "$out7" | grep -q "TOKEN MINIMIZER EXTREME" \
  && pass "threshold override (1) prompts on 1st compaction" || die "override failed: $out7"

echo "---"
if [ $fail -eq 0 ]; then echo "test_precompact_tmx: OK"; exit 0; else echo "test_precompact_tmx: FAIL"; exit 1; fi
