#!/bin/bash
# build_watch.sh — no-Monitor fallback log watcher: block until a build log
# emits its FIRST success or failure line, print one line, and exit. No
# manual re-arm — the script self-clears by exiting on the first match.
#
# Usage:
#   bash build_watch.sh <logfile> <success-regex> <fail-regex>
#
# Prints exactly one of:
#   BUILD OK: <matched log line>        (exit 0)
#   BUILD FAILED: <matched log line>    (exit 1)
# and, if BUILD_WATCH_TIMEOUT_SECS elapses with no match:
#   BUILD WATCH TIMEOUT: no match within <n>s   (exit 2)
#
# Harness-native alternative — if the calling agent HAS the Monitor tool,
# prefer it over this script: point Monitor at an until-loop such as
#   until grep -qE '<success-regex>|<fail-regex>' <logfile>; do sleep 2; done
# and Monitor delivers exactly one notification when the loop exits, without
# an agent-side polling loop to re-arm. This script is the dependency-free
# fallback for agents/harnesses that do NOT have Monitor (or a plain CI/cron
# context with no harness at all). See
# registry/guides/background-build-watch.md for the full relationship: this
# is the thin fallback; Monitor is the preferred backbone when available.
#
# Config via environment (all optional):
#   BUILD_WATCH_TIMEOUT_SECS   max seconds to wait before giving up (default 120)
#   BUILD_WATCH_POLL_INTERVAL  seconds between polls (default 0.2)
#
# Portable to macOS's default bash 3.2 — no `declare -A`, no `mapfile`, no
# reliance on GNU-only `tail -F` or a `timeout` binary.

set -u

LOGFILE="${1:-}"
OK_REGEX="${2:-}"
FAIL_REGEX="${3:-}"

if [ -z "$LOGFILE" ] || [ -z "$OK_REGEX" ] || [ -z "$FAIL_REGEX" ]; then
  echo "usage: bash build_watch.sh <logfile> <success-regex> <fail-regex>" >&2
  exit 2
fi

TIMEOUT_SECS="${BUILD_WATCH_TIMEOUT_SECS:-120}"
POLL_INTERVAL="${BUILD_WATCH_POLL_INTERVAL:-0.2}"

START_EPOCH="$(date +%s)"
OFFSET=0

while :; do
  if [ -f "$LOGFILE" ]; then
    SIZE="$(wc -c < "$LOGFILE" 2>/dev/null | tr -d ' ')"
    SIZE="${SIZE:-0}"

    if [ "$SIZE" -gt "$OFFSET" ]; then
      NEW_CONTENT="$(tail -c "+$((OFFSET + 1))" "$LOGFILE")"
      OFFSET="$SIZE"

      while IFS= read -r LINE; do
        if [[ "$LINE" =~ $FAIL_REGEX ]]; then
          echo "BUILD FAILED: $LINE"
          exit 1
        fi
        if [[ "$LINE" =~ $OK_REGEX ]]; then
          echo "BUILD OK: $LINE"
          exit 0
        fi
      done <<< "$NEW_CONTENT"
    fi
  fi

  NOW_EPOCH="$(date +%s)"
  ELAPSED=$((NOW_EPOCH - START_EPOCH))
  if [ "$ELAPSED" -ge "$TIMEOUT_SECS" ]; then
    echo "BUILD WATCH TIMEOUT: no match within ${TIMEOUT_SECS}s" >&2
    exit 2
  fi

  sleep "$POLL_INTERVAL"
done
