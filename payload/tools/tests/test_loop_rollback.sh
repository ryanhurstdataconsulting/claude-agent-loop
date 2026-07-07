#!/bin/bash
# test_loop_rollback.sh — sandboxed tests for the auto-commit rollback tool (P5).
#
# Everything runs against throwaway git repos and a throwaway $HOME. The tool
# must revert ONLY loop-authored commits (`loop:` subject prefix), log each
# revert, and honour --last N newest-first ordering. Written TDD-first — the
# tool does not exist yet, so every case fails RED until it is built.
#
# macOS bash-3.2 portable; no `set -e`.
# Run: bash test_loop_rollback.sh

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"
ROLLBACK="$TOOLS/loop_rollback.sh"

fails=0
pass() { printf 'PASS - %s\n' "$1"; }
fail() { printf 'FAIL - %s\n' "$1"; fails=$((fails + 1)); }

SANDBOX="$(mktemp -d 2>/dev/null || mktemp -d -t calrb)"
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

new_fw_repo() {
  fw="$SANDBOX/fw-$1"; rm -rf "$fw"; mkdir -p "$fw"
  git -C "$fw" init -q
  git -C "$fw" config user.email test@example.com
  git -C "$fw" config user.name "Test Bot"
  printf 'seed\n' > "$fw/README.md"
  git -C "$fw" add README.md >/dev/null 2>&1
  git -C "$fw" commit -qm init >/dev/null 2>&1
  printf '%s' "$fw"
}

new_home() {
  h="$SANDBOX/home-$1"; rm -rf "$h"; mkdir -p "$h/.claude/learning"
  printf '%s' "$h"
}

# git commit adding <file> with subject <subject>; echoes the sha.
mk_commit() {
  repo="$1"; file="$2"; subject="$3"
  printf 'body of %s\n' "$file" > "$repo/$file"
  git -C "$repo" add -- "$file" >/dev/null 2>&1
  git -C "$repo" commit -qm "$subject" >/dev/null 2>&1
  git -C "$repo" rev-parse HEAD
}

run_rb() {
  h="$1"; fw="$2"; shift 2
  env HOME="$h" LOOP_FRAMEWORK_REPO="$fw" PATH="/usr/bin:/bin:$PATH" \
      bash "$ROLLBACK" "$@" 2>&1
}

if [ ! -f "$ROLLBACK" ]; then
  echo "FAIL - loop_rollback.sh not found at $ROLLBACK (RED: build it first)"
  exit 1
fi

# --- Case 1: revert of a loop: commit works + is logged ----------------------
FW="$(new_fw_repo one)"; H="$(new_home one)"
S1="$(mk_commit "$FW" a.txt 'loop: add a')"
S2="$(mk_commit "$FW" b.txt 'loop: add b')"
before="$(git -C "$FW" rev-list --count HEAD)"
out="$(run_rb "$H" "$FW" "$S2")"; rc=$?
[ "$rc" -eq 0 ] && pass "single: exit 0" || fail "single: exit $rc — $out"
after="$(git -C "$FW" rev-list --count HEAD)"
[ "$after" = "$((before + 1))" ] && pass "single: a revert commit was created" || fail "single: no revert commit ($before -> $after)"
head_subj="$(git -C "$FW" log -1 --format=%s)"
case "$head_subj" in Revert*) pass "single: HEAD is a Revert commit" ;; *) fail "single: HEAD subject '$head_subj'" ;; esac
# b.txt (added by S2) should be gone after the revert.
[ ! -f "$FW/b.txt" ] && pass "single: reverted file removed" || fail "single: b.txt survived the revert"
LOG="$H/.claude/learning/AUTO_COMMITS.log"
if [ -f "$LOG" ] && grep -q 'REVERT' "$LOG" && grep -q "$S2" "$LOG"; then
  pass "single: REVERT logged referencing the original sha"
else
  fail "single: REVERT not logged for $S2"
fi

# --- Case 2: a non-loop commit is refused (exit 4) ---------------------------
FW="$(new_fw_repo two)"; H="$(new_home two)"
_="$(mk_commit "$FW" a.txt 'loop: add a')"
HUMAN="$(mk_commit "$FW" c.txt 'regular human change')"
before="$(git -C "$FW" rev-list --count HEAD)"
out="$(run_rb "$H" "$FW" "$HUMAN")"; rc=$?
[ "$rc" -eq 4 ] && pass "human: refused with exit 4" || fail "human: exit $rc (expected 4) — $out"
after="$(git -C "$FW" rev-list --count HEAD)"
[ "$after" = "$before" ] && pass "human: no commit created" || fail "human: a commit was created ($before -> $after)"

# --- Case 3: --last N reverts newest-first -----------------------------------
FW="$(new_fw_repo last)"; H="$(new_home last)"
mkdir -p "$H/.claude/learning"
S1="$(mk_commit "$FW" a.txt 'loop: add a')"
S2="$(mk_commit "$FW" b.txt 'loop: add b')"
FWB="$(basename "$FW")"
LOG="$H/.claude/learning/AUTO_COMMITS.log"
{
  printf '2026-07-06T00:00:01Z\t%s\t%s\tloop: add a\t-\n' "$FWB" "$S1"
  printf '2026-07-06T00:00:02Z\t%s\t%s\tloop: add b\t-\n' "$FWB" "$S2"
} > "$LOG"
out="$(run_rb "$H" "$FW" --last 2)"; rc=$?
[ "$rc" -eq 0 ] && pass "last: exit 0" || fail "last: exit $rc — $out"
# Both files removed (both reverted).
{ [ ! -f "$FW/a.txt" ] && [ ! -f "$FW/b.txt" ]; } && pass "last: both commits reverted" || fail "last: not both reverted (a=$([ -f "$FW/a.txt" ] && echo present || echo gone) b=$([ -f "$FW/b.txt" ] && echo present || echo gone))"
# Newest-first: the first REVERT line appended must reference S2 (the newest).
first_revert="$(grep 'REVERT' "$LOG" | head -1)"
case "$first_revert" in
  *"$S2"*) pass "last: newest reverted first" ;;
  *) fail "last: first revert did not reference newest ($first_revert)" ;;
esac

# --- Case 4 (BI2): a mixed two-lane commit is ONE group → --last 1 reverts both
# A mixed commit writes two ledger lines (framework + local) sharing a GROUP id
# (6th tab field). `--last 1` operates on logical GROUPS, so it must revert BOTH
# halves, not just the newest single line.
FW="$(new_fw_repo grp)"; H="$(new_home grp)"
# A local repo living at $H/.claude (basename '.claude' = the logged local repo).
git -C "$H/.claude" init -q
git -C "$H/.claude" config user.email test@example.com
git -C "$H/.claude" config user.name "Test Bot"
printf 'seed\n' > "$H/.claude/README.md"
git -C "$H/.claude" add README.md >/dev/null 2>&1
git -C "$H/.claude" commit -qm init >/dev/null 2>&1
FL="$(mk_commit "$FW" fwfile.txt 'loop: mixed grp [framework]')"
LL="$(mk_commit "$H/.claude" locfile.txt 'loop: mixed grp [local]')"
GID="$(printf '%s' "$FL" | cut -c1-8)"
LOCB="$(basename "$H/.claude")"
LOG="$H/.claude/learning/AUTO_COMMITS.log"
{
  printf '2026-07-07T00:00:01Z\t%s\t%s\tloop: mixed grp [framework]\t-\t%s\n' "$(basename "$FW")" "$FL" "$GID"
  printf '2026-07-07T00:00:02Z\t%s\t%s\tloop: mixed grp [local]\t-\t%s\n' "$LOCB" "$LL" "$GID"
} > "$LOG"
out="$(run_rb "$H" "$FW" --last 1)"; rc=$?
[ "$rc" -eq 0 ] && pass "grp: exit 0" || fail "grp: exit $rc — $out"
# --last 1 = one GROUP = BOTH halves reverted: fwfile.txt AND locfile.txt gone.
[ ! -f "$FW/fwfile.txt" ] && pass "grp: framework half reverted" || fail "grp: fwfile.txt survived"
[ ! -f "$H/.claude/locfile.txt" ] && pass "grp: local half reverted" || fail "grp: locfile.txt survived"
# Both original shas referenced by REVERT lines.
if grep -q "$FL" "$LOG" && grep -q "$LL" "$LOG"; then
  pass "grp: both halves logged as reverted"
else
  fail "grp: missing REVERT for one half"
fi

echo "---"
if [ "$fails" -eq 0 ]; then echo "loop_rollback tests: OK"; else echo "loop_rollback tests: FAIL ($fails)"; fi
exit "$fails"
