#!/bin/bash
# run.sh — runs payload/observability/tests/ if the obs-venv dependency is
# available; otherwise reports a clear, loud SKIP rather than silently
# passing zero tests. Run: bash run.sh (from anywhere — cd's to its own dir).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 1

VENV_PY="$HOME/.claude-agent-loop/obs-venv/bin/python3"
if [ -x "$VENV_PY" ]; then
  PY="$VENV_PY"
elif python3 -c "import opentelemetry.sdk" >/dev/null 2>&1; then
  PY="python3"
else
  echo "SKIP - opentelemetry-sdk not available (obs-venv not set up yet; see payload/observability/README.md)"
  exit 0
fi

out="$("$PY" -m unittest test_obs_ship -v 2>&1)"
rc=$?
printf '%s\n' "$out"
if [ "$rc" -eq 0 ]; then
  echo "PASS - test_obs_ship.py"
else
  echo "FAIL - test_obs_ship.py"
fi
exit "$rc"
