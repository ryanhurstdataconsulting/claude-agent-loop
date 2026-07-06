#!/bin/bash
# run_all.sh — runs the full carried + framework test suite in this directory.
#
# Every test_*.py runs via `python3 -m unittest`; every test_*.sh runs via
# bash. Each suite's full output is printed, followed by a per-suite
# PASS/FAIL line, and finally a one-line summary. Exits non-zero if any
# suite failed.
#
# macOS bash-3.2 portable: no mapfile, no associative arrays, no `set -e`
# (one failing suite must not abort the run of the rest).
#
# Run: bash run_all.sh   (from anywhere — it cd's to its own directory first)

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 1

suite_count=0
fail_count=0

run_py_suite() {
  f="$1"
  name="${f%.py}"
  out="$(python3 -m unittest "$name" 2>&1)"
  rc=$?
  printf '%s\n' "$out"
  if [ "$rc" -eq 0 ]; then
    echo "PASS - $f"
  else
    echo "FAIL - $f"
    fail_count=$((fail_count + 1))
  fi
  suite_count=$((suite_count + 1))
}

run_sh_suite() {
  f="$1"
  out="$(bash "$f" 2>&1)"
  rc=$?
  printf '%s\n' "$out"
  if [ "$rc" -eq 0 ]; then
    echo "PASS - $f"
  else
    echo "FAIL - $f"
    fail_count=$((fail_count + 1))
  fi
  suite_count=$((suite_count + 1))
}

for f in test_*.py; do
  [ -f "$f" ] || continue
  echo "=== $f ==="
  run_py_suite "$f"
  echo ""
done

for f in test_*.sh; do
  [ -f "$f" ] || continue
  echo "=== $f ==="
  run_sh_suite "$f"
  echo ""
done

echo "---"
echo "run_all: $suite_count suites, $fail_count failed"
if [ "$fail_count" -eq 0 ]; then
  exit 0
else
  exit 1
fi
