import contextlib, io, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import consensus_vote as cv


class TestConsensusVote(unittest.TestCase):
    def _db(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return str(pathlib.Path(td.name) / "blackboard.db")

    def test_record_rejects_bad_action_type(self):
        db = self._db()
        with self.assertRaises(ValueError):
            cv.record(db, "t1", "delete-prod-db", "alice", "approve")

    def test_record_rejects_bad_vote(self):
        db = self._db()
        with self.assertRaises(ValueError):
            cv.record(db, "t1", "git-push", "alice", "maybe")

    def test_tally_counts_votes_by_action_type(self):
        db = self._db()
        cv.record(db, "t1", "git-push", "alice", "approve")
        cv.record(db, "t1", "git-push", "bob", "approve")
        cv.record(db, "t1", "git-push", "carol", "reject")
        cv.record(db, "t1", "aws-mutation", "alice", "approve")  # different action_type, must not count
        result = cv.tally(db, "t1", "git-push")
        self.assertEqual(result["total_votes"], 3)
        self.assertEqual(result["approve"], 2)
        self.assertEqual(result["reject"], 1)
        self.assertTrue(result["quorum_met"])
        self.assertEqual(sorted(result["voters"]), ["alice", "bob", "carol"])

    def test_tally_quorum_not_met_below_threshold(self):
        db = self._db()
        cv.record(db, "t1", "publish-release", "alice", "approve")
        result = cv.tally(db, "t1", "publish-release")
        self.assertFalse(result["quorum_met"])

    def test_tally_custom_threshold(self):
        db = self._db()
        cv.record(db, "t1", "aws-mutation", "alice", "approve")
        result = cv.tally(db, "t1", "aws-mutation", threshold=1)
        self.assertTrue(result["quorum_met"])

    def test_tally_scoped_to_task_id(self):
        db = self._db()
        cv.record(db, "t1", "git-push", "alice", "approve")
        cv.record(db, "t2", "git-push", "bob", "approve")
        result = cv.tally(db, "t1", "git-push")
        self.assertEqual(result["total_votes"], 1)

    def test_cli_record_and_tally(self):
        db = self._db()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc1 = cv.main(["--record", "--task-id", "t1", "--action-type", "git-push",
                           "--voter", "alice", "--vote", "approve", "--db", db])
        self.assertEqual(rc1, 0)
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = cv.main(["--tally", "--task-id", "t1", "--action-type", "git-push", "--db", db])
        self.assertEqual(rc2, 0)
        self.assertIn("1 approve", buf2.getvalue())

    def test_cli_record_requires_voter_and_vote(self):
        db = self._db()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = cv.main(["--record", "--task-id", "t1", "--action-type", "git-push", "--db", db])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
