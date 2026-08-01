#!/bin/bash
# test_audit_run.sh — audit_run.sh worktree isolation and the headless launch.
#
# The properties under test are safety properties: a nightly, unattended audit
# must never disturb the live checkout it audits. Cases 2-4 are the ones that
# matter — branch unchanged, dirty working file untouched, no worktree left
# registered — and they hold whatever else the run does.
#
# No case invokes a real `claude` session: a stub is injected through
# AUDIT_CLAUDE_BIN, which the script must honour.
#
# macOS bash-3.2 portable. Hermetic: every repo and store lives under one
# mktemp -d that a trap removes.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$(cd "$HERE/.." && pwd)/audit_run.sh"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# A package repo with one commit and a dirty working file the run must not touch.
PKG="$TMP/pkg"; mkdir -p "$PKG"
git -C "$PKG" init -q
git -C "$PKG" config user.email t@example.com
git -C "$PKG" config user.name T
echo "app" > "$PKG/app.py"; git -C "$PKG" add app.py
git -C "$PKG" commit -q -m "init"
git -C "$PKG" checkout -q -b feature-in-progress
echo "WORK IN PROGRESS" > "$PKG/scratch.txt"

STORE="$TMP/store"; mkdir -p "$STORE/audit/runs"

# Stub claude: writes a SECURITY_AUDIT.md into the worktree, prints JSON.
STUB="$TMP/claude-stub"; cat > "$STUB" <<'EOS'
#!/bin/bash
wt=""; while [ $# -gt 0 ]; do [ "$1" = "--add-dir" ] && wt="$2"; shift; done
printf '# Security Audit\n\nNo findings.\n' > "$wt/SECURITY_AUDIT.md"
echo '{"result":"ok","findings":{"critical":0,"high":0,"medium":0,"low":1}}'
EOS
chmod +x "$STUB"

BEFORE_BRANCH="$(git -C "$PKG" branch --show-current)"
BEFORE_SCRATCH="$(cat "$PKG/scratch.txt")"
AUDIT_CLAUDE_BIN="$STUB" bash "$SCRIPT" "$PKG" "$STORE" >/dev/null 2>&1; rc=$?
[ $rc -eq 0 ] && pass "1 exit 0" || die "1 exit $rc"

# THE critical assertion: the live checkout is untouched.
[ "$(git -C "$PKG" branch --show-current)" = "$BEFORE_BRANCH" ] \
  && pass "2 live branch unchanged" || die "2 branch changed"
[ "$(cat "$PKG/scratch.txt")" = "$BEFORE_SCRATCH" ] \
  && pass "3 dirty working file untouched" || die "3 working file changed"
[ -z "$(git -C "$PKG" worktree list | grep -v "$PKG ")" ] \
  && pass "4 no stale worktree registered" || die "4 stale worktree left behind"
git -C "$PKG" rev-parse --verify "audit/security-$(date +%F)" >/dev/null 2>&1 \
  && pass "5 audit branch created" || die "5 no audit branch"
[ -n "$(ls "$STORE/audit/runs"/*/*.json 2>/dev/null)" ] \
  && pass "6 run log written" || die "6 no run log"

# Missing claude binary -> exit 4, no damage.
AUDIT_CLAUDE_BIN="$TMP/nope" bash "$SCRIPT" "$PKG" "$STORE" >/dev/null 2>&1
[ $? -eq 4 ] && pass "7 missing claude exits 4" || die "7 wrong exit for missing claude"

# Gate abort: a stub that plants a fake secret must abort and leave no branch.
STUB2="$TMP/claude-secret"; cat > "$STUB2" <<'EOS'
#!/bin/bash
wt=""; while [ $# -gt 0 ]; do [ "$1" = "--add-dir" ] && wt="$2"; shift; done
printf 'AKIAIOSFODNN7EXAMPLE\naws_secret_access_key = wJalrXUtnFEMI/K7MDENG\n' \
  > "$wt/SECURITY_AUDIT.md"
echo '{"result":"ok","findings":{"critical":0,"high":0,"medium":0,"low":0}}'
EOS
chmod +x "$STUB2"
git -C "$PKG" branch -D "audit/security-$(date +%F)" >/dev/null 2>&1
AUDIT_CLAUDE_BIN="$STUB2" bash "$SCRIPT" "$PKG" "$STORE" >/dev/null 2>&1
[ $? -eq 3 ] && pass "8 secret in audit file aborts (exit 3)" || die "8 gate did not abort"
git -C "$PKG" rev-parse --verify "audit/security-$(date +%F)" >/dev/null 2>&1 \
  && die "8b aborted run still left a branch" || pass "8b no branch after abort"

# 9. The commit body is machine-generated prose in front of a human, so it is
# held to the same grammar gate as any other generated text.
GATE="$(cd "$HERE/.." && pwd)/prose_grammar_gate.py"
git -C "$PKG" branch -D "audit/security-$(date +%F)" >/dev/null 2>&1
AUDIT_CLAUDE_BIN="$STUB" bash "$SCRIPT" "$PKG" "$STORE" >/dev/null 2>&1
git -C "$PKG" log -1 --format='%B' "audit/security-$(date +%F)" > "$TMP/body.txt" 2>/dev/null
python3 "$GATE" "$TMP/body.txt" >/dev/null 2>&1 \
  && pass "9 generated commit body passes the grammar gate" \
  || die "9 grammar gate flagged the commit body: $(python3 "$GATE" "$TMP/body.txt" 2>&1)"
grep -q "(1) Task & Change" "$TMP/body.txt" \
  && grep -q "(2) Tests created / modified" "$TMP/body.txt" \
  && grep -q "(3) Test results — evidence" "$TMP/body.txt" \
  && pass "9b commit body carries all three sections" || die "9b malformed commit body"

# 10. Interrupt safety: the trap is registered BEFORE the worktree is added, so
# a run killed mid-session leaves nothing registered against the live repo.
STUB3="$TMP/claude-slow"; cat > "$STUB3" <<'EOS'
#!/bin/bash
sleep 30
EOS
chmod +x "$STUB3"
AUDIT_CLAUDE_BIN="$STUB3" bash "$SCRIPT" "$PKG" "$STORE" >/dev/null 2>&1 &
runner=$!
i=0
while [ $i -lt 100 ] && [ -z "$(git -C "$PKG" worktree list | grep -v "$PKG ")" ]; do
  sleep 0.1; i=$((i + 1))
done
[ -n "$(git -C "$PKG" worktree list | grep -v "$PKG ")" ] \
  && pass "10 worktree registered while the session runs" \
  || die "10 worktree never appeared (case cannot prove anything)"
kill -TERM "$runner" 2>/dev/null
wait "$runner" 2>/dev/null
[ -z "$(git -C "$PKG" worktree list | grep -v "$PKG ")" ] \
  && pass "10b interrupted run leaves no worktree" || die "10b stale worktree after TERM"
[ "$(git -C "$PKG" branch --show-current)" = "$BEFORE_BRANCH" ] \
  && pass "10c interrupted run left the live branch alone" || die "10c branch changed"

[ $fail -eq 0 ] && { echo "test_audit_run: PASS"; exit 0; }
echo "test_audit_run: FAIL"; exit 1
