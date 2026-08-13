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
