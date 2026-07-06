"""Tests for score_task — the subjective self-score writer (P3).

Written TDD-first: imports ``score_task`` before it exists (RED). Fixtures are
synthetic; the one JWT-shaped string exercises the redaction path and is not a
real token. Records are read back from the monthly shard to assert the store
contract (last task record per task_id supplies ``resources_deployed``; a score
record joins its task on ``task_id``).
"""
import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import score_task as st  # noqa: E402
import harvest_metrics as hm  # noqa: E402
import lint_scales as ls  # noqa: E402

SEED = pathlib.Path(__file__).resolve().parents[2] / "learning" / "SCALES.md"


def _records(shard):
    return [json.loads(ln) for ln in shard.read_text().splitlines() if ln.strip()]


class TestScoreTask(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        base = pathlib.Path(self.td.name)
        self.metrics = base / "metrics"
        self.metrics.mkdir()
        self.scales = base / "SCALES.md"
        self.scales.write_text(SEED.read_text())

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = st.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def _shard(self):
        shards = sorted(self.metrics.glob("*.jsonl"))
        return shards[-1] if shards else None

    def _plant_task(self, task_id, resources):
        hm._append_record(str(self.metrics), {
            "schema": 1, "kind": "task", "task_id": task_id,
            "resources_deployed": resources, "ts_end": st._now_iso(),
        })

    def _score_args(self, *extra):
        return list(extra) + ["--metrics-dir", str(self.metrics),
                              "--scales-file", str(self.scales)]

    # --- scoring -------------------------------------------------------------

    def test_valid_score_appends_record_with_resources(self):
        self._plant_task("session-abc", ["sports-analyst", "data-visualization"])
        rc, _, err = self._run(self._score_args(
            "--task-id", "session-abc",
            "--scale", "outcome=good", "--scale", "ui=ok"))
        self.assertEqual(rc, 0, err)
        recs = _records(self._shard())
        scores = [r for r in recs if r["kind"] == "score"]
        self.assertEqual(len(scores), 1)
        s = scores[0]
        self.assertEqual(s["task_id"], "session-abc")
        self.assertEqual(s["scales"], {"outcome": "good", "ui": "ok"})
        self.assertEqual(s["resources_deployed"],
                         ["sports-analyst", "data-visualization"])
        # the score joins its task on task_id
        tasks = [r for r in recs if r["kind"] == "task"]
        self.assertEqual(s["task_id"], tasks[0]["task_id"])

    def test_last_task_record_wins_for_resources(self):
        # store contract: consumers take the LAST record per (task_id, kind)
        self._plant_task("session-abc", [])
        self._plant_task("session-abc", ["token-efficiency"])
        rc, _, err = self._run(self._score_args(
            "--task-id", "session-abc", "--scale", "outcome=great"))
        self.assertEqual(rc, 0, err)
        s = [r for r in _records(self._shard()) if r["kind"] == "score"][0]
        self.assertEqual(s["resources_deployed"], ["token-efficiency"])

    def test_resources_empty_when_no_task_record(self):
        rc, _, err = self._run(self._score_args(
            "--task-id", "session-none", "--scale", "outcome=good"))
        self.assertEqual(rc, 0, err)
        s = [r for r in _records(self._shard()) if r["kind"] == "score"][0]
        self.assertEqual(s["resources_deployed"], [])

    def test_unknown_scale_exits_2(self):
        rc, _, err = self._run(self._score_args(
            "--task-id", "t", "--scale", "bogus=good"))
        self.assertEqual(rc, 2)
        self.assertIn("unknown scale", err.lower())
        self.assertIn("bogus", err)

    def test_unknown_level_exits_2_and_lists_valid(self):
        rc, _, err = self._run(self._score_args(
            "--task-id", "t", "--scale", "outcome=amazing"))
        self.assertEqual(rc, 2)
        self.assertIn("unknown level", err.lower())
        self.assertIn("great", err)   # valid levels are listed

    def test_note_is_redacted(self):
        jwt = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
               "eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcDEFghiJKLmnop")
        rc, _, err = self._run(self._score_args(
            "--task-id", "t", "--scale", "outcome=good",
            "--note", f"leaked {jwt} in the note"))
        self.assertEqual(rc, 0, err)
        s = [r for r in _records(self._shard()) if r["kind"] == "score"][0]
        self.assertNotIn(jwt, s["note"])
        self.assertIn("REDACTED-JWT", s["note"])

    # --- --new-scale ---------------------------------------------------------

    def test_new_scale_appends_under_extended_and_lints(self):
        rc, out, err = self._run([
            "--new-scale", "latency", "--levels", "fast>ok>slow",
            "--applies-to", "any perf-sensitive task",
            "--desc", "How snappy the result felt",
            "--scales-file", str(self.scales)])
        self.assertEqual(rc, 0, err)
        self.assertIn("latency", self.scales.read_text())
        self.assertEqual(ls.lint(self.scales), [])

    def test_new_scale_duplicate_rejected_unchanged(self):
        self._run(["--new-scale", "latency", "--levels", "fast>ok>slow",
                   "--applies-to", "t", "--desc", "d",
                   "--scales-file", str(self.scales)])
        before = self.scales.read_text()
        rc, _, err = self._run([
            "--new-scale", "latency", "--levels", "fast>ok>slow",
            "--applies-to", "t", "--desc", "d",
            "--scales-file", str(self.scales)])
        self.assertEqual(rc, 2)
        self.assertIn("already exists", err.lower())
        self.assertEqual(self.scales.read_text(), before)

    def test_new_scale_duplicate_of_core_id_rejected(self):
        rc, _, err = self._run([
            "--new-scale", "outcome", "--levels", "a>b",
            "--applies-to", "t", "--desc", "d",
            "--scales-file", str(self.scales)])
        self.assertEqual(rc, 2)
        self.assertIn("already exists", err.lower())

    def test_new_scale_reverts_on_lint_failure(self):
        before = self.scales.read_text()
        rc, _, err = self._run([
            "--new-scale", "broken", "--levels", "onlyone",
            "--applies-to", "t", "--desc", "d",
            "--scales-file", str(self.scales)])
        self.assertEqual(rc, 2)
        self.assertEqual(self.scales.read_text(), before)   # reverted
        self.assertNotIn("broken", self.scales.read_text())


if __name__ == "__main__":
    unittest.main()
