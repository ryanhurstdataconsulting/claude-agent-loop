#!/bin/bash
# test_audit_run_kind_run.sh — kind:"run" (audit) emission helper in
# audit_run.sh. Scoped narrowly to the new _emit_run_record helper's
# behavior, not a full audit_run.sh integration test (out of scope for
# this plan — see Phase 2 plan Task 3). macOS bash-3.2 portable.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
AUDIT_RUN="$(cd "$HERE/.." && pwd)/audit_run.sh"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Source only the helper function definitions, not the whole script (which
# expects real CLI args and would error/exit on a bare source). Extract
# _emit_run_record's definition via sed between its opening and the next
# top-level "}" at column 1, write it to a standalone file, then source that.
awk '/^_emit_run_record\(\) \{/,/^\}/' "$AUDIT_RUN" > "$TMP/helper.sh"
if [ ! -s "$TMP/helper.sh" ]; then
  die "could not extract _emit_run_record from audit_run.sh — check the function name/shape matches what this test expects"
else
  pass "extracted _emit_run_record definition"
fi

# shellcheck source=/dev/null
source "$TMP/helper.sh"

# _emit_run_record <verdict> <package-key> <metrics-dir> [cli-rc]
CLAUDE_DIR="$TMP/claude" METRICS_DIR="$TMP/claude/metrics" \
  _emit_run_record "ok" "test-package" "$TMP/claude/metrics" "0"
shard="$(find "$TMP/claude/metrics" -maxdepth 1 -name '*.jsonl' | head -1)"
if [ -n "$shard" ] && grep -q '"kind":"run"' "$shard" && grep -q '"run_kind":"audit"' "$shard" && grep -q '"outcome":"success"' "$shard"; then
  pass "ok verdict -> outcome:success recorded"
else
  die "ok verdict did not produce expected kind:run record (shard: $shard)"
fi

CLAUDE_DIR="$TMP/claude" METRICS_DIR="$TMP/claude/metrics" \
  _emit_run_record "failed" "test-package-2" "$TMP/claude/metrics" "124"
if grep -q '"outcome":"failure"' "$shard" && grep -q '"stop_reason":"timeout"' "$shard"; then
  pass "failed verdict + rc=124 -> outcome:failure, stop_reason:timeout"
else
  die "timeout case not recorded correctly"
fi

CLAUDE_DIR="$TMP/claude" METRICS_DIR="$TMP/claude/metrics" \
  _emit_run_record "failed" "test-package-3" "$TMP/claude/metrics" "1"
if grep -q '"stop_reason":"error"' "$shard"; then
  pass "failed verdict + rc=1 -> stop_reason:error"
else
  die "non-timeout failure not recorded correctly"
fi

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_audit_run_kind_run.sh"; exit 0
else
  echo "SOME FAILED - test_audit_run_kind_run.sh"; exit 1
fi
