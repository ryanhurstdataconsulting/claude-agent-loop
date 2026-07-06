#!/bin/bash
# PreCompact hook — records one compaction event in the current month shard.
#
# ADDITIVE-ONLY, exactly like inject-resource-loop.sh: this hook ALWAYS exits 0.
# The hook JSON arrives on stdin (session_id, hook_event_name); we parse it
# defensively in python and tolerate absent or malformed input.
set -u

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
METRICS_DIR="${METRICS_DIR:-$CLAUDE_DIR/metrics}"
INPUT="$(cat 2>/dev/null || true)"

HOOK_JSON="$INPUT" METRICS_DIR="$METRICS_DIR" python3 >/dev/null <<'PY' || true
import datetime
import json
import os
import sys

raw = os.environ.get("HOOK_JSON", "")
try:
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}

session_id = data.get("session_id")
now = datetime.datetime.now(datetime.timezone.utc)
record = {
    "schema": 1,
    "kind": "compaction",
    "session_id": session_id,
    "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
}
metrics_dir = os.environ.get("METRICS_DIR")
try:
    os.makedirs(metrics_dir, exist_ok=True)
    shard = os.path.join(metrics_dir, now.strftime("%Y-%m") + ".jsonl")
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    # One os.write(2) of the whole line to an O_APPEND fd. A single write to an
    # O_APPEND regular file on a local filesystem does not interleave with other
    # single-write appenders, so concurrent hooks never tear a record. (PIPE_BUF
    # governs atomic writes to pipes, not this property of regular files.)
    fd = os.open(shard, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
except Exception as exc:
    sys.stderr.write("precompact-event: %s\n" % exc)

os._exit(0)
PY

exit 0
