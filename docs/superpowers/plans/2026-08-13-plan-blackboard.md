# Blackboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Stand up `~/.claude/state/blackboard.db` — a single-file, WAL-mode
SQLite store with five tables (`shared_state`, `events`, `consensus_state`,
`workflow_state`, `artifacts`) — and the three sanctioned tools
(`bb_write.py`, `bb_read.py`, `bb_gc.py`) that are the only path in or out of
it, per the spec's Phase 3.

**Architecture:** A shared module (`bb_common.py`) owns the schema, the WAL
connection helper, and the `(task_id, phase, agent_id, ts, sha256(payload))`
stamp the spec requires. `bb_write.py`/`bb_read.py` are thin CLI wrappers
over it; `bb_gc.py` applies the spec's stated retention windows. No daemon,
no server process — every tool opens the file, does its work, and closes it,
exactly like `plan_task.py` already does with its own JSON files.

**Tech Stack:** Python 3 stdlib only — `sqlite3`, `hashlib`, `json`,
`datetime`, `argparse`, `pathlib`. No new dependency: every existing tool in
`payload/tools/` is stdlib-only by explicit design (see Grounding below),
and `sqlite3` ships with the Python stdlib.

**Spec:** `docs/superpowers/specs/2026-08-06-agent-loop-v2-design.md`
(Phase 3 — "Blackboard")

## Grounding (read before Task 1)

A pre-planning sweep of the actual codebase (not just the spec) found four
things worth recording before writing code:

1. **The spec's own phrase "mirroring the metrics harvester's discipline" is
   imprecise.** `harvest_metrics.py`'s real record shape has no `phase` or
   `agent_id` field and never stamps `sha256(payload)` — that hashing
   pattern actually lives in `obs_emit.py` (`trace_id_for()`/`span_id_for()`,
   sha256 of a task/component key) and `metrics_to_otlp.py`
   (`_content_hash()` = `sha256(json.dumps(record, sort_keys=True))`, used
   as a dedup cursor, never stored). This plan takes the spec's literal
   stamp tuple as the requirement and builds it fresh — canonical-JSON
   payload hashing from `metrics_to_otlp.py`'s precedent — rather than
   copying code that doesn't actually do what the spec describes.
2. **Timestamp format is a genuine two-way split in this codebase.**
   `plan_task.py` generates `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`
   (`Z`-suffixed, no microseconds); `obs_emit.py` uses `.isoformat()`
   (`+00:00` offset, microseconds). This plan picks the `plan_task.py`
   convention, since blackboard rows are expected to be written most often
   from work already flowing through `plan_task.py`'s pipeline (EXECUTE
   steps of a plan).
3. **No SQLite usage exists anywhere in this codebase today.** This phase is
   genuinely greenfield — there is no WAL setup, connection helper, or
   migration pattern to follow. `bb_common.py`'s `connect()` is written from
   scratch, informed only by the atomic-write and idempotent-`CREATE TABLE
   IF NOT EXISTS` conventions used elsewhere.
4. **`~/.claude/state/` does not exist yet.** The one existing "state"
   convention in this codebase is `~/.claude/metrics/state/` (cursor files,
   the old work-order directory). The spec's chosen path,
   `~/.claude/state/blackboard.db`, is a deliberate new top-level directory,
   not a typo for the metrics one — blackboard is explicitly *not* part of
   the metrics domain (spec: "The `metrics/*.jsonl` ledger is untouched —
   blackboard is working state, metrics stays the permanent ledger"), so a
   separate top-level dir is the right call. `connect()` creates it via
   `mkdir(parents=True, exist_ok=True)`.
5. **`bb_gc.py`'s "existing cron surface"** is three static, hand-installed
   launchd plists under `payload/launchd/` — there is no generic job
   dispatcher yet (that's what the spec's own Phase 5, not built, proposes).
   This plan adds a fourth plist in the same shape, installed the same
   manual way the other three are (there is no installer script anywhere in
   this repo to hook into).

## Design decisions locked in by this plan (not fully specified by the spec)

- **`artifacts` gets its own shape**, not the common stamped-row shape the
  other four tables share. The spec describes it differently in kind — "id
  → path + sha256 for large payloads referenced elsewhere" is a lookup map
  (write-then-look-up-by-id), while the other four are append-only logs
  (write-then-scan-by-task_id). `artifacts.artifact_id` is a `PRIMARY KEY`
  with `INSERT OR REPLACE` semantics; the other four use `INTEGER PRIMARY
  KEY AUTOINCREMENT` and are append-only.
- **`payload` is a single JSON-encoded TEXT column** on each of the four
  stamped tables, not bespoke per-table columns — this is what "every write
  is stamped `(task_id, phase, agent_id, ts, sha256(payload))`" literally
  describes (one common stamp, one payload), and it means `bb_write.py`
  needs exactly one code path for all four, not four bespoke ones.
- **`bb_gc.py` trims exactly the three tables the spec names retention
  policy for** (`shared_state`, `artifacts`: 30 days; `events`: 90 days) and
  leaves `consensus_state` and `workflow_state` alone — the spec gives no
  retention window for either, and both are audit/resume state (a vote
  history that Phase 6 explicitly wants "queryable"; a checkpoint a plan may
  still resume from) that should not silently expire. This is a deliberate
  reading of an intentional omission, not an oversight — Task 3 documents
  it in the module docstring so a future reader doesn't "fix" it into
  trimming everything.
- **`phase` values are the pipeline-stage names from the spec's own
  architecture diagram** (`MATCH`, `PLAN`, `ANNOUNCE`, `ROUTE`, `EXECUTE`,
  `SCORE`, `MERGE`, `LEARN`) — free text at the SQL layer (no CHECK
  constraint), so a future phase can extend the vocabulary without a
  migration; `bb_common.py`'s docstring names the current set as guidance,
  not enforcement.
- **Dynamic table names in SQL strings are whitelist-validated, not
  user-controlled.** `bb_common.insert_stamped()` and `bb_gc.gc()` both
  interpolate a table name into an SQL string via `%s` — sqlite3's
  parameter binding cannot bind identifiers (only values), so whitelisting
  against a fixed tuple/dict (`STAMPED_TABLES`, `RETENTION_DAYS`) checked
  *before* the interpolation is the standard, correct mitigation here, not
  an oversight. Task 1 and Task 4's code comments say so explicitly.

## Global Constraints

- Stdlib only — no new pip/venv dependency for any of the three tools.
- Every tool takes an explicit `--db` override (default
  `~/.claude/state/blackboard.db` via `bb_common.default_db_path()`) so
  tests never touch the real file — same discipline `plan_task.py`'s
  `--state-dir` and `lint_registry.py`'s positional root already follow.
- Exit codes: `0` success, `2` usage error (bad table, missing companion
  arg, invalid JSON) — matching `plan_task.py`'s convention, not
  `lint_registry.py`'s `0`/`1` lint-tool convention (these are CLIs that DO
  things, not linters that report findings).
- `payload` is canonicalized via `json.dumps(obj, sort_keys=True)` before
  hashing and storage, so the same logical payload always hashes the same
  way regardless of key order.
- New tools each need one `payload/registry/REGISTRY.md` row, one
  `payload/registry/guides/<name>.md`, and one `payload/MANIFEST` line —
  `lint_registry.py` (Phase 2, already landed) enforces the first two are
  never added without each other.

---

### Task 1: `bb_common.py` — schema, connection, and stamp helpers

**Files:**
- Create: `payload/tools/bb_common.py`
- Test: `payload/tools/tests/test_bb_common.py`

**Interfaces:**
- Produces:
  - `ALL_TABLES: tuple[str]` — all 5 table names.
  - `STAMPED_TABLES: tuple[str]` — the 4 that share the common stamp shape
    (excludes `artifacts`).
  - `default_db_path() -> pathlib.Path`
  - `connect(db_path) -> sqlite3.Connection` — WAL mode, full schema applied,
    parent dir created.
  - `now_ts() -> str` — `%Y-%m-%dT%H:%M:%SZ` UTC.
  - `payload_sha256(payload_obj) -> str` — sha256 hex of the canonical JSON
    encoding.
  - `insert_stamped(conn, table, task_id, phase, agent_id, payload_obj) ->
    int` — `agent_id` may be `None`; returns the new row's `id`. Raises
    `ValueError` if `table not in STAMPED_TABLES`.
  - `insert_artifact(conn, artifact_id, task_id, phase, agent_id, path,
    sha256_hex) -> str` — `INSERT OR REPLACE`, returns `artifact_id`.
- Consumes: nothing — this is the foundation module every other task in
  this plan imports.

- [ ] **Step 1: Write the failing tests**

Create `payload/tools/tests/test_bb_common.py`:

```python
import json, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import bb_common as bb


class TestConnect(unittest.TestCase):
    def _db(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return pathlib.Path(td.name) / "sub" / "blackboard.db"

    def test_connect_creates_parent_dir_and_all_tables(self):
        db_path = self._db()
        conn = bb.connect(db_path)
        self.addCleanup(conn.close)
        self.assertTrue(db_path.parent.is_dir())
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {r[0] for r in rows}
        for t in bb.ALL_TABLES:
            self.assertIn(t, names)

    def test_connect_is_idempotent(self):
        db_path = self._db()
        conn1 = bb.connect(db_path)
        conn1.close()
        conn2 = bb.connect(db_path)  # must not raise on existing tables
        self.addCleanup(conn2.close)

    def test_connect_uses_wal_mode(self):
        db_path = self._db()
        conn = bb.connect(db_path)
        self.addCleanup(conn.close)
        (mode,) = conn.execute("PRAGMA journal_mode").fetchone()
        self.assertEqual(mode.lower(), "wal")

    def test_payload_sha256_is_stable_regardless_of_key_order(self):
        a = bb.payload_sha256({"x": 1, "y": 2})
        b = bb.payload_sha256({"y": 2, "x": 1})
        self.assertEqual(a, b)

    def test_now_ts_format(self):
        ts = bb.now_ts()
        self.assertRegex(ts, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_insert_stamped_rejects_unknown_table(self):
        db_path = self._db()
        conn = bb.connect(db_path)
        self.addCleanup(conn.close)
        with self.assertRaises(ValueError):
            bb.insert_stamped(conn, "not_a_table", "t1", "EXECUTE", None, {"a": 1})

    def test_insert_stamped_round_trips_and_stamps_correctly(self):
        db_path = self._db()
        conn = bb.connect(db_path)
        self.addCleanup(conn.close)
        row_id = bb.insert_stamped(
            conn, "events", "t1", "EXECUTE", "agent-abc", {"event": "step-started"})
        row = conn.execute(
            "SELECT task_id, phase, agent_id, payload, payload_sha256 "
            "FROM events WHERE id = ?", (row_id,),
        ).fetchone()
        task_id, phase, agent_id, payload_json, digest = row
        self.assertEqual(task_id, "t1")
        self.assertEqual(phase, "EXECUTE")
        self.assertEqual(agent_id, "agent-abc")
        self.assertEqual(json.loads(payload_json), {"event": "step-started"})
        self.assertEqual(digest, bb.payload_sha256({"event": "step-started"}))

    def test_insert_artifact_upserts_on_same_id(self):
        db_path = self._db()
        conn = bb.connect(db_path)
        self.addCleanup(conn.close)
        bb.insert_artifact(conn, "art-1", "t1", "EXECUTE", None, "/tmp/a.txt", "deadbeef")
        bb.insert_artifact(conn, "art-1", "t1", "EXECUTE", None, "/tmp/a-v2.txt", "beadfeed")
        rows = conn.execute(
            "SELECT path, sha256 FROM artifacts WHERE artifact_id = ?", ("art-1",)
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], ("/tmp/a-v2.txt", "beadfeed"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the suite and confirm it fails**

Run: `python3 -m pytest payload/tools/tests/test_bb_common.py -v`
Expected: collection error / `ModuleNotFoundError: No module named 'bb_common'`
— the module doesn't exist yet.

- [ ] **Step 3: Write `payload/tools/bb_common.py`**

```python
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
    the standard, correct mitigation, not raw string interpolation of
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
```

- [ ] **Step 4: Run the suite and confirm it passes**

Run: `python3 -m pytest payload/tools/tests/test_bb_common.py -v`
Expected: PASS, 8 passed.

- [ ] **Step 5: Commit**

```bash
git add payload/tools/bb_common.py payload/tools/tests/test_bb_common.py
git commit -m "feat(blackboard): bb_common.py — schema, WAL connection, stamp helpers"
```

---

### Task 2: `bb_write.py`

**Files:**
- Create: `payload/tools/bb_write.py`
- Test: `payload/tools/tests/test_bb_write.py`

**Interfaces:**
- Consumes: `bb_common.{ALL_TABLES, default_db_path, connect, insert_stamped,
  insert_artifact}` from Task 1.
- Produces: `main(argv=None) -> int` (0 success, 2 usage error) — same
  entry-point shape every tool in this repo uses for its `if __name__ ==
  "__main__": sys.exit(main())` line.

- [ ] **Step 1: Write the failing tests**

Create `payload/tools/tests/test_bb_write.py`:

```python
import contextlib, hashlib, io, json, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import bb_write
import bb_common as bb


class TestBBWriteCLI(unittest.TestCase):
    def _db(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return str(pathlib.Path(td.name) / "blackboard.db")

    def _run(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = bb_write.main(argv)
        return rc, buf.getvalue()

    def test_writes_stamped_row_from_inline_payload(self):
        db = self._db()
        rc, out = self._run([
            "--db", db, "--table", "shared_state", "--task-id", "t1",
            "--phase", "EXECUTE", "--agent-id", "agent-1",
            "--payload", '{"key": "greeting", "value": "hi"}',
        ])
        self.assertEqual(rc, 0)
        self.assertIn("shared_state", out)
        conn = bb.connect(db)
        self.addCleanup(conn.close)
        row = conn.execute(
            "SELECT payload FROM shared_state WHERE task_id='t1'").fetchone()
        self.assertEqual(json.loads(row[0]), {"key": "greeting", "value": "hi"})

    def test_writes_from_payload_file(self):
        db = self._db()
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        payload_path = pathlib.Path(td.name) / "payload.json"
        payload_path.write_text('{"event": "step-done"}')
        rc, _ = self._run([
            "--db", db, "--table", "events", "--task-id", "t1",
            "--phase", "SCORE", "--payload-file", str(payload_path),
        ])
        self.assertEqual(rc, 0)
        conn = bb.connect(db)
        self.addCleanup(conn.close)
        row = conn.execute(
            "SELECT payload FROM events WHERE task_id='t1'").fetchone()
        self.assertEqual(json.loads(row[0]), {"event": "step-done"})

    def test_missing_payload_is_usage_error(self):
        db = self._db()
        rc, _ = self._run(
            ["--db", db, "--table", "events", "--task-id", "t1", "--phase", "SCORE"])
        self.assertEqual(rc, 2)

    def test_invalid_json_payload_is_usage_error(self):
        db = self._db()
        rc, _ = self._run([
            "--db", db, "--table", "events", "--task-id", "t1",
            "--phase", "SCORE", "--payload", "{not json",
        ])
        self.assertEqual(rc, 2)

    def test_writes_artifact_computing_sha256_from_file(self):
        db = self._db()
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        art_path = pathlib.Path(td.name) / "artifact.bin"
        art_path.write_bytes(b"hello blackboard")
        rc, out = self._run([
            "--db", db, "--table", "artifacts", "--artifact-id", "art-1",
            "--task-id", "t1", "--phase", "EXECUTE", "--path", str(art_path),
        ])
        self.assertEqual(rc, 0)
        conn = bb.connect(db)
        self.addCleanup(conn.close)
        row = conn.execute(
            "SELECT sha256 FROM artifacts WHERE artifact_id='art-1'").fetchone()
        self.assertEqual(row[0], hashlib.sha256(b"hello blackboard").hexdigest())

    def test_artifacts_requires_artifact_id_and_path(self):
        db = self._db()
        rc, _ = self._run(
            ["--db", db, "--table", "artifacts", "--task-id", "t1", "--phase", "EXECUTE"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the suite and confirm it fails**

Run: `python3 -m pytest payload/tools/tests/test_bb_write.py -v`
Expected: `ModuleNotFoundError: No module named 'bb_write'`.

- [ ] **Step 3: Write `payload/tools/bb_write.py`**

```python
#!/usr/bin/env python3
"""Write one stamped row to the blackboard — the only sanctioned write path
to ~/.claude/state/blackboard.db (agent-loop-v2 design spec, Phase 3).

Usage:
  python3 bb_write.py --table {shared_state,events,consensus_state,workflow_state} \
      --task-id ID --phase PHASE [--agent-id ID] (--payload JSON | --payload-file PATH)
  python3 bb_write.py --table artifacts --artifact-id ID --task-id ID --phase PHASE \
      [--agent-id ID] --path PATH [--sha256 HEX]

Exit 0 on success, 2 on a usage error (bad table, missing companion arg,
invalid JSON) — this tool does not fail open.
"""
import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bb_common as bb  # noqa: E402


def _load_payload(args):
    if args.payload_file:
        return json.loads(pathlib.Path(args.payload_file).read_text())
    if args.payload is None:
        raise ValueError("--table %s requires --payload or --payload-file" % args.table)
    return json.loads(args.payload)


def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--table", required=True, choices=list(bb.ALL_TABLES))
    p.add_argument("--task-id", required=True)
    p.add_argument("--phase", required=True)
    p.add_argument("--agent-id")
    p.add_argument("--payload")
    p.add_argument("--payload-file")
    p.add_argument("--artifact-id")
    p.add_argument("--path")
    p.add_argument("--sha256")
    p.add_argument("--db", default=str(bb.default_db_path()))
    a = p.parse_args(argv)

    conn = bb.connect(a.db)
    try:
        if a.table == "artifacts":
            if not a.artifact_id or not a.path:
                print("error: --table artifacts requires --artifact-id and --path",
                      file=sys.stderr)
                return 2
            digest = a.sha256 or _file_sha256(a.path)
            bb.insert_artifact(conn, a.artifact_id, a.task_id, a.phase, a.agent_id,
                                a.path, digest)
            print("wrote artifact %s -> %s" % (a.artifact_id, a.path))
            return 0

        try:
            payload_obj = _load_payload(a)
        except (ValueError, json.JSONDecodeError) as e:
            print("error: %s" % e, file=sys.stderr)
            return 2
        row_id = bb.insert_stamped(conn, a.table, a.task_id, a.phase, a.agent_id, payload_obj)
        print("wrote %s row %d for task %s" % (a.table, row_id, a.task_id))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the suite and confirm it passes**

Run: `python3 -m pytest payload/tools/tests/test_bb_write.py -v`
Expected: PASS, 6 passed.

- [ ] **Step 5: Commit**

```bash
git add payload/tools/bb_write.py payload/tools/tests/test_bb_write.py
git commit -m "feat(blackboard): bb_write.py — CLI to write stamped rows"
```

---

### Task 3: `bb_read.py`

**Files:**
- Create: `payload/tools/bb_read.py`
- Test: `payload/tools/tests/test_bb_read.py`

**Interfaces:**
- Consumes: `bb_common.{ALL_TABLES, STAMPED_TABLES, default_db_path, connect,
  insert_stamped, insert_artifact}` from Task 1.
- Produces: `fetch(conn, table, task_id=None, artifact_id=None) ->
  list[dict]` and `main(argv=None) -> int` — `fetch()` is exposed as a
  reusable function (not just CLI-internal) since Task 6 (REGISTRY guide) and
  any future in-process caller will want it without shelling out.

- [ ] **Step 1: Write the failing tests**

Create `payload/tools/tests/test_bb_read.py`:

```python
import contextlib, io, json, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import bb_read
import bb_common as bb


class TestBBReadCLI(unittest.TestCase):
    def _db_with_rows(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        db = str(pathlib.Path(td.name) / "blackboard.db")
        conn = bb.connect(db)
        bb.insert_stamped(conn, "events", "t1", "EXECUTE", "agent-1", {"event": "a"})
        bb.insert_stamped(conn, "events", "t1", "SCORE", "agent-1", {"event": "b"})
        bb.insert_stamped(conn, "events", "t2", "EXECUTE", "agent-2", {"event": "c"})
        bb.insert_artifact(conn, "art-1", "t1", "EXECUTE", None, "/tmp/a.txt", "deadbeef")
        conn.close()
        return db

    def _run(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = bb_read.main(argv)
        return rc, buf.getvalue()

    def test_filters_by_task_id(self):
        db = self._db_with_rows()
        rc, out = self._run(["--db", db, "--table", "events", "--task-id", "t1", "--json"])
        self.assertEqual(rc, 0)
        rows = json.loads(out)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["task_id"] == "t1" for r in rows))

    def test_no_task_id_returns_all_rows(self):
        db = self._db_with_rows()
        rc, out = self._run(["--db", db, "--table", "events", "--json"])
        rows = json.loads(out)
        self.assertEqual(len(rows), 3)

    def test_payload_is_decoded_json_not_a_string(self):
        db = self._db_with_rows()
        rc, out = self._run(["--db", db, "--table", "events", "--task-id", "t1", "--json"])
        rows = json.loads(out)
        self.assertEqual(rows[0]["payload"], {"event": "a"})

    def test_artifact_lookup_by_id(self):
        db = self._db_with_rows()
        rc, out = self._run(
            ["--db", db, "--table", "artifacts", "--artifact-id", "art-1", "--json"])
        rows = json.loads(out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sha256"], "deadbeef")

    def test_empty_result_human_output(self):
        db = self._db_with_rows()
        rc, out = self._run(
            ["--db", db, "--table", "consensus_state", "--task-id", "nope"])
        self.assertEqual(rc, 0)
        self.assertIn("no consensus_state rows", out)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the suite and confirm it fails**

Run: `python3 -m pytest payload/tools/tests/test_bb_read.py -v`
Expected: `ModuleNotFoundError: No module named 'bb_read'`.

- [ ] **Step 3: Write `payload/tools/bb_read.py`**

```python
#!/usr/bin/env python3
"""Read rows back from the blackboard (agent-loop-v2 design spec, Phase 3).

Usage:
  python3 bb_read.py --table {shared_state,events,consensus_state,workflow_state,artifacts} \
      [--task-id ID] [--artifact-id ID] [--json]

--artifact-id only applies to --table artifacts. Human output (default)
prints one JSON line per row; --json prints the whole result as one array.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bb_common as bb  # noqa: E402

_ARTIFACT_COLS = ["artifact_id", "task_id", "phase", "agent_id", "path", "sha256", "ts"]
_STAMPED_COLS = ["id", "task_id", "phase", "agent_id", "ts", "payload", "payload_sha256"]


def fetch(conn, table, task_id=None, artifact_id=None):
    if table == "artifacts":
        cols_sql = ", ".join(_ARTIFACT_COLS)
        if artifact_id:
            cur = conn.execute(
                "SELECT %s FROM artifacts WHERE artifact_id = ?" % cols_sql, (artifact_id,))
        elif task_id:
            cur = conn.execute(
                "SELECT %s FROM artifacts WHERE task_id = ? ORDER BY ts" % cols_sql,
                (task_id,))
        else:
            cur = conn.execute("SELECT %s FROM artifacts ORDER BY ts" % cols_sql)
        cols = _ARTIFACT_COLS
    else:
        if table not in bb.STAMPED_TABLES:
            raise ValueError("unknown table %r" % table)
        cols_sql = ", ".join(_STAMPED_COLS)
        if task_id:
            cur = conn.execute(
                "SELECT %s FROM %s WHERE task_id = ? ORDER BY id" % (cols_sql, table),
                (task_id,))
        else:
            cur = conn.execute("SELECT %s FROM %s ORDER BY id" % (cols_sql, table))
        cols = _STAMPED_COLS
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        if "payload" in r:
            r["payload"] = json.loads(r["payload"])
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--table", required=True, choices=list(bb.ALL_TABLES))
    p.add_argument("--task-id")
    p.add_argument("--artifact-id")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.add_argument("--db", default=str(bb.default_db_path()))
    a = p.parse_args(argv)

    conn = bb.connect(a.db)
    try:
        rows = fetch(conn, a.table, task_id=a.task_id, artifact_id=a.artifact_id)
    finally:
        conn.close()

    if a.as_json:
        print(json.dumps(rows, sort_keys=True))
    else:
        if not rows:
            print("no %s rows" % a.table)
        for r in rows:
            print(json.dumps(r, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the suite and confirm it passes**

Run: `python3 -m pytest payload/tools/tests/test_bb_read.py -v`
Expected: PASS, 5 passed.

- [ ] **Step 5: Commit**

```bash
git add payload/tools/bb_read.py payload/tools/tests/test_bb_read.py
git commit -m "feat(blackboard): bb_read.py — CLI to read rows back, filtered by task"
```

---

### Task 4: `bb_gc.py` + launchd plist

**Files:**
- Create: `payload/tools/bb_gc.py`
- Create: `payload/launchd/com.hdc.claude-agent-loop.blackboard-gc.plist`
- Test: `payload/tools/tests/test_bb_gc.py`
- Modify: `payload/MANIFEST`

**Interfaces:**
- Consumes: `bb_common.{default_db_path, connect}` from Task 1.
- Produces: `gc(conn, dry_run=False) -> dict[str, int]` (table name → rows
  deleted, or would-delete under `--dry-run`) and `main(argv=None) -> int`.

- [ ] **Step 1: Write the failing tests**

Create `payload/tools/tests/test_bb_gc.py`:

```python
import datetime, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import bb_gc
import bb_common as bb


class TestGC(unittest.TestCase):
    def _db(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return str(pathlib.Path(td.name) / "blackboard.db")

    def _insert_with_ts(self, conn, table, ts):
        conn.execute(
            "INSERT INTO %s (task_id, phase, agent_id, ts, payload, payload_sha256) "
            "VALUES ('t1', 'EXECUTE', NULL, ?, '{}', 'x')" % table,
            (ts,),
        )
        conn.commit()

    def test_trims_shared_state_and_artifacts_at_30_days_events_at_90(self):
        db = self._db()
        conn = bb.connect(db)
        self.addCleanup(conn.close)
        now = datetime.datetime.now(datetime.timezone.utc)
        old_31 = (now - datetime.timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old_29 = (now - datetime.timedelta(days=29)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old_91 = (now - datetime.timedelta(days=91)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old_89 = (now - datetime.timedelta(days=89)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._insert_with_ts(conn, "shared_state", old_31)
        self._insert_with_ts(conn, "shared_state", old_29)
        self._insert_with_ts(conn, "events", old_91)
        self._insert_with_ts(conn, "events", old_89)
        conn.execute(
            "INSERT INTO artifacts (artifact_id, task_id, phase, agent_id, path, sha256, ts) "
            "VALUES ('a1', 't1', 'EXECUTE', NULL, '/x', 'deadbeef', ?)", (old_31,))
        conn.commit()

        counts = bb_gc.gc(conn)

        self.assertEqual(counts["shared_state"], 1)
        self.assertEqual(counts["events"], 1)
        self.assertEqual(counts["artifacts"], 1)
        (remaining_shared,) = conn.execute("SELECT COUNT(*) FROM shared_state").fetchone()
        self.assertEqual(remaining_shared, 1)
        (remaining_events,) = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        self.assertEqual(remaining_events, 1)

    def test_dry_run_deletes_nothing(self):
        db = self._db()
        conn = bb.connect(db)
        self.addCleanup(conn.close)
        old = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._insert_with_ts(conn, "events", old)
        counts = bb_gc.gc(conn, dry_run=True)
        self.assertEqual(counts["events"], 1)
        (remaining,) = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        self.assertEqual(remaining, 1)

    def test_consensus_state_and_workflow_state_are_never_trimmed(self):
        db = self._db()
        conn = bb.connect(db)
        self.addCleanup(conn.close)
        ancient = (datetime.datetime.now(datetime.timezone.utc)
                   - datetime.timedelta(days=3650)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._insert_with_ts(conn, "consensus_state", ancient)
        self._insert_with_ts(conn, "workflow_state", ancient)
        bb_gc.gc(conn)
        (c,) = conn.execute("SELECT COUNT(*) FROM consensus_state").fetchone()
        (w,) = conn.execute("SELECT COUNT(*) FROM workflow_state").fetchone()
        self.assertEqual(c, 1)
        self.assertEqual(w, 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the suite and confirm it fails**

Run: `python3 -m pytest payload/tools/tests/test_bb_gc.py -v`
Expected: `ModuleNotFoundError: No module named 'bb_gc'`.

- [ ] **Step 3: Write `payload/tools/bb_gc.py`**

```python
#!/usr/bin/env python3
"""Trim old blackboard rows (agent-loop-v2 design spec, Phase 3): 30-day
retention on shared_state/artifacts, 90-day on events. consensus_state and
workflow_state are DELIBERATELY not trimmed here — the spec gives no
retention window for either, and both are audit/resume state (a vote
history Phase 6 wants queryable; a checkpoint a plan may still resume from)
that should not silently expire. Do not add them to RETENTION_DAYS without
re-reading the spec's Phase 3/6 sections first.

Usage: python3 bb_gc.py [--db PATH] [--dry-run]
Run from launchd — see
payload/launchd/com.hdc.claude-agent-loop.blackboard-gc.plist.
"""
import argparse
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bb_common as bb  # noqa: E402

RETENTION_DAYS = {"shared_state": 30, "artifacts": 30, "events": 90}


def _cutoff(days):
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def gc(conn, dry_run=False):
    """Return {table: rows_deleted_or_would_delete}. `table` below is only
    ever one of RETENTION_DAYS's own fixed keys — never caller input — so
    the %s interpolation is a whitelist substitution, not raw SQL injection
    surface (see bb_common.insert_stamped's docstring for the same note)."""
    counts = {}
    for table, days in RETENTION_DAYS.items():
        cutoff = _cutoff(days)
        if dry_run:
            (n,) = conn.execute(
                "SELECT COUNT(*) FROM %s WHERE ts < ?" % table, (cutoff,)
            ).fetchone()
            counts[table] = n
        else:
            cur = conn.execute("DELETE FROM %s WHERE ts < ?" % table, (cutoff,))
            counts[table] = cur.rowcount
    if not dry_run:
        conn.commit()
    return counts


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", default=str(bb.default_db_path()))
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)

    conn = bb.connect(a.db)
    try:
        counts = gc(conn, dry_run=a.dry_run)
    finally:
        conn.close()

    verb = "would delete" if a.dry_run else "deleted"
    for table, n in counts.items():
        print("%s: %s %d row(s) older than %d day(s)"
              % (table, verb, n, RETENTION_DAYS[table]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the suite and confirm it passes**

Run: `python3 -m pytest payload/tools/tests/test_bb_gc.py -v`
Expected: PASS, 3 passed.

- [ ] **Step 5: Add the launchd plist**

Create `payload/launchd/com.hdc.claude-agent-loop.blackboard-gc.plist`,
matching the exact shape of the 3 existing plists (daily, right after the
3:17am repo-audit slot to avoid contending with it; `/tmp` logs since
`bb_gc.py`'s own output is just row counts, not project/client-tinged
content — same sensitivity tier as `usage-poll`/`obs-ship`, not
`repo-audit`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hdc.claude-agent-loop.blackboard-gc</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-lc</string>
        <string>exec /usr/bin/env python3 "$HOME/.claude/tools/bb_gc.py"</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>4</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>
    <key>ProcessType</key>
    <string>Background</string>
    <key>StandardOutPath</key>
    <string>/tmp/com.hdc.claude-agent-loop.blackboard-gc.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/com.hdc.claude-agent-loop.blackboard-gc.err.log</string>
</dict>
</plist>
```

Note `RunAtLoad` is `false` here (unlike the other 3) — a GC job has no
reason to run immediately every time a session loads the agent (e.g. on
login); it should only ever run on its daily schedule. This plist is
version-controlled only; per the Grounding section, there is no installer
script in this repo — actually copying it to `~/Library/LaunchAgents/` and
`launchctl load`-ing it is a deploy-time action, out of scope for this dev-repo
plan (same boundary Phase 1/Phase 2 of this spec already drew).

- [ ] **Step 6: Add the MANIFEST entries**

In `payload/MANIFEST`, add one line under the existing `# --- launchd/ ---`
section (after the other 3 `link-file launchd/...` lines):

```
link-file launchd/com.hdc.claude-agent-loop.blackboard-gc.plist
```

- [ ] **Step 7: Commit**

```bash
git add payload/tools/bb_gc.py payload/tools/tests/test_bb_gc.py \
        payload/launchd/com.hdc.claude-agent-loop.blackboard-gc.plist \
        payload/MANIFEST
git commit -m "feat(blackboard): bb_gc.py retention trim + launchd plist"
```

---

### Task 5: Registry rows, guides, and ARCHITECTURE.md

**Files:**
- Modify: `payload/registry/REGISTRY.md`
- Create: `payload/registry/guides/bb-write.md`
- Create: `payload/registry/guides/bb-read.md`
- Create: `payload/registry/guides/bb-gc.md`
- Modify: `ARCHITECTURE.md`

**Interfaces:**
- Consumes: nothing code-level.
- Produces: nothing another task depends on — terminal task of this plan.

- [ ] **Step 1: Add 3 rows to the `## Tools` section of `payload/registry/REGISTRY.md`**

Append after the existing `repo-audit-action` row (same domain as the other
plan/registry-lifecycle tools — cross-agent shared-state coordination):

```
| bb-write | tool | meta-orchestration | Write a stamped row (task_id/phase/agent_id/ts/sha256) to the blackboard — shared_state, events, consensus_state, workflow_state, or artifacts |
| bb-read | tool | meta-orchestration | Read blackboard rows back, filtered by task_id (or artifact_id for the artifacts table) |
| bb-gc | tool | meta-orchestration | Nightly blackboard retention trim — 30-day shared_state/artifacts, 90-day events; consensus_state/workflow_state kept indefinitely |
```

- [ ] **Step 2: Run `lint_registry.py` and confirm it fails on the missing guides**

Run: `python3 payload/tools/lint_registry.py payload/registry`
Expected: 3 errors — `'bb-write': index row has no guide (guides/bb-write.md)`
and the same for `bb-read`, `bb-gc`.

- [ ] **Step 3: Write the 3 guide files**

Create `payload/registry/guides/bb-write.md`:

```markdown
# Guide — bb-write

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The blackboard (agent-loop-v2 design spec, Phase 3) is cross-agent shared
state — hints, results, artifact IDs, phase-transition events, consensus
votes, resumable checkpoints — that no single JSON file (like a plan's own
`plans/<id>.json`) is the right shape for. `bb_write.py` is the only
sanctioned write path into it.

## When to deploy (triggers)
Any EXECUTE step that needs to leave a result, hint, or checkpoint another
step or a later session can read back; any phase transition worth an audit
trail; any gated action needing a Phase 6 consensus vote recorded (once
Phase 6 lands).

## Interface (how to invoke)
```
python3 ~/.claude/tools/bb_write.py --table {shared_state,events,consensus_state,workflow_state} \
    --task-id <id> --phase <MATCH|PLAN|ANNOUNCE|ROUTE|EXECUTE|SCORE|MERGE|LEARN> \
    [--agent-id <id>] (--payload '<json>' | --payload-file <path>)

python3 ~/.claude/tools/bb_write.py --table artifacts --artifact-id <id> \
    --task-id <id> --phase <phase> [--agent-id <id>] --path <path> [--sha256 <hex>]
```

## Composition (pairs with / hands off to)
Pairs with `bb-read` (the read side of the same store) and `bb-gc` (the
retention trim). Sits alongside, not instead of, `plan-task`'s own
`plans/<id>.json` — the plan file is a task's own record; the blackboard is
what tasks share with each other.

## Build & maintenance notes
Lives at `~/.claude/tools/bb_write.py`, backed by `~/.claude/tools/bb_common.py`
(schema + connection) and `~/.claude/state/blackboard.db` (WAL-mode SQLite,
single file, no daemon). Exit 0 success, 2 usage error.
```

Create `payload/registry/guides/bb-read.md`:

```markdown
# Guide — bb-read

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The read side of the blackboard (agent-loop-v2 design spec, Phase 3) — the
only sanctioned way to look up what another agent or an earlier phase left
behind, without every reader inventing its own SQLite query.

## When to deploy (triggers)
Any step that wants a prior step's shared_state hint, an artifact's path by
its id, the event trail for a task, or (once Phase 6 lands) a consensus
vote's current tally.

## Interface (how to invoke)
```
python3 ~/.claude/tools/bb_read.py --table {shared_state,events,consensus_state,workflow_state,artifacts} \
    [--task-id <id>] [--artifact-id <id>] [--json]
```
`--artifact-id` only applies to `--table artifacts`. Default output is one
JSON line per row; `--json` returns the whole result as one array.

## Composition (pairs with / hands off to)
The read counterpart to `bb-write`; `bb-gc` trims what this can see over
time.

## Build & maintenance notes
Lives at `~/.claude/tools/bb_read.py`; exposes a reusable `fetch()` function,
not just a CLI, for any future in-process caller.
```

Create `payload/registry/guides/bb-gc.md`:

```markdown
# Guide — bb-gc

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The blackboard (agent-loop-v2 design spec, Phase 3) has no daemon and no
automatic expiry — without a trim job, `shared_state`/`events`/`artifacts`
grow forever. `bb_gc.py` applies the spec's stated retention windows.

## When to deploy (triggers)
Runs unattended, nightly, via
`payload/launchd/com.hdc.claude-agent-loop.blackboard-gc.plist` — not
something a session invokes directly, though `--dry-run` is safe to run by
hand to preview what a real run would delete.

## Interface (how to invoke)
`python3 ~/.claude/tools/bb_gc.py [--db <path>] [--dry-run]` — 30-day trim on
`shared_state`/`artifacts`, 90-day on `events`. `consensus_state` and
`workflow_state` are never trimmed by this tool (deliberate — see the
module's own docstring before changing that).

## Composition (pairs with / hands off to)
Operates on the same `blackboard.db` that `bb-write`/`bb-read` do; shares no
code with `audit-dispatch`'s nightly sweep (different launchd job, different
concern).

## Build & maintenance notes
Lives at `~/.claude/tools/bb_gc.py`. Installed the same manual way the other
3 launchd plists in this repo are — copy to `~/Library/LaunchAgents/`,
`launchctl load` — there is no installer script.
```

- [ ] **Step 4: Run `lint_registry.py` and confirm it's clean**

Run: `python3 payload/tools/lint_registry.py payload/registry`
Expected: `lint_registry: OK (0 error(s))`

- [ ] **Step 5: Add the ARCHITECTURE.md note**

In `ARCHITECTURE.md`, immediately after the "### 2. Runtime loop layer"
subsection's bullet list (after the `usage-budget.sh` bullet, before "###
3. Doc-cascade layer"), add one new bullet:

```
- **`payload/tools/bb_write.py` / `bb_read.py` / `bb_gc.py`** (backed by
  `bb_common.py`) are the sanctioned access path to
  `~/.claude/state/blackboard.db` — a single-file, WAL-mode SQLite store for
  cross-agent shared state (hints/results, a phase-transition event log,
  consensus votes, resumable plan checkpoints, and large-payload artifact
  pointers) that sits alongside, not instead of, the metrics `*.jsonl`
  ledger: metrics is the permanent record, the blackboard is working state.
```

- [ ] **Step 6: Run the full tool test suite**

Run: `python3 -m pytest payload/tools/tests/ -v -k "bb_ or registry"`
Expected: all PASS (8 + 6 + 5 + 3 blackboard tests, plus the 13 registry
tests from Phase 2 — 35 total).

- [ ] **Step 7: Commit**

```bash
git add payload/registry/REGISTRY.md payload/registry/guides/bb-write.md \
        payload/registry/guides/bb-read.md payload/registry/guides/bb-gc.md \
        ARCHITECTURE.md
git commit -m "docs(blackboard): registry rows, guides, and architecture note for bb_*"
```

---

## Testing & rollback

Each task's commit is independently revertable via `git revert`, in reverse
task order (Task 5 depends on Tasks 1-4 existing to have something to
document; Task 4 depends on Task 1; Tasks 2/3 depend on Task 1 but not on
each other or on Task 4).

Final check for the whole phase:

```bash
python3 -m pytest payload/tools/tests/ -v -k "bb_"
python3 payload/tools/lint_registry.py payload/registry
```

Expected: 22 blackboard tests passed; `lint_registry: OK (0 error(s))`.

Deploying the resulting `~/.claude/state/blackboard.db` onto the live
machine, and installing the new launchd plist, are deploy-time actions —
out of scope for this dev-repo plan, same boundary this spec's Phase 1 and
Phase 2 plans already drew.
