#!/bin/bash
# Tests the SessionStart hook: PENDING-WORK-ONLY output.
#
# Rewritten for the behaviour 2a5d7bb shipped. The hook no longer prints a
# static directive or cats the registry index — both are static text that now
# live in ~/.claude/CLAUDE.md as part of the cached prompt prefix. It emits ONLY
# state that changed since the last session, and NOTHING AT ALL when there is no
# pending work. The old assertions ("REGISTRY INDEX", "INDEX unavailable") tested
# output that was deliberately removed, and the degraded case moved this
# machine's REAL registry aside to do it — a hazard as well as a stale test.
#
# Every case runs under an isolated HOME so the live ~/.claude is never touched.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
H="$HERE/../../hooks/inject-resource-loop.sh"
fails=0

# Silence is the correct output when nothing is pending. An empty isolated HOME
# has no themes file, no digest ledger, and no closed work orders.
QUIET_HOME="$(mktemp -d 2>/dev/null || mktemp -d -t calquiet)"
mkdir -p "$QUIET_HOME/.claude/learning"
out=$(env HOME="$QUIET_HOME" "$H"); rc=$?
[ $rc -eq 0 ] || { echo "FAIL: quiet-case exit $rc"; fails=1; }
[ -z "$out" ] || { echo "FAIL: emitted output with nothing pending: $out"; fails=1; }

# A closed work order surfaces as exactly one line, inside the tags, and the
# artifact is consumed so the same nudge never repeats.
CLOSE_HOME="$(mktemp -d 2>/dev/null || mktemp -d -t calclose)"
mkdir -p "$CLOSE_HOME/.claude/metrics/state/loop-close" "$CLOSE_HOME/.claude/learning"
cat > "$CLOSE_HOME/.claude/metrics/state/loop-close/s1.json" <<'JSON'
{"session_id":"s1","closed":[{"plan_id":"wo-x","parts":3,"linked":1,
 "verdicts":{"clean":2,"dirty":1}}],"firings":[]}
JSON
out=$(env HOME="$CLOSE_HOME" "$H"); rc=$?
[ $rc -eq 0 ] || { echo "FAIL: loop-close exit $rc"; fails=1; }
printf '%s\n' "$out" | grep -q '<resource-loop>' \
  || { echo "FAIL: loop-close nudge not wrapped in tags"; fails=1; }
n=$(printf '%s\n' "$out" | grep -c 'Loop closed 1 work order(s), 3 part(s) assessed')
[ "$n" -eq 1 ] || { echo "FAIL: expected 1 loop-close line, got $n"; fails=1; }
[ -f "$CLOSE_HOME/.claude/metrics/state/loop-close/s1.json" ] \
  && { echo "FAIL: loop-close artifact not consumed"; fails=1; }
out=$(env HOME="$CLOSE_HOME" "$H")
[ -z "$out" ] || { echo "FAIL: loop-close nudge repeated: $out"; fails=1; }
rm -rf "$QUIET_HOME" "$CLOSE_HOME"

# --- Loop-themes nudge (P4) --------------------------------------------------
# The hook resolves the counter tool and the themes file from $HOME/.claude, so
# every themes case runs under an isolated HOME=$TMP — the real ~/.claude is
# never touched. The nudge fires once at 10 or more NEW rows and not below.
HOOK="$H"                                 # $H is reused below for temp HOMEs
TOOLS="$(cd "$HERE/.." && pwd)"           # payload/tools
SANDBOX="$(mktemp -d 2>/dev/null || mktemp -d -t calthemes)"
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

# Build an isolated HOME with the counter tool installed and a themes file of
# $2 NEW rows. Prints the HOME path.
theme_home() {
  h="$SANDBOX/$1"
  rm -rf "$h"
  mkdir -p "$h/.claude/tools" "$h/.claude/learning"
  cp "$TOOLS/themes_pending.py" "$h/.claude/tools/" 2>/dev/null
  {
    echo '| status | date | project | theme-tag | note | metrics-ref |'
    echo '|---|---|---|---|---|---|'
    i=0
    while [ "$i" -lt "$2" ]; do
      echo "| NEW | 2026-07-06 | proj | tag-$i | note $i | 2026-07#task_id=agent-$i |"
      i=$((i + 1))
    done
  } > "$h/.claude/learning/LOOP_THEMES.md"
  printf '%s' "$h"
}

# Case A: 12 NEW rows -> exactly one nudge line, inside the tags, exit 0.
H="$(theme_home twelve 12)"
out=$(env HOME="$H" "$HOOK"); rc=$?
[ $rc -eq 0 ] || { echo "FAIL: themes-12 exit $rc"; fails=1; }
n=$(printf '%s\n' "$out" | grep -c 'Loop themes: 12 unprocessed')
[ "$n" -eq 1 ] || { echo "FAIL: expected 1 nudge line, got $n"; fails=1; }
# The nudge must sit between the <resource-loop> tags.
printf '%s\n' "$out" | awk '/<resource-loop>/{o=1} /Loop themes: 12 unprocessed/{if(o)f=1} /<\/resource-loop>/{o=0} END{exit f?0:1}' \
  || { echo "FAIL: nudge not inside <resource-loop> tags"; fails=1; }

# Case B: 3 NEW rows -> no nudge line, exit 0.
H="$(theme_home three 3)"
out=$(env HOME="$H" "$HOOK"); rc=$?
[ $rc -eq 0 ] || { echo "FAIL: themes-3 exit $rc"; fails=1; }
printf '%s\n' "$out" | grep -q 'Loop themes:' && { echo "FAIL: nudge fired below threshold"; fails=1; }

# Case C: tool missing -> degrade to no nudge, exit 0. (python3-absent degrades
# through the same guard; not simulated directly since the harness cannot
# reliably remove python3 from PATH portably.)
H="$SANDBOX/notool"
rm -rf "$H"; mkdir -p "$H/.claude/learning"
{
  echo '| status | date | project | theme-tag | note | metrics-ref |'
  i=0; while [ "$i" -lt 12 ]; do echo "| NEW | d | p | t-$i | n | r |"; i=$((i + 1)); done
} > "$H/.claude/learning/LOOP_THEMES.md"
out=$(env HOME="$H" "$HOOK"); rc=$?
[ $rc -eq 0 ] || { echo "FAIL: themes-notool exit $rc"; fails=1; }
printf '%s\n' "$out" | grep -q 'Loop themes:' && { echo "FAIL: nudge fired with tool missing"; fails=1; }

# --- Digest nudge (P5, line 2 of 2) ------------------------------------------
# The hook resolves loop_digest.py and the ledger from $HOME/.claude, so every
# case runs under an isolated HOME=$TMP. The nudge fires at 10 or more undigested
# AUTO_COMMITS.log entries and stays quiet when nothing is due.

# Build an isolated HOME with loop_digest.py installed and a ledger of $2 loop
# entries; optionally seed .last-digest with $3. Prints the HOME path.
digest_home() {
  h="$SANDBOX/$1"
  rm -rf "$h"
  mkdir -p "$h/.claude/tools" "$h/.claude/learning"
  cp "$TOOLS/loop_digest.py" "$h/.claude/tools/" 2>/dev/null
  {
    i=0
    while [ "$i" -lt "$2" ]; do
      printf '2026-01-01T00:00:00Z\tclaude-agent-loop\tsha%d\tloop: change %d\t-\n' "$i" "$i"
      i=$((i + 1))
    done
  } > "$h/.claude/learning/AUTO_COMMITS.log"
  [ -n "${3:-}" ] && printf '%s' "$3" > "$h/.claude/learning/.last-digest"
  printf '%s' "$h"
}

# Case D: 12 undigested entries, no .last-digest -> exactly one digest nudge.
H="$(digest_home dtwelve 12)"
out=$(env HOME="$H" "$HOOK"); rc=$?
[ $rc -eq 0 ] || { echo "FAIL: digest-12 exit $rc"; fails=1; }
n=$(printf '%s\n' "$out" | grep -c 'Loop digest pending: 12')
[ "$n" -eq 1 ] || { echo "FAIL: expected 1 digest nudge, got $n"; fails=1; }
printf '%s\n' "$out" | awk '/<resource-loop>/{o=1} /Loop digest pending: 12/{if(o)f=1} /<\/resource-loop>/{o=0} END{exit f?0:1}' \
  || { echo "FAIL: digest nudge not inside <resource-loop> tags"; fails=1; }

# Case E: entries all predate a later .last-digest -> nothing undigested, no nudge.
H="$(digest_home drecent 5 '2026-06-01T00:00:00Z')"
out=$(env HOME="$H" "$HOOK"); rc=$?
[ $rc -eq 0 ] || { echo "FAIL: digest-recent exit $rc"; fails=1; }
printf '%s\n' "$out" | grep -q 'Loop digest pending:' && { echo "FAIL: digest nudge fired with nothing undigested"; fails=1; }

# Case F: tool missing -> degrade to no nudge, exit 0.
H="$SANDBOX/dnotool"
rm -rf "$H"; mkdir -p "$H/.claude/learning"
{ i=0; while [ "$i" -lt 12 ]; do printf '2026-01-01T00:00:00Z\tr\ts%d\tloop: c\t-\n' "$i"; i=$((i + 1)); done; } \
  > "$H/.claude/learning/AUTO_COMMITS.log"
out=$(env HOME="$H" "$HOOK"); rc=$?
[ $rc -eq 0 ] || { echo "FAIL: digest-notool exit $rc"; fails=1; }
printf '%s\n' "$out" | grep -q 'Loop digest pending:' && { echo "FAIL: digest nudge fired with tool missing"; fails=1; }

# --- Audit-digest nudge (section 5) -------------------------------------------
# The hook resolves dispatch/digest.py and the store from $HOME/.claude, so every
# case runs under an isolated HOME=$TMP. The nudge fires once for an unread
# digest, then goes quiet — self-consuming, unlike the plain threshold nudges
# above — and stays quiet when there is no digest at all or the tool is missing.

# Build an isolated HOME with dispatch/digest.py (and its dispatch/store.py
# dependency) installed. Prints the HOME path.
audit_home() {
  h="$SANDBOX/$1"
  rm -rf "$h"
  mkdir -p "$h/.claude/tools/dispatch" "$h/.claude/metrics/audit/digests"
  cp "$TOOLS/dispatch/digest.py" "$TOOLS/dispatch/store.py" \
     "$h/.claude/tools/dispatch/" 2>/dev/null
  printf '%s' "$h"
}

# Case G: an unread digest -> exactly one audit nudge, inside the tags, and it
# does not repeat on the next session once reported.
H="$(audit_home aunread)"
echo '# stub digest' > "$H/.claude/metrics/audit/digests/2026-07-30.md"
out=$(env HOME="$H" "$HOOK"); rc=$?
[ $rc -eq 0 ] || { echo "FAIL: audit-unread exit $rc"; fails=1; }
n=$(printf '%s\n' "$out" | grep -c 'Audit digest ready for review')
[ "$n" -eq 1 ] || { echo "FAIL: expected 1 audit nudge, got $n"; fails=1; }
printf '%s\n' "$out" | awk '/<resource-loop>/{o=1} /Audit digest ready for review/{if(o)f=1} /<\/resource-loop>/{o=0} END{exit f?0:1}' \
  || { echo "FAIL: audit nudge not inside <resource-loop> tags"; fails=1; }
out2=$(env HOME="$H" "$HOOK")
[ -z "$out2" ] || { echo "FAIL: audit nudge repeated: $out2"; fails=1; }

# Case H: no digest at all -> no audit nudge, exit 0.
H="$(audit_home anone)"
out=$(env HOME="$H" "$HOOK"); rc=$?
[ $rc -eq 0 ] || { echo "FAIL: audit-none exit $rc"; fails=1; }
printf '%s\n' "$out" | grep -q 'Audit digest ready for review' && { echo "FAIL: audit nudge fired with no digest"; fails=1; }

# Case I: tool missing -> degrade to no nudge, exit 0.
H="$SANDBOX/anotool"
rm -rf "$H"; mkdir -p "$H/.claude/metrics/audit/digests"
echo '# stub digest' > "$H/.claude/metrics/audit/digests/2026-07-30.md"
out=$(env HOME="$H" "$HOOK"); rc=$?
[ $rc -eq 0 ] || { echo "FAIL: audit-notool exit $rc"; fails=1; }
printf '%s\n' "$out" | grep -q 'Audit digest ready for review' && { echo "FAIL: audit nudge fired with tool missing"; fails=1; }

[ $fails -eq 0 ] && echo "hook tests: OK" || echo "hook tests: FAIL"
exit $fails
