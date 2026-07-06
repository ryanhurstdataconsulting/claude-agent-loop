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
[ $fails -eq 0 ] && echo "hook tests: OK" || echo "hook tests: FAIL"
exit $fails
