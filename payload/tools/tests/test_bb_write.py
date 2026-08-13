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
