#!/bin/bash
# Tests for build_watch.sh — no external test framework, just temp-file
# fixtures + assertions. macOS bash-3.2 portable — no `declare -A`.
#
# Run: bash ~/.claude/tools/tests/test_build_watch.sh

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../build_watch.sh"

FAILURES=0

assert_contains() {
  # $1 = haystack, $2 = needle, $3 = test label
  if printf '%s' "$1" | grep -qF "$2"; then
    echo "ok - $3"
  else
    echo "FAIL - $3 (expected to find: $2)"
    FAILURES=$((FAILURES + 1))
  fi
}

assert_eq() {
  # $1 = actual, $2 = expected, $3 = label
  if [ "$1" = "$2" ]; then
    echo "ok - $3"
  else
    echo "FAIL - $3 (expected [$2], got [$1])"
    FAILURES=$((FAILURES + 1))
  fi
}

if [ ! -f "$SCRIPT" ]; then
  echo "FAIL - script not found at $SCRIPT (RED: build it first)"
  exit 1
fi

# --- Case 1: success line pre-written before the watch starts ---------------
OK_LOG="$(mktemp -t build_watch_ok)"
printf 'compiling...\nBUILD SUCCESSFUL in 3s\n' > "$OK_LOG"

OK_OUTPUT="$(BUILD_WATCH_TIMEOUT_SECS=5 bash "$SCRIPT" "$OK_LOG" 'BUILD SUCCESSFUL' 'BUILD FAILED' 2>&1)"
OK_EXIT=$?

assert_contains "$OK_OUTPUT" "BUILD OK" "success case: prints BUILD OK"
assert_eq "$OK_EXIT" "0" "success case: exits 0"

rm -f "$OK_LOG"

# --- Case 2: fail line pre-written before the watch starts -------------------
FAIL_LOG="$(mktemp -t build_watch_fail)"
printf 'compiling...\nBUILD FAILED: error in module x\n' > "$FAIL_LOG"

FAIL_OUTPUT="$(BUILD_WATCH_TIMEOUT_SECS=5 bash "$SCRIPT" "$FAIL_LOG" 'BUILD SUCCESSFUL' 'BUILD FAILED' 2>&1)"
FAIL_EXIT=$?

assert_contains "$FAIL_OUTPUT" "BUILD FAILED" "fail case: prints BUILD FAILED"
assert_eq "$FAIL_EXIT" "1" "fail case: exits 1"

rm -f "$FAIL_LOG"

# --- Case 3: success line appended in the background after watch starts -----
BG_LOG="$(mktemp -t build_watch_bg)"
: > "$BG_LOG"
( sleep 0.3; printf 'BUILD SUCCESSFUL in 1s\n' >> "$BG_LOG" ) &
BG_WRITER_PID=$!

BG_OUTPUT="$(BUILD_WATCH_TIMEOUT_SECS=5 bash "$SCRIPT" "$BG_LOG" 'BUILD SUCCESSFUL' 'BUILD FAILED' 2>&1)"
BG_EXIT=$?

assert_contains "$BG_OUTPUT" "BUILD OK" "background-append case: prints BUILD OK"
assert_eq "$BG_EXIT" "0" "background-append case: exits 0"

wait "$BG_WRITER_PID" 2>/dev/null
rm -f "$BG_LOG"

echo "---"
if [ "$FAILURES" -eq 0 ]; then
  echo "test_build_watch: ALL OK"
  exit 0
else
  echo "test_build_watch: $FAILURES failure(s)"
  exit 1
fi
