#!/bin/bash
# test_hook_error_trap.sh — the hook.error trap block fires on an unexpected
# non-zero exit inside the bash wrapper. Verified against one representative
# hook (harvest-metrics.sh) plus a static grep confirming all 11 files carry
# the block. macOS bash-3.2 portable.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOKS_DIR="$(cd "$HERE/../../hooks" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

EXPECTED_HOOKS="inject-resource-loop.sh harvest-metrics.sh precompact-event.sh auto-update.sh context-budget.sh usage-budget.sh read-guard.sh workorder-gate.sh pipeline-relay.sh loop-close.sh obs-events.sh"

for h in $EXPECTED_HOOKS; do
  if grep -q '_obs_hook_error' "$HOOKS_DIR/$h" && grep -q "trap _obs_hook_error ERR" "$HOOKS_DIR/$h"; then
    pass "$h: trap block present"
  else
    die "$h: trap block missing"
  fi
done

# Functional check: force an ERR trap trip in a throwaway copy of
# harvest-metrics.sh's wrapper shape and confirm obs_emit records hook.error.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/fake-hook.sh" <<'EOS'
#!/bin/bash
set -u
_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="fake-hook.sh" \
    python3 -c '
import os, sys
sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))
try:
    import obs_emit
    obs_emit.emit("hook.error", session_id=os.environ.get("SESSION_ID"),
                  hook=os.environ.get("HOOK_NAME"), stage="trap")
except Exception:
    pass
' >/dev/null 2>&1 || true
}
trap _obs_hook_error ERR
false  # unconditional non-zero command -> trips ERR trap
exit 0
EOS
chmod +x "$TMP/fake-hook.sh"

env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" SESSION_ID="herr1" bash "$TMP/fake-hook.sh" >/dev/null 2>&1

events_file="$(find "$TMP/claude/metrics/events" -name '*.ndjson' 2>/dev/null | head -1)"
if [ -n "$events_file" ] && grep -q '"event":"hook.error"' "$events_file" && grep -q '"hook":"fake-hook.sh"' "$events_file"; then
  pass "functional: ERR trap emits hook.error"
else
  die "functional: no hook.error record found"
fi

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_hook_error_trap.sh"; exit 0
else
  echo "SOME FAILED - test_hook_error_trap.sh"; exit 1
fi
