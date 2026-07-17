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
        # Reads the NEWEST monthly shard only. There is a sub-second window at a
        # month boundary where a planted record (dated to one _now_iso()) and the
        # score record (dated to a later _now_iso()) could straddle two shards;
        # this helper would then see only the score. Accepted: the suite runs far
        # from month boundaries in practice, and _lookup_resources itself scans
        # both the previous and current month shards, so the join is unaffected.
        shards = sorted(self.metrics.glob("*.jsonl"))
        return shards[-1] if shards else None

    def _plant_session(self, task_id, resources):
        hm._append_record(str(self.metrics), {
            "schema": 1, "kind": "session", "task_id": task_id,
            "resources_deployed": resources, "ts_end": st._now_iso(),
        })

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
        # L4: ts_end is the single score timestamp; the redundant `ts` is gone.
        self.assertIn("ts_end", s)
        self.assertNotIn("ts", s)

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

    # --- M1: task_id normalization -------------------------------------------

    def test_bare_task_id_normalized_to_session_and_joins(self):
        # M1: a bare session id (neither session-* nor agent-*) is main-thread
        # work; it must be prefixed `session-` so it joins the harvester's
        # session-<sid> record, and the tool must print a note when it does.
        self._plant_task("session-abc", ["sports-analyst"])
        rc, out, err = self._run(self._score_args(
            "--task-id", "abc", "--scale", "outcome=good"))
        self.assertEqual(rc, 0, err)
        self.assertIn("normaliz", out.lower())   # a note is printed
        s = [r for r in _records(self._shard()) if r["kind"] == "score"][0]
        self.assertEqual(s["task_id"], "session-abc")
        self.assertEqual(s["resources_deployed"], ["sports-analyst"])

    def test_agent_task_id_passes_through(self):
        # M1: an agent-<id> is a subagent's own score — it passes through
        # unchanged and joins its own task record.
        self._plant_task("agent-xyz", ["token-efficiency"])
        rc, out, err = self._run(self._score_args(
            "--task-id", "agent-xyz", "--scale", "outcome=good"))
        self.assertEqual(rc, 0, err)
        self.assertNotIn("normaliz", out.lower())   # no note for a valid key
        s = [r for r in _records(self._shard()) if r["kind"] == "score"][0]
        self.assertEqual(s["task_id"], "agent-xyz")
        self.assertEqual(s["resources_deployed"], ["token-efficiency"])

    def test_session_prefixed_task_id_not_double_prefixed(self):
        # M1: an already-session-* id is left alone (no session-session-...).
        rc, out, err = self._run(self._score_args(
            "--task-id", "session-abc", "--scale", "outcome=good"))
        self.assertEqual(rc, 0, err)
        self.assertNotIn("normaliz", out.lower())
        s = [r for r in _records(self._shard()) if r["kind"] == "score"][0]
        self.assertEqual(s["task_id"], "session-abc")

    # --- M2: main-thread resources join the session record -------------------

    def test_main_thread_score_joins_session_record(self):
        # M2: main-thread resources live on the session rollup, not a task
        # record. A score for a session-* id with only a kind:"session" record
        # present must inherit that session's resources_deployed.
        self._plant_session("session-abc",
                            ["token-efficiency", "sports-analyst"])
        rc, _, err = self._run(self._score_args(
            "--task-id", "session-abc", "--scale", "outcome=good"))
        self.assertEqual(rc, 0, err)
        s = [r for r in _records(self._shard()) if r["kind"] == "score"][0]
        self.assertEqual(s["resources_deployed"],
                         ["token-efficiency", "sports-analyst"])

    def test_task_record_wins_over_session_record(self):
        # M2: when both a task and a session record share the id, the task
        # record still wins.
        self._plant_session("session-abc", ["session-only"])
        self._plant_task("session-abc", ["task-wins"])
        rc, _, err = self._run(self._score_args(
            "--task-id", "session-abc", "--scale", "outcome=good"))
        self.assertEqual(rc, 0, err)
        s = [r for r in _records(self._shard()) if r["kind"] == "score"][0]
        self.assertEqual(s["resources_deployed"], ["task-wins"])

    # --- T1: argument-error coverage -----------------------------------------

    def test_scale_without_equals_exits_2(self):
        rc, _, err = self._run(self._score_args(
            "--task-id", "session-abc", "--scale", "outcomegood"))
        self.assertEqual(rc, 2)
        self.assertIn("expected name=level", err)

    def test_score_mode_no_scale_exits_2(self):
        rc, _, err = self._run(self._score_args("--task-id", "session-abc"))
        self.assertEqual(rc, 2)
        self.assertIn("--scale", err)

    def test_new_scale_missing_levels_exits_2(self):
        rc, _, err = self._run([
            "--new-scale", "latency", "--applies-to", "t", "--desc", "d",
            "--scales-file", str(self.scales)])
        self.assertEqual(rc, 2)
        self.assertIn("--levels", err)

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

    # --- task shape (H5 route-cost signal) ------------------------------------

    def test_task_shape_flag_lands_on_record(self):
        rc, _, err = self._run(self._score_args(
            "--task-id", "session-shape1",
            "--scale", "outcome=good",
            "--task-shape", "mechanical"))
        self.assertEqual(rc, 0, err)
        score = [r for r in _records(self._shard()) if r["kind"] == "score"][-1]
        self.assertEqual(score["task_shape"], "mechanical")

    def test_task_shape_omitted_leaves_key_absent(self):
        rc, _, err = self._run(self._score_args(
            "--task-id", "session-shape2", "--scale", "outcome=good"))
        self.assertEqual(rc, 0, err)
        score = [r for r in _records(self._shard()) if r["kind"] == "score"][-1]
        self.assertNotIn("task_shape", score)

    def test_task_shape_invalid_value_rejected(self):
        with self.assertRaises(SystemExit) as ctx:
            self._run(self._score_args(
                "--task-id", "session-shape3", "--scale", "outcome=good",
                "--task-shape", "huge"))
        self.assertNotEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
