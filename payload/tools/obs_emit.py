#!/usr/bin/env python3
"""obs_emit.py — the obs.v1 structured event log (Phase 1, stdlib only).

One function, `emit()`, appends one JSON line to
~/.claude/metrics/events/YYYY-MM-DD.ndjson per call. Copies harvest_metrics.py's
atomic-append primitive (os.open(O_WRONLY|O_APPEND|O_CREAT) + a single
os.write) onto a daily file instead of a monthly shard.

trace_id/span_id are sha256-derived, deterministic functions of caller-visible
arguments only — no uuid4, no clock, no counter — matching the framework's
existing plan_id() convention in plan_task.py. See trace_id_for()/span_id_for().

Never raises into the caller: the whole body of emit() runs inside one bare
try/except. A broken environment (unwritable dir, bad CLAUDE_DIR) degrades to
a silent no-op, never a crash.
"""
import datetime
import hashlib
import json
import os
import pathlib

# obs.v1 event enum, for reference — emit() does not enforce membership (a
# caller with a typo'd event name must never crash; better to record the typo
# than to raise).
EVENTS = (
    "session.start", "prompt.submit", "gate.decision", "tool.pre",
    "tool.post", "skill.invoked", "subagent.stop", "compaction",
    "turn.stop", "session.end", "run.end", "hook.error", "heartbeat",
)


def _events_dir():
    claude_dir = os.environ.get("CLAUDE_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    return os.path.join(claude_dir, "metrics", "events")


def _root_task_id(session_id, agent_id, plan_id):
    return session_id or agent_id or plan_id or "unknown"


def _component_key(event, agent_id, part_id, attrs, ts):
    explicit = attrs.pop("component_key", None)
    if explicit:
        return str(explicit)
    return "%s|%s|%s|%s" % (event, agent_id or "", part_id or "", ts)


def trace_id_for(root_task_id):
    """Deterministic trace_id: sha256("run:" + root_task_id)[:32 hex]."""
    digest = hashlib.sha256(("run:" + str(root_task_id)).encode("utf-8"))
    return digest.hexdigest()[:32]


def span_id_for(root_task_id, component_key):
    """Deterministic span_id: sha256(root_task_id + ":" + component_key)[:16 hex]."""
    digest = hashlib.sha256(
        ("%s:%s" % (root_task_id, component_key)).encode("utf-8"))
    return digest.hexdigest()[:16]


def _append_record(events_dir, day, record):
    pathlib.Path(events_dir).mkdir(parents=True, exist_ok=True)
    shard = os.path.join(events_dir, "%s.ndjson" % day)
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    data = line.encode("utf-8")
    # Single os.write(2) to an O_APPEND fd — see harvest_metrics.py's
    # _append_record for why this never tears a concurrent writer's line.
    fd = os.open(shard, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def emit(event, session_id=None, agent_id=None, plan_id=None, part_id=None,
          project=None, **attrs):
    """Append one obs.v1 record. Never raises; always returns None."""
    try:
        attrs = dict(attrs)
        parent_span_id = attrs.pop("parent_span_id", None)
        root_task_id = _root_task_id(session_id, agent_id, plan_id)
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        component_key = _component_key(event, agent_id, part_id, attrs, ts)
        record = {
            "schema": "obs.v1",
            "ts": ts,
            "event": event,
            "session_id": session_id,
            "agent_id": agent_id,
            "trace_id": trace_id_for(root_task_id),
            "span_id": span_id_for(root_task_id, component_key),
            "parent_span_id": parent_span_id,
            "plan_id": plan_id,
            "part_id": part_id,
            "project": project,
            "attrs": attrs,
        }
        _append_record(_events_dir(), ts[:10], record)
    except Exception:
        pass
    return None
