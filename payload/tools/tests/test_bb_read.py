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
