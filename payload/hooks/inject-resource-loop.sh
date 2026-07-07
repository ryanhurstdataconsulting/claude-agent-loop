#!/bin/bash
# SessionStart hook — injects the Resource Loop directive + registry index.
# ADDITIVE-ONLY: always exits 0; a broken registry degrades to directive-only.
REGISTRY="$HOME/.claude/registry/REGISTRY.md"
cat <<'EOF'
<resource-loop>
Run the Resource Loop before your first task (skill: resource-loop):
MATCH the task against the index below; ANNOUNCE one line starting
"Resource Loop — deploying:" (or "Resource Loop — no registry match;
proceeding bare."); ROUTE subagents (planning = session model, creation =
opus, mechanical = sonnet/haiku); EXECUTE; SCORE the result; LEARN (evaluate
heuristics → improve-now / theme-note / no-action). File GAPs (recurring
unmet needs) as candidate stubs in ~/.claude/registry/candidates/. Keyword
shortcuts for MATCH are in ~/.claude/registry/TRIGGERS.md. Carry this
directive into every subagent brief. First run on this machine? Run the
environment-bootstrap skill to tailor this config to your stack.
EOF
if [ -r "$REGISTRY" ]; then
  echo "--- REGISTRY INDEX ($(grep -c '^|' "$REGISTRY") rows) ---"
  cat "$REGISTRY"
else
  echo "--- REGISTRY INDEX unavailable; read ~/.claude/registry/guides/ on demand ---"
fi

# --- Nudge budget: at most 2 injected lines inside these tags (2 of 2 used). --
# Line 1 of 2: the loop-themes nudge (P4). When 10 or more theme rows are still
# unprocessed, point the session at the theme-assessment skill. Additive-only:
# if python3 or the counter tool is missing, or the count is not a plain
# integer, we inject nothing and never fail the session start.
# Line 2 of 2: the digest nudge (P5), added below after the themes block.
THEME_NUDGE_AT=10
THEMES_TOOL="$HOME/.claude/tools/themes_pending.py"
THEMES_FILE="$HOME/.claude/learning/LOOP_THEMES.md"
if command -v python3 >/dev/null 2>&1 && [ -r "$THEMES_TOOL" ]; then
  pending="$(python3 "$THEMES_TOOL" --file "$THEMES_FILE" 2>/dev/null)"
  case "$pending" in
    '' | *[!0-9]*) : ;;                     # empty or non-numeric — no nudge
    *)
      if [ "$pending" -ge "$THEME_NUDGE_AT" ]; then
        echo "Loop themes: $pending unprocessed — run Skill(theme-assessment)."
      fi
      ;;
  esac
fi

# Line 2 of 2: the digest nudge (P5). loop_digest.py --nudge prints one line
# when a digest is due (10+ undigested AUTO_COMMITS.log entries, or a stale/
# absent .last-digest with at least one undigested entry) and nothing otherwise.
# Same degrade discipline: a missing python3 or tool injects nothing, exit 0.
DIGEST_TOOL="$HOME/.claude/tools/loop_digest.py"
if command -v python3 >/dev/null 2>&1 && [ -r "$DIGEST_TOOL" ]; then
  digest_line="$(python3 "$DIGEST_TOOL" --nudge 2>/dev/null)"
  case "$digest_line" in
    '') : ;;                                # nothing due — no nudge
    *) printf '%s\n' "$digest_line" ;;
  esac
fi

echo "</resource-loop>"
exit 0
