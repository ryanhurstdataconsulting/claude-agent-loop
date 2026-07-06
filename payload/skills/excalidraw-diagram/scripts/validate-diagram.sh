#!/usr/bin/env bash
# validate-diagram.sh — sanity check on a project .excalidraw file.
# Usage: ./validate-diagram.sh path/to/diagram.excalidraw

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <diagram.excalidraw>" >&2
  exit 64
fi

FILE="$1"

if [[ ! -f "$FILE" ]]; then
  echo "error: file not found: $FILE" >&2
  exit 66
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "error: jq is required (brew install jq)" >&2
  exit 69
fi

if ! jq empty "$FILE" 2>/dev/null; then
  echo "FAIL: not valid JSON: $FILE" >&2
  exit 1
fi

TYPE=$(jq -r '.type // empty' "$FILE")
[[ "$TYPE" == "excalidraw" ]] || { echo "FAIL: top-level type must be 'excalidraw' (got '$TYPE')"; exit 1; }

ELEMENT_COUNT=$(jq '.elements | length' "$FILE")
[[ "$ELEMENT_COUNT" -gt 0 ]] || { echo "FAIL: diagram has zero elements"; exit 1; }

HAS_TITLE=$(jq '[.elements[] | select(.id == "title")] | length' "$FILE")
[[ "$HAS_TITLE" -ge 1 ]] || { echo "FAIL: missing required title node (id=='title')"; exit 1; }

UNLABELED_ARROWS=$(jq '[.elements[] | select(.type == "arrow") | select(.label == null or .label.text == "" or .label.text == null)] | length' "$FILE")
[[ "$UNLABELED_ARROWS" -eq 0 ]] || { echo "FAIL: $UNLABELED_ARROWS arrow(s) without labels — every arrow must say what data flows"; exit 1; }

echo "PASS: $FILE — $ELEMENT_COUNT elements, title present, all arrows labeled"
