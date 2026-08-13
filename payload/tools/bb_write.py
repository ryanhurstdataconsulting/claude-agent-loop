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
