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
