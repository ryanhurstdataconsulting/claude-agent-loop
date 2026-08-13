#!/usr/bin/env python3
"""Shared schema, connection, and stamp helpers for the blackboard tools
(bb_write.py / bb_read.py / bb_gc.py) — the only sanctioned access path to
~/.claude/state/blackboard.db (agent-loop-v2 design spec, Phase 3).

`phase` values are expected to be one of the pipeline stage names from the
loop's own architecture (MATCH, PLAN, ANNOUNCE, ROUTE, EXECUTE, SCORE,
MERGE, LEARN), but this is guidance, not an enforced constraint — a future
phase can extend the vocabulary without a schema migration.
"""
import datetime
import hashlib
import json
import pathlib
import sqlite3

STAMPED_TABLES = ("shared_state", "events", "consensus_state", "workflow_state")
ALL_TABLES = STAMPED_TABLES + ("artifacts",)

_STAMPED_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    agent_id TEXT,
    ts TEXT NOT NULL,
    payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{table}_task ON {table}(task_id);
"""

_ARTIFACTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    agent_id TEXT,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_task ON artifacts(task_id);
"""


def default_db_path():
    return pathlib.Path.home() / ".claude" / "state" / "blackboard.db"


def connect(db_path):
    """Open (creating if needed) the blackboard DB in WAL mode with the full
    schema applied. Safe to call from bb_write/bb_read/bb_gc alike —
    CREATE TABLE IF NOT EXISTS makes this idempotent."""
    db_path = pathlib.Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    for table in STAMPED_TABLES:
        conn.executescript(_STAMPED_SCHEMA.format(table=table))
    conn.executescript(_ARTIFACTS_SCHEMA)
    conn.commit()
    return conn


def now_ts():
    """UTC, Z-suffixed, second precision — the plan_task.py convention
    (obs_emit.py uses a separate .isoformat() convention elsewhere in this
    codebase; blackboard rows are most often written next to plan_task.py
    calls, so this module follows that one)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def payload_sha256(payload_obj):
    """sha256 hex of the canonical (sort_keys=True) JSON encoding of
    payload_obj — same canonicalization metrics_to_otlp.py's
    _content_hash() uses, so the same logical payload always hashes the
    same way regardless of key order."""
    return hashlib.sha256(
        json.dumps(payload_obj, sort_keys=True).encode()
    ).hexdigest()


def insert_stamped(conn, table, task_id, phase, agent_id, payload_obj):
    """Insert one stamped row into `table` (must be in STAMPED_TABLES).
    `table` is interpolated into the SQL string below, but only ever after
    this whitelist check — sqlite3's parameter binding cannot bind
    identifiers, only values, so a fixed-tuple whitelist checked first is
    the standard, correct mitigation here, not raw string interpolation of
    caller input."""
    if table not in STAMPED_TABLES:
        raise ValueError("insert_stamped only supports %r, not %r" % (STAMPED_TABLES, table))
    ts = now_ts()
    payload_json = json.dumps(payload_obj, sort_keys=True)
    digest = hashlib.sha256(payload_json.encode()).hexdigest()
    cur = conn.execute(
        "INSERT INTO %s (task_id, phase, agent_id, ts, payload, payload_sha256) "
        "VALUES (?, ?, ?, ?, ?, ?)" % table,
        (task_id, phase, agent_id, ts, payload_json, digest),
    )
    conn.commit()
    return cur.lastrowid


def insert_artifact(conn, artifact_id, task_id, phase, agent_id, path, sha256_hex):
    """Upsert one artifacts row keyed by artifact_id — a lookup map
    (id -> path + sha256), not an append-only log like the stamped tables."""
    ts = now_ts()
    conn.execute(
        "INSERT OR REPLACE INTO artifacts "
        "(artifact_id, task_id, phase, agent_id, path, sha256, ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (artifact_id, task_id, phase, agent_id, path, sha256_hex, ts),
    )
    conn.commit()
    return artifact_id
