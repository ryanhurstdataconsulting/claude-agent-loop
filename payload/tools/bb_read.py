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
