#!/bin/bash
# test_auto_update.sh — auto-update hook: fast-forward pull on session start /
# stale resume, with pre-flight guards that never clobber local work.
# Uses a real bare "origin" + a working clone. macOS bash-3.2 portable.
set -u

HOOK="$(cd "$(dirname "$0")/../../hooks" && pwd)/auto-update.sh"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
G() { git -C "$1" "${@:2}" >/dev/null 2>&1; }
head_of() { git -C "$1" rev-parse --short HEAD; }
advance_origin() { # make a new upstream commit via the second clone
  printf '%s\n' "$1" >> "$TMP/second/payload/MANIFEST"
  G "$TMP/second" add -A; G "$TMP/second" commit -m "$1"; G "$TMP/second" push origin main
}

# --- build origin + working clone + a second clone to advance origin ---------
git init -q --bare "$TMP/origin"
git clone -q "$TMP/origin" "$TMP/work"
G "$TMP/work" checkout -b main
mkdir -p "$TMP/work/payload"; printf 'v1\n' > "$TMP/work/payload/MANIFEST"
G "$TMP/work" add -A; G "$TMP/work" commit -m init; G "$TMP/work" push -u origin main
git clone -q "$TMP/origin" "$TMP/second"

export CLAUDE_DIR="$TMP/claude"
export AGENT_LOOP_STATE_DIR="$TMP/state"
export AGENT_LOOP_REPO="$TMP/work"
export AGENT_LOOP_UPDATE_RUN_INSTALL=0    # exercise pull logic, don't run install
mkdir -p "$TMP/state"
STAMP="$TMP/state/last-pull"
stale() { printf '0\n' > "$STAMP"; }
fresh() { python3 -c 'import time;print(int(time.time()))' > "$STAMP"; }
SS='{"hook_event_name":"SessionStart","source":"startup"}'
UP='{"hook_event_name":"UserPromptSubmit"}'

# 1. opt-out: silent, no pull.
b="$(head_of "$TMP/work")"; stale
out="$(printf '%s' "$SS" | AGENT_LOOP_AUTO_UPDATE=0 bash "$HOOK")"; rc=$?
{ [ $rc -eq 0 ] && [ -z "$out" ] && [ "$(head_of "$TMP/work")" = "$b" ]; } \
  && pass "opt-out: silent, no pull" || die "opt-out rc=$rc out=$out"

# 2. new session, stale, origin ahead -> fast-forward pull + announce.
advance_origin upstream-1
b="$(head_of "$TMP/work")"; stale
out="$(printf '%s' "$SS" | bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] || die "new-session exit $rc"
echo "$out" | grep -q "claude-agent-loop updated" && pass "new session: pulled + announced" || die "no update: $out"
[ "$(head_of "$TMP/work")" != "$b" ] && pass "new session: HEAD fast-forwarded" || die "HEAD did not move"
echo "$out" | python3 -c 'import json,sys;d=json.load(sys.stdin);assert d["hookSpecificOutput"]["hookEventName"]=="SessionStart";assert d["systemMessage"].strip()' >/dev/null 2>&1 \
  && pass "new session: valid hook JSON" || die "bad JSON: $out"

# 3. dedup: SessionStart with a fresh stamp -> no attempt.
fresh
out="$(printf '%s' "$SS" | bash "$HOOK")"
[ -z "$out" ] && pass "dedup: fresh stamp -> silent" || die "dedup emitted: $out"

# 4a. idle not met: UserPromptSubmit with a fresh stamp -> silent.
fresh
out="$(printf '%s' "$UP" | bash "$HOOK")"
[ -z "$out" ] && pass "idle-not-met: silent" || die "idle emitted: $out"

# 4b. idle met: UserPromptSubmit with a stale stamp -> pull.
advance_origin upstream-2
b="$(head_of "$TMP/work")"; stale
out="$(printf '%s' "$UP" | bash "$HOOK")"
{ echo "$out" | grep -q updated && [ "$(head_of "$TMP/work")" != "$b" ]; } \
  && pass "idle-met: pulled on stale prompt" || die "idle-met failed: $out"
echo "$out" | grep -q '"hookEventName": "UserPromptSubmit"' && pass "idle: correct event name" || die "wrong event: $out"

# 5. dirty pre-flight -> skip + nudge, no pull.
advance_origin upstream-3
printf 'dirty-edit\n' > "$TMP/work/payload/MANIFEST"
b="$(head_of "$TMP/work")"; stale
out="$(printf '%s' "$SS" | bash "$HOOK")"
{ echo "$out" | grep -qi uncommitted && [ "$(head_of "$TMP/work")" = "$b" ]; } \
  && pass "dirty: skipped + nudged, no pull" || die "dirty failed: $out"
G "$TMP/work" checkout -- payload/MANIFEST

# 6. diverged pre-flight (local commit + origin ahead) -> skip + nudge, no pull.
printf 'local-only\n' >> "$TMP/work/payload/MANIFEST"
G "$TMP/work" add -A; G "$TMP/work" commit -m local-only
b="$(head_of "$TMP/work")"; stale
out="$(printf '%s' "$SS" | bash "$HOOK")"
{ { echo "$out" | grep -qi unpushed || echo "$out" | grep -qi diverged; } && [ "$(head_of "$TMP/work")" = "$b" ]; } \
  && pass "diverged: skipped + nudged, no pull" || die "diverged failed: $out"

echo "---"
if [ $fail -eq 0 ]; then echo "test_auto_update: OK"; exit 0; else echo "test_auto_update: FAIL"; exit 1; fi
