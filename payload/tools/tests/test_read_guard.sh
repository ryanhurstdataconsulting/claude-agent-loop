#!/bin/bash
# test_read_guard.sh — PreToolUse read-guard hook.
#
# The hook hard-blocks whole-file Reads of never-read-whole file classes
# (deny), soft-nudges large files read without offset/limit (allow +
# additionalContext), and fails open on every ambiguous or error case (allow).
# It ALWAYS exits 0 and signals only through hookSpecificOutput JSON — never
# exit 2, never "ask"/"defer". macOS bash-3.2 portable. Modeled on
# test_precompact_tmx.sh.
set -u

HOOK="$(cd "$(dirname "$0")/../../hooks" && pwd)/read-guard.sh"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Fixtures: one small text file, one large text file (1,500 lines).
SMALL="$TMP/notes.txt"
printf 'hello world\n' > "$SMALL"
BIG="$TMP/big.txt"
python3 -c "open('$BIG','w').write('x\n'*1500)"

# assert_json <label> <stdout> <python-assertion-body>
# Loads the hook's stdout as JSON, asserts hookEventName, then runs the body.
# A parse failure or a failed assert makes this return non-zero (the caller dies).
assert_json() {
  echo "$2" | python3 -c "import json,sys
d=json.load(sys.stdin)
h=d['hookSpecificOutput']
assert h['hookEventName']=='PreToolUse', 'wrong hookEventName'
$3" >/dev/null 2>&1
}

# 1. Hard-blocked file (package-lock.json) -> deny naming the class.
P1='{"tool_name":"Read","tool_input":{"file_path":"/repo/package-lock.json"}}'
out1="$(printf '%s' "$P1" | env CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "1 hard-block file: exit 0" || die "1 exit $rc"
assert_json "1" "$out1" "
assert h['permissionDecision']=='deny', 'expected deny'
r=h.get('permissionDecisionReason','')
assert isinstance(r,str) and r.strip(), 'missing reason'
assert 'lockfile' in r.lower(), 'reason must name the class'
" && pass "1 hard-block file: deny + reason names class" || die "1 bad JSON: $out1"

# 2. Hard-blocked directory segment (node_modules/) -> deny.
P2='{"tool_name":"Read","tool_input":{"file_path":"/repo/node_modules/left-pad/index.js"}}'
out2="$(printf '%s' "$P2" | env CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "2 hard-block dir: exit 0" || die "2 exit $rc"
assert_json "2" "$out2" "
assert h['permissionDecision']=='deny', 'expected deny'
assert 'node_modules' in h.get('permissionDecisionReason',''), 'reason names dir'
" && pass "2 hard-block dir: deny" || die "2 bad JSON: $out2"

# 3. Normal small file, no offset/limit -> allow, no additionalContext.
P3="{\"tool_name\":\"Read\",\"tool_input\":{\"file_path\":\"$SMALL\"}}"
out3="$(printf '%s' "$P3" | env CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "3 small file: exit 0" || die "3 exit $rc"
assert_json "3" "$out3" "
assert h['permissionDecision']=='allow', 'expected allow'
assert 'additionalContext' not in h, 'small file must not nudge'
" && pass "3 small file: allow, no nudge" || die "3 bad JSON: $out3"

# 4. Large file, no offset/limit -> allow + additionalContext nudge.
P4="{\"tool_name\":\"Read\",\"tool_input\":{\"file_path\":\"$BIG\"}}"
out4="$(printf '%s' "$P4" | env CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "4 large file: exit 0" || die "4 exit $rc"
assert_json "4" "$out4" "
assert h['permissionDecision']=='allow', 'expected allow'
c=h.get('additionalContext','')
assert isinstance(c,str) and c.strip(), 'large file must nudge'
assert 'offset' in c.lower(), 'nudge should mention offset/limit'
" && pass "4 large file: allow + nudge" || die "4 bad JSON: $out4"

# 5. Large file WITH offset/limit -> allow, no nudge.
P5="{\"tool_name\":\"Read\",\"tool_input\":{\"file_path\":\"$BIG\",\"offset\":100,\"limit\":50}}"
out5="$(printf '%s' "$P5" | env CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "5 large+offset: exit 0" || die "5 exit $rc"
assert_json "5" "$out5" "
assert h['permissionDecision']=='allow', 'expected allow'
assert 'additionalContext' not in h, 'offset/limit read must not nudge'
" && pass "5 large+offset: allow, no nudge" || die "5 bad JSON: $out5"

# 6. Malformed stdin JSON -> exit 0, allow, no crash.
out6="$(printf '%s' 'not json {{{' | env CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "6 malformed stdin: exit 0" || die "6 exit $rc"
assert_json "6" "$out6" "
assert h['permissionDecision']=='allow', 'malformed -> allow'
" && pass "6 malformed stdin: allow, no crash" || die "6 bad JSON: $out6"

# 7. Missing file_path AND nonexistent path -> allow, exit 0.
P7A='{"tool_name":"Read","tool_input":{}}'
out7a="$(printf '%s' "$P7A" | env CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "7a missing file_path: exit 0" || die "7a exit $rc"
assert_json "7a" "$out7a" "assert h['permissionDecision']=='allow', 'missing path -> allow'" \
  && pass "7a missing file_path: allow" || die "7a bad JSON: $out7a"
P7B='{"tool_name":"Read","tool_input":{"file_path":"/no/such/file/here.txt"}}'
out7b="$(printf '%s' "$P7B" | env CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "7b unreadable path: exit 0" || die "7b exit $rc"
assert_json "7b" "$out7b" "
assert h['permissionDecision']=='allow', 'unreadable path -> allow'
assert 'additionalContext' not in h, 'stat failure must not nudge'
" && pass "7b unreadable path: allow, no nudge" || die "7b bad JSON: $out7b"

# 8. MANIFEST wiring: no dedicated case here. test_install_symlinks.sh's existing
#    MANIFEST-driven install/uninstall scenarios pick up hooks/read-guard.sh
#    automatically once its `link-file` line lands in payload/MANIFEST (Task 2).

echo "---"
if [ $fail -eq 0 ]; then echo "test_read_guard: OK"; exit 0; else echo "test_read_guard: FAIL"; exit 1; fi
