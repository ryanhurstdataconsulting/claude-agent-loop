#!/bin/bash
# dev_down.sh — TEMPLATE: stop this project's dev stack cleanly. Idempotent —
# safe to run when nothing is up; it must not error just because there was
# nothing to stop.
#
# Copy this file into your project root next to dev_up.sh (see
# ~/.claude/tools/templates/README.md for the convention). Fill in every
# `# CONFIGURE:` block below to match how dev_up.sh started the stack.
#
# Usage: ./dev_down.sh   (run from the project root)
#
# Portable to macOS's default bash 3.2 — no `declare -A`, no `mapfile`.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# CONFIGURE: must match the PIDFILE path used in dev_up.sh.
PIDFILE="$HERE/.dev_up.pid"

# CONFIGURE: the port this stack binds, used as a fallback for when the
# pidfile is missing or stale (e.g. a crash left an orphaned process behind).
# Leave empty ("") to skip the port-based fallback entirely.
FALLBACK_PORT="8000"

STOPPED_ANY=0

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "dev_down: stopping pid $PID"
    kill "$PID" 2>/dev/null
    STOPPED_ANY=1
  else
    echo "dev_down: pidfile present but process $PID is not running — stale, cleaning up"
  fi
  rm -f "$PIDFILE"
else
  echo "dev_down: no pidfile at $PIDFILE — nothing tracked"
fi

if [ -n "$FALLBACK_PORT" ] && command -v lsof >/dev/null 2>&1; then
  PORT_PIDS="$(lsof -ti tcp:"$FALLBACK_PORT" 2>/dev/null || true)"
  if [ -n "$PORT_PIDS" ]; then
    echo "dev_down: killing orphaned process(es) still holding port $FALLBACK_PORT: $PORT_PIDS"
    echo "$PORT_PIDS" | xargs kill 2>/dev/null || true
    STOPPED_ANY=1
  fi
fi

if [ "$STOPPED_ANY" -eq 1 ]; then
  echo "dev_down: stack stopped"
else
  echo "dev_down: nothing was running — no-op (idempotent)"
fi

exit 0
