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
    with open(shard, "a") as f:   # single append — atomic under PIPE_BUF
        f.write(line)
except Exception as exc:
    sys.stderr.write("precompact-event: %s\n" % exc)

os._exit(0)
PY

exit 0
