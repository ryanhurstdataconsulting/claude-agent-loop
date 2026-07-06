#!/bin/bash
# Tests for the dev-server-orchestration templates. Templates are inert
# scaffolds (CONFIGURE placeholders, no real server to bring up) — this test
# only checks that the three files exist and that the two .sh templates are
# syntactically valid bash, per the task contract. macOS bash-3.2 portable.
#
# Run: bash ~/.claude/tools/tests/test_dev_templates.sh

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES_DIR="$HERE/../templates"

FAILURES=0

assert_file_exists() {
  # $1 = path, $2 = label
  if [ -f "$1" ]; then
    echo "ok - $2"
  else
    echo "FAIL - $2 (missing: $1)"
    FAILURES=$((FAILURES + 1))
  fi
}

assert_bash_syntax_ok() {
  # $1 = path, $2 = label
  local err_file
  err_file="$(mktemp -t dev_templates_syntax_err)"
  if bash -n "$1" 2>"$err_file"; then
    echo "ok - $2"
  else
    echo "FAIL - $2 ($(cat "$err_file"))"
    FAILURES=$((FAILURES + 1))
  fi
  rm -f "$err_file"
}

assert_file_exists "$TEMPLATES_DIR/dev_up.sh" "dev_up.sh template exists"
assert_file_exists "$TEMPLATES_DIR/dev_down.sh" "dev_down.sh template exists"
assert_file_exists "$TEMPLATES_DIR/README.md" "README.md convention doc exists"

assert_bash_syntax_ok "$TEMPLATES_DIR/dev_up.sh" "dev_up.sh is syntactically valid bash"
assert_bash_syntax_ok "$TEMPLATES_DIR/dev_down.sh" "dev_down.sh is syntactically valid bash"

echo "---"
if [ "$FAILURES" -eq 0 ]; then
  echo "test_dev_templates: ALL OK"
  exit 0
else
  echo "test_dev_templates: $FAILURES failure(s)"
  exit 1
fi
