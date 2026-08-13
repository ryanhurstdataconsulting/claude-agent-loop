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
