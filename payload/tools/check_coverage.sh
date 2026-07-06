#!/bin/bash
# Static coverage check: the Resource Loop stub + a SUBAGENTS.md roster are
# present in each of your projects. "Projects" = immediate subdirectories of
# PROJECTS_DIR (default ~/projects) that contain a CLAUDE.md.
PROJECTS_DIR="${PROJECTS_DIR:-$HOME/projects}"
fail=0; total=0; okc=0
for p in "$PROJECTS_DIR"/*/; do
  [ -f "${p}CLAUDE.md" ] || continue
  total=$((total+1))
  ok=1
  grep -qs "Resource Loop" "${p}CLAUDE.md" || ok=0
  [ -f "${p}.claude/SUBAGENTS.md" ] || ok=0
  if [ $ok -eq 1 ]; then echo "OK   $(basename "$p")"; okc=$((okc+1)); else echo "MISS $(basename "$p")"; fail=1; fi
done
if [ $total -eq 0 ]; then
  echo "no projects with a CLAUDE.md under $PROJECTS_DIR (set PROJECTS_DIR to point elsewhere)"
  exit 0
fi
echo "coverage: $okc/$total"
exit $fail
