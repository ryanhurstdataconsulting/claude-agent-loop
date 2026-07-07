#!/bin/bash
# Tests the SessionStart hook: normal output + corrupt-registry degradation.
# Targets the payload hook (payload/hooks/inject-resource-loop.sh), which
# hardcodes $HOME/.claude/registry/REGISTRY.md internally — so the
# degraded-mode case below still exercises this machine's installed registry.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
H="$HERE/../../hooks/inject-resource-loop.sh"
R="$HOME/.claude/registry/REGISTRY.md"
fails=0
out=$("$H"); rc=$?
[ $rc -eq 0 ] || { echo "FAIL: exit $rc"; fails=1; }
echo "$out" | grep -q '<resource-loop>' || { echo "FAIL: no directive"; fails=1; }
echo "$out" | grep -q 'REGISTRY INDEX' || { echo "FAIL: no index"; fails=1; }
mv "$R" "$R.bak"
out=$("$H"); rc=$?
mv "$R.bak" "$R"
[ $rc -eq 0 ] || { echo "FAIL: corrupt-case exit $rc"; fails=1; }
echo "$out" | grep -q 'INDEX unavailable' || { echo "FAIL: no degraded notice"; fails=1; }

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

[ $fails -eq 0 ] && echo "hook tests: OK" || echo "hook tests: FAIL"
exit $fails
