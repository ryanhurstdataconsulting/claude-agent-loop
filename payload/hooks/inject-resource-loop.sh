#!/bin/bash
# SessionStart hook — injects the Resource Loop directive + registry index.
# ADDITIVE-ONLY: always exits 0; a broken registry degrades to directive-only.
REGISTRY="$HOME/.claude/registry/REGISTRY.md"
cat <<'EOF'
<resource-loop>
Run the Resource Loop before your first task (skill: resource-loop):
MATCH the task against the index below; ANNOUNCE one line starting
"Resource Loop — deploying:" (or "Resource Loop — no registry match;
proceeding bare."); file GAPs as candidate stubs in
~/.claude/registry/candidates/; ROUTE subagents (planning = session model,
creation = opus, mechanical = sonnet/haiku). Keyword shortcuts for MATCH are
in ~/.claude/registry/TRIGGERS.md. Carry this directive into every subagent
brief. First run on this machine? Run the environment-bootstrap skill to
tailor this config to your stack.
EOF
if [ -r "$REGISTRY" ]; then
  echo "--- REGISTRY INDEX ($(grep -c '^|' "$REGISTRY") rows) ---"
  cat "$REGISTRY"
else
  echo "--- REGISTRY INDEX unavailable; read ~/.claude/registry/guides/ on demand ---"
fi
echo "</resource-loop>"
exit 0
