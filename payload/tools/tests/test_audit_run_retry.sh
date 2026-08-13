#!/bin/bash
# test_audit_run_retry.sh — the infrastructural-vs-model-produced failure
# classification helper in audit_run.sh. Scoped narrowly, matching this
# repo's established convention for this large script (see
# test_audit_run_kind_run.sh's own header note). macOS bash-3.2 portable.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
AUDIT_RUN="$(cd "$HERE/.." && pwd)/dispatch/run.sh"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Extract just the _classify_attempt function (a small, pure, side-effect-free
# helper this task adds) rather than sourcing the whole script.
awk '/^_classify_attempt\(\) \{/,/^\}/' "$AUDIT_RUN" > "$TMP/helper.sh"
if [ ! -s "$TMP/helper.sh" ]; then
  die "could not extract _classify_attempt — check the function exists with this exact name/shape"
else
  pass "extracted _classify_attempt"
fi
source "$TMP/helper.sh"

# _classify_attempt <cli_rc> <findings_file_exists: 0|1> -> prints classification, one of:
#   infrastructural | model-produced | ok

out="$(_classify_attempt 1 0)"
[ "$out" = "infrastructural" ] && pass "nonzero exit + no findings -> infrastructural" \
  || die "expected infrastructural, got: $out"

out="$(_classify_attempt 0 0)"
[ "$out" = "model-produced" ] && pass "zero exit + no findings -> model-produced" \
  || die "expected model-produced, got: $out"

out="$(_classify_attempt 1 1)"
[ "$out" = "model-produced" ] && pass "nonzero exit + findings DID land -> model-produced (never discard real findings)" \
  || die "expected model-produced, got: $out"

out="$(_classify_attempt 0 1)"
[ "$out" = "ok" ] && pass "zero exit + findings present -> ok" \
  || die "expected ok, got: $out"

# rc=124 is the `timeout`/`gtimeout` wrapper's own signal for "the wall-clock
# budget expired". It is a nonzero exit with no findings — the same shape as
# the first case above — but a hung CLI that already used its full timeout
# once is unlikely to succeed on a retry, so it is deliberately routed to
# model-produced (fail once, alert, never retried) rather than
# infrastructural (retry once). See Phase 4 plan design decision 3 and the
# review finding that added this case.
out="$(_classify_attempt 124 0)"
[ "$out" = "model-produced" ] && pass "rc=124 (timeout) + no findings -> model-produced, not retried" \
  || die "expected model-produced, got: $out"

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_audit_run_retry.sh"; exit 0
else
  echo "SOME FAILED - test_audit_run_retry.sh"; exit 1
fi
