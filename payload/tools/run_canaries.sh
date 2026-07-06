#!/bin/bash
# Live coverage probe: each of your projects' sessions announces the Resource
# Loop. A canary passes when a fresh headless session started in the project
# directory emits a "Resource Loop —" announce line. "Projects" = immediate
# subdirectories of PROJECTS_DIR (default ~/projects) that contain a CLAUDE.md.
PROJECTS_DIR="${PROJECTS_DIR:-$HOME/projects}"
MODEL="${CANARY_MODEL:-claude-haiku-4-5-20251001}"
PROMPT='Canary probe: output ONLY your Resource Loop ANNOUNCE line (it starts "Resource Loop —") for the task "add a small utility script to this project". Nothing else.'
pass=0; fail=0; total=0
for p in "$PROJECTS_DIR"/*/; do
  [ -f "${p}CLAUDE.md" ] || continue
  total=$((total+1))
  name=$(basename "$p")
  out=$(cd "$p" && claude -p "$PROMPT" --model "$MODEL" 2>/dev/null)
  if echo "$out" | grep -qE 'Resource Loop —'; then
    echo "PASS $name"; pass=$((pass+1))
  else
    echo "FAIL $name :: ${out:0:80}"; fail=$((fail+1))
  fi
done
if [ $total -eq 0 ]; then
  echo "no projects with a CLAUDE.md under $PROJECTS_DIR (set PROJECTS_DIR to point elsewhere)"
  exit 0
fi
echo "canaries: $pass/$total passed"
exit $fail
