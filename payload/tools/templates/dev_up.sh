#!/bin/bash
# dev_up.sh — TEMPLATE: bring this project's dev stack up, then block on a
# health gate before returning control to the caller.
#
# Copy this file into your project root (keep the filename `dev_up.sh` — see
# ~/.claude/tools/templates/README.md for the dev-server-orchestration
# convention this implements), then fill in every `# CONFIGURE:` block below.
#
# Contract: this script MUST NOT exit 0 until the health gate has actually
# observed an HTTP 200 (or it has timed out, in which case it reports failure
# and exits non-zero). "The process launched" is not sufficient — a restart
# that never came up must not look like success. This one property is the
# whole point of the convention: it stops a stale-server-vs-real-code-bug
# false alarm from ever getting started.
#
# Usage: ./dev_up.sh   (run from the project root)
#
# Portable to macOS's default bash 3.2 — no `declare -A`, no `mapfile`.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# CONFIGURE: where this project's dev-server PID and combined log are
# tracked. dev_down.sh must read the same PIDFILE path.
PIDFILE="$HERE/.dev_up.pid"
LOGFILE="$HERE/.dev_up.log"

# CONFIGURE: the health-gate URL — pick an endpoint that only returns 200
# once the stack is actually ready to serve real traffic, not merely "the
# port is open" (e.g. a `/health` route that checks its own DB connection).
HEALTH_URL="http://localhost:8000/health"

# CONFIGURE: how long to wait for the health gate before giving up, and how
# often to poll it. Override per-run with env vars if a slower stack needs it.
HEALTH_TIMEOUT_SECS="${HEALTH_TIMEOUT_SECS:-30}"
HEALTH_POLL_INTERVAL="${HEALTH_POLL_INTERVAL:-1}"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "dev_up: already running (pid $(cat "$PIDFILE")) — skipping start, re-checking health gate"
else
  echo "dev_up: starting dev stack..."

  # CONFIGURE: the actual start command(s) for this project's stack. Examples:
  #   (cd api && .venv/bin/uvicorn app:app --reload --port 8000 >>"$LOGFILE" 2>&1 &)
  #   (cd web && npm run dev >>"$LOGFILE" 2>&1 &)
  #   docker compose up -d
  # Record the primary (or last-launched) process's PID so dev_down.sh can
  # stop it cleanly. For a multi-process stack, prefer one supervising
  # process (docker compose, a Procfile runner) over tracking N PIDs by hand.
  nohup true >>"$LOGFILE" 2>&1 &
  echo $! > "$PIDFILE"
fi

echo "dev_up: waiting on health gate ($HEALTH_URL, up to ${HEALTH_TIMEOUT_SECS}s)..."

ELAPSED=0
while :; do
  STATUS="$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || echo 000)"
  if [ "$STATUS" = "200" ]; then
    echo "dev_up: READY — $HEALTH_URL returned 200 after ${ELAPSED}s"
    exit 0
  fi

  if [ "$ELAPSED" -ge "$HEALTH_TIMEOUT_SECS" ]; then
    echo "dev_up: FAILED — no 200 from $HEALTH_URL after ${HEALTH_TIMEOUT_SECS}s (last status: $STATUS)" >&2
    echo "dev_up: check $LOGFILE for details" >&2
    exit 1
  fi

  sleep "$HEALTH_POLL_INTERVAL"
  ELAPSED=$((ELAPSED + HEALTH_POLL_INTERVAL))
done
