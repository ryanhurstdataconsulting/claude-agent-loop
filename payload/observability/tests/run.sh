#!/bin/bash
# run.sh — runs payload/observability/tests/test_obs_ship.py AND
# payload/tools/tests/test_metrics_to_otlp.py's OTel-gated classes under the
# SAME resolved interpreter, if the obs-venv dependency is available;
# otherwise reports a clear, loud SKIP rather than silently passing zero
# tests. Both modules share the same two pip dependencies (opentelemetry-sdk
# + opentelemetry-exporter-otlp-proto-http), so one venv covers both. Run:
# bash run.sh (from anywhere — cd's to its own dir).
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

# test_metrics_to_otlp.py lives in payload/tools/tests/, not here — it has
# its own OTel-gated classes (see its module docstring) that need the SAME
# venv interpreter this file already resolved into $PY. run_all.sh (bare
# python3, no venv-awareness) only exercises this module's OTel-free pure
# unit tests, skipping the OTel-gated classes; running it here too, under
# $PY, is what actually exercises those classes instead of skipping them.
# Subshell so the `cd` doesn't leak into anything after this file returns.
out2="$(cd "$HERE/../../tools/tests" && "$PY" -m unittest test_metrics_to_otlp -v 2>&1)"
rc2=$?
printf '%s\n' "$out2"
if [ "$rc2" -eq 0 ]; then
  echo "PASS - test_metrics_to_otlp.py"
else
  echo "FAIL - test_metrics_to_otlp.py"
fi

if [ "$rc" -eq 0 ] && [ "$rc2" -eq 0 ]; then
  exit 0
fi
exit 1
