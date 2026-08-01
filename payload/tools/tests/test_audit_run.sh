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
# Silence the OS notification the gate-abort and severity paths would otherwise
# fire on a developer's desktop every time the suite runs.
export AUDIT_NOTIFY=0
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

# 8. A credential in the FINDINGS DOCUMENT quarantines; it must never vanish.
# Quoting the credential it found is a findings document's job, so the audits
# most worth reading are precisely the ones guaranteed to trip the secret
# gate. Discarding them with the worktree would mean this layer structurally
# cannot deliver its highest-value output. The document is copied into the
# store — local-only, no remote — and the package repo gets nothing.
STUB2="$TMP/claude-secret"; cat > "$STUB2" <<'EOS'
#!/bin/bash
wt=""; while [ $# -gt 0 ]; do [ "$1" = "--add-dir" ] && wt="$2"; shift; done
printf 'AKIAIOSFODNN7EXAMPLE\naws_secret_access_key = wJalrXUtnFEMI/K7MDENG\n' \
  > "$wt/SECURITY_AUDIT.md"
echo '{"result":"ok","findings":{"critical":0,"high":0,"medium":0,"low":0}}'
EOS
chmod +x "$STUB2"
QKEY="quarantine-case"
QLOG="$STORE/audit/runs/$QKEY/$(date +%F).json"
QFILE="$STORE/audit/quarantine/$QKEY/$(date +%F)-SECURITY_AUDIT.md"
git -C "$PKG" branch -D "audit/security-$(date +%F)" >/dev/null 2>&1
AUDIT_CLAUDE_BIN="$STUB2" bash "$SCRIPT" "$PKG" "$STORE" --key "$QKEY" \
  >/dev/null 2>&1
[ $? -eq 5 ] && pass "8 secret in the findings doc quarantines (exit 5)" \
  || die "8 findings doc was not quarantined"
[ -f "$QFILE" ] && pass "8b the findings document survives in the store" \
  || die "8b the findings document was discarded"
git -C "$PKG" rev-parse --verify "audit/security-$(date +%F)" >/dev/null 2>&1 \
  && die "8c quarantined run still created a branch" \
  || pass "8c no branch after quarantine"
grep -q '"verdict": "quarantined"' "$QLOG" \
  && pass "8d run log records the quarantined verdict" \
  || die "8d quarantined verdict not recorded"
grep -q '"last_audit_date"' "$QLOG" \
  && die "8e a quarantined run marked the package audited" \
  || pass "8e a quarantined run leaves the package due"

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
# Bounded, and the bound is the point. The stub sleeps 30s, so an unbounded
# check would also pass against a foreground CLI call — the run would just be
# cleaned up when the session ended on its own, 30 seconds later. Signal
# deferral is the defect this case exists to catch, so cleanup gets 5 seconds.
kill -TERM "$runner" 2>/dev/null
i=0
while [ $i -lt 50 ] && [ -n "$(git -C "$PKG" worktree list | grep -v "$PKG ")" ]; do
  sleep 0.1; i=$((i + 1))
done
[ -z "$(git -C "$PKG" worktree list | grep -v "$PKG ")" ] \
  && pass "10b interrupted run leaves no worktree (cleaned up in $((i + 1)) polls of 0.1s, deadline 50)" \
  || die "10b worktree still registered 5s after TERM — signal deferred?"
# Never let a failing mutant hang the suite on the stub's remaining sleep.
kill -KILL "$runner" 2>/dev/null
wait "$runner" 2>/dev/null
[ "$(git -C "$PKG" branch --show-current)" = "$BEFORE_BRANCH" ] \
  && pass "10c interrupted run left the live branch alone" || die "10c branch changed"

# 11. Cleanup reaches OUR worktree and nothing else. A developer's unrelated
# worktree whose directory is currently missing — an unmounted volume looks
# exactly like this — must survive the run. A repo-global `git worktree prune`
# would silently drop it.
OTHER="$TMP/other-worktree"
git -C "$PKG" worktree add -q --detach "$OTHER" HEAD 2>/dev/null
rm -rf "$OTHER"   # the volume goes away; the registration stays behind
git -C "$PKG" branch -D "audit/security-$(date +%F)" >/dev/null 2>&1
AUDIT_CLAUDE_BIN="$STUB" bash "$SCRIPT" "$PKG" "$STORE" >/dev/null 2>&1
git -C "$PKG" worktree list | grep -q "other-worktree" \
  && pass "11 unrelated worktree registration survives" \
  || die "11 cleanup pruned a worktree that was not ours"
git -C "$PKG" worktree list | grep -q "audit-pkg-" \
  && die "11b our own worktree was left registered" \
  || pass "11b our own worktree still removed"
git -C "$PKG" worktree remove --force "$OTHER" >/dev/null 2>&1
git -C "$PKG" worktree prune >/dev/null 2>&1

# 12. The other half of the split. A credential in a CODE FIX is an agent
# introducing a credential into the client's source, so it still aborts the
# commit outright — the quarantine path above applies to the findings prose
# and to nothing else.
STUB5="$TMP/claude-leaky-fix"; cat > "$STUB5" <<'EOS'
#!/bin/bash
wt=""; while [ $# -gt 0 ]; do [ "$1" = "--add-dir" ] && wt="$2"; shift; done
printf '# Security Audit\n\nNo findings.\n' > "$wt/SECURITY_AUDIT.md"
printf 'client = boto3.client(key="AKIAIOSFODNN7EXAMPLE")\n' >> "$wt/app.py"
echo '{"result":"ok","findings":{"critical":0,"high":0,"medium":0,"low":0}}'
EOS
chmod +x "$STUB5"
git -C "$PKG" branch -D "audit/security-$(date +%F)" >/dev/null 2>&1
AUDIT_CLAUDE_BIN="$STUB5" bash "$SCRIPT" "$PKG" "$STORE" >/dev/null 2>&1
[ $? -eq 3 ] && pass "12 secret in an agent-modified file aborts (exit 3)" \
  || die "12 ungated file reached the commit"
git -C "$PKG" rev-parse --verify "audit/security-$(date +%F)" >/dev/null 2>&1 \
  && die "12b aborted run still left a branch" || pass "12b no branch after abort"

# 13. An override that is set but EMPTY must fail, never fall through to the
# real CLI and launch a live, billed session.
AUDIT_CLAUDE_BIN="" bash "$SCRIPT" "$PKG" "$STORE" >/dev/null 2>&1
[ $? -eq 4 ] && pass "13 empty AUDIT_CLAUDE_BIN exits 4" \
  || die "13 empty override fell through to the real claude"

# 14. Two runs against the same package on the same date must not collide. The
# worktree directory name carries a per-run tag, so one run's fallback cleanup
# cannot drop a concurrent run's registration.
#
# The decoy below is named exactly as an UNDISAMBIGUATED run would name its
# worktree, and its directory is deleted first, so the per-run tag is the only
# thing standing between it and our cleanup — which is what makes this case
# fail if the tag is ever dropped.
DECOY="$TMP/concurrent/audit-pkg-$(date +%F)"
mkdir -p "$TMP/concurrent"
git -C "$PKG" worktree add -q --detach "$DECOY" HEAD 2>/dev/null
rm -rf "$DECOY"
git -C "$PKG" branch -D "audit/security-$(date +%F)" >/dev/null 2>&1
AUDIT_CLAUDE_BIN="$STUB" bash "$SCRIPT" "$PKG" "$STORE" >/dev/null 2>&1
git -C "$PKG" worktree list | grep -q "concurrent/audit-pkg-" \
  && pass "14 a same-name concurrent registration survives" \
  || die "14 cleanup dropped a concurrent run's registration"

# 14b. The same, but with the concurrent worktree still LIVE on disk — the
# reviewer's reproduction. A registration whose directory is present is never
# stale, whatever it is called.
LIVE="$TMP/live/audit-pkg-$(date +%F)"
mkdir -p "$TMP/live"
git -C "$PKG" worktree add -q --detach "$LIVE" HEAD 2>/dev/null
git -C "$PKG" branch -D "audit/security-$(date +%F)" >/dev/null 2>&1
AUDIT_CLAUDE_BIN="$STUB" bash "$SCRIPT" "$PKG" "$STORE" >/dev/null 2>&1
git -C "$PKG" worktree list | grep -q "live/audit-pkg-" \
  && pass "14b a live concurrent registration survives" \
  || die "14b cleanup dropped a live concurrent worktree"
[ -d "$LIVE" ] && pass "14c the live concurrent worktree is still on disk" \
  || die "14c live concurrent worktree deleted from disk"
git -C "$PKG" worktree list | grep -q "audit-pkg-$(date +%F)-" \
  && die "14d our own worktree was left registered" \
  || pass "14d our own worktree still removed"

# 15. THE key round-trip. A package key is a workspace-relative path, so a
# nested key must write state exactly where audit_dispatch.last_state reads
# it. A flat-name case cannot catch this: while the runner derived the key
# from `basename <package-path>`, state for HDC-shaped keys landed one level
# shallower than the reader looked, so every nested package reported "never
# audited" every night — a full agent session per package per night, forever.
NESTED_KEY="client-dir/pkg"
git -C "$PKG" branch -D "audit/security-$(date +%F)" >/dev/null 2>&1
AUDIT_CLAUDE_BIN="$STUB" bash "$SCRIPT" "$PKG" "$STORE" --key "$NESTED_KEY" \
  >/dev/null 2>&1
[ -f "$STORE/audit/runs/$NESTED_KEY/$(date +%F).json" ] \
  && pass "15 a nested key writes its run log at the nested path" \
  || die "15 nested run log not written where the key says"
ROUNDTRIP="$(cd "$HERE/.." && python3 -c '
import sys
sys.path.insert(0, ".")
import audit_dispatch
print(audit_dispatch.last_state(sys.argv[1], sys.argv[2]).get("last_audited_sha") or "")
' "$STORE" "$NESTED_KEY" 2>/dev/null)"
[ -n "$ROUNDTRIP" ] \
  && pass "15b audit_dispatch.last_state reads the nested key back" \
  || die "15b write/read key mismatch — the package would read as never audited"
[ "$ROUNDTRIP" = "$(git -C "$PKG" rev-parse HEAD)" ] \
  && pass "15c the round-tripped sha is this run's HEAD" \
  || die "15c round-tripped sha does not match HEAD"

# 16. The audited repository's own hooks must not run. A worktree shares
# `.git/hooks` with the checkout it came from, so without --no-verify a
# hanging or prompting pre-commit would stall this unattended run past its
# own timeout — which wraps only the CLI — and leave a worktree registered in
# the developer's repository indefinitely. A pre-commit that stages files
# would also put content into the index that the safety gates never scanned.
HOOK_MARK="$TMP/pre-commit-ran"
mkdir -p "$PKG/.git/hooks"
cat > "$PKG/.git/hooks/pre-commit" <<EOS
#!/bin/bash
touch "$HOOK_MARK"
exit 1
EOS
chmod +x "$PKG/.git/hooks/pre-commit"
git -C "$PKG" branch -D "audit/security-$(date +%F)" >/dev/null 2>&1
AUDIT_CLAUDE_BIN="$STUB" bash "$SCRIPT" "$PKG" "$STORE" --key hook-case \
  >/dev/null 2>&1
rc=$?
[ $rc -eq 0 ] && pass "16 the commit succeeds despite a failing pre-commit hook" \
  || die "16 the audited repo's pre-commit hook ran and broke the run (exit $rc)"
[ -f "$HOOK_MARK" ] && die "16b the pre-commit hook executed" \
  || pass "16b the pre-commit hook never executed"
rm -f "$PKG/.git/hooks/pre-commit"

# 17. A run log that cannot be written is a lost run, not a quiet success.
# Before this was checked, the empty count string fell through to a
# "audit: pkg —  critical,  high" notification: malformed AND wrong.
LOSTKEY="lost-log"
mkdir -p "$STORE/audit/runs"
printf 'not a directory\n' > "$STORE/audit/runs/$LOSTKEY"
git -C "$PKG" branch -D "audit/security-$(date +%F)" >/dev/null 2>&1
LOST_OUT="$TMP/lost.log"
AUDIT_CLAUDE_BIN="$STUB" bash "$SCRIPT" "$PKG" "$STORE" --key "$LOSTKEY" \
  > "$LOST_OUT" 2>&1
rc=$?
[ $rc -eq 1 ] && pass "17 an unwritable run log fails the run (exit 1)" \
  || die "17 an unwritable run log was ignored (exit $rc)"
grep -q "scheduler state was lost" "$LOST_OUT" \
  && pass "17b the lost run log is reported explicitly" \
  || die "17b no explicit report of the lost run log"
grep -qE '^audit_run: .* — +critical' "$LOST_OUT" \
  && die "17c a malformed count line was still emitted" \
  || pass "17c no malformed count line"
rm -f "$STORE/audit/runs/$LOSTKEY"

# 18. An absolute or traversing key must never write outside the store.
bash "$SCRIPT" "$PKG" "$STORE" --key "/etc/passwd" >/dev/null 2>&1
[ $? -eq 2 ] && pass "18 an absolute --key is refused" || die "18 absolute key accepted"
bash "$SCRIPT" "$PKG" "$STORE" --key "../escape" >/dev/null 2>&1
[ $? -eq 2 ] && pass "18b a traversing --key is refused" || die "18b '..' key accepted"

# --- post-checkout, the hook case 16 does not reach ---------------------------
# Case 16 covers pre-commit, which `--no-verify` suppresses. post-checkout
# obeys no such flag, and `worktree add` fires it in the audited repository
# before this script has run a single line of its own inside the worktree.
# Cases 19 and 20 below are the two halves of that hazard.
#
# The decoy registrations cases 11 and 14 deliberately left behind are cleared
# first, so `worktree list` minus the live checkout names our worktree and
# nothing else — the same idiom case 10 uses.
git -C "$PKG" worktree remove --force "$LIVE" >/dev/null 2>&1
git -C "$PKG" worktree prune >/dev/null 2>&1
mkdir -p "$PKG/.git/hooks"

# 19. The audited repository's post-checkout hook must never execute. It runs
# unattended, at 03:17, against a repository whose hooks this framework
# neither wrote nor reviewed — one that prompts, rewrites files, or calls out
# to the network is a real thing to find in a client checkout.
CO_MARK="$TMP/post-checkout-ran"
cat > "$PKG/.git/hooks/post-checkout" <<EOS
#!/bin/bash
touch "$CO_MARK"
exit 0
EOS
chmod +x "$PKG/.git/hooks/post-checkout"
rm -f "$CO_MARK"
git -C "$PKG" branch -D "audit/security-$(date +%F)" >/dev/null 2>&1
AUDIT_CLAUDE_BIN="$STUB" bash "$SCRIPT" "$PKG" "$STORE" --key post-checkout-case \
  >/dev/null 2>&1
rc=$?
[ $rc -eq 0 ] && pass "19 the run succeeds with a post-checkout hook installed" \
  || die "19 a post-checkout hook broke the run (exit $rc)"
[ -f "$CO_MARK" ] && die "19b the audited repo's post-checkout hook executed" \
  || pass "19b the post-checkout hook never executed"

# 20. Interrupt safety while the hook itself is what is slow. Case 10 proves
# the trap fires during the agent SESSION; this proves it fires during
# `worktree add`, which was the one hook-firing git call left running in the
# foreground. bash defers a trapped signal until the current foreground
# command returns, so a hanging post-checkout made the whole run
# un-interruptible and a TERM left our worktree registered in the developer's
# live repository — the exact damage the trap exists to prevent.
cat > "$PKG/.git/hooks/post-checkout" <<'EOS'
#!/bin/bash
sleep 20
EOS
chmod +x "$PKG/.git/hooks/post-checkout"
git -C "$PKG" branch -D "audit/security-$(date +%F)" >/dev/null 2>&1
AUDIT_CLAUDE_BIN="$STUB3" bash "$SCRIPT" "$PKG" "$STORE" --key hanging-hook-case \
  >/dev/null 2>&1 &
runner=$!
i=0
while [ $i -lt 100 ] && [ -z "$(git -C "$PKG" worktree list | grep -v "$PKG ")" ]; do
  sleep 0.1; i=$((i + 1))
done
[ -n "$(git -C "$PKG" worktree list | grep -v "$PKG ")" ] \
  && pass "20 worktree registered while the hanging hook case runs" \
  || die "20 worktree never appeared (case cannot prove anything)"
kill -TERM "$runner" 2>/dev/null
i=0
while [ $i -lt 50 ] && [ -n "$(git -C "$PKG" worktree list | grep -v "$PKG ")" ]; do
  sleep 0.1; i=$((i + 1))
done
[ -z "$(git -C "$PKG" worktree list | grep -v "$PKG ")" ] \
  && pass "20b TERM during a hanging post-checkout still cleans up (cleaned up in $((i + 1)) polls of 0.1s, deadline 50)" \
  || die "20b worktree still registered 5s after TERM — the hook deferred the signal"
kill -KILL "$runner" 2>/dev/null
wait "$runner" 2>/dev/null
[ "$(git -C "$PKG" branch --show-current)" = "$BEFORE_BRANCH" ] \
  && pass "20c the live branch survived the hanging-hook interrupt" \
  || die "20c branch changed"
rm -f "$PKG/.git/hooks/post-checkout"
git -C "$PKG" worktree prune >/dev/null 2>&1

[ $fail -eq 0 ] && { echo "test_audit_run: PASS"; exit 0; }
echo "test_audit_run: FAIL"; exit 1
