"""Tests for score_task — the self-score writer (P3) and the objective
auto-assess algorithm ported in from assess_task.py.

Written TDD-first: imports ``score_task`` before it exists (RED). Fixtures are
synthetic; the one JWT-shaped string exercises the redaction path and is not a
real token. Records are read back from the monthly shard to assert the store
contract (last task record per task_id supplies ``resources_deployed``; a score
record joins its task on ``task_id``).
"""
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import score_task as st  # noqa: E402
import harvest_metrics as hm  # noqa: E402
import lint_scales as ls  # noqa: E402
import plan_task as pt  # noqa: E402

TOOLS = pathlib.Path(__file__).resolve().parents[1]
SEED = pathlib.Path(__file__).resolve().parents[2] / "learning" / "SCALES.md"


def ev(**over):
    base = {"tests_detected": True, "tests_failed": 0, "reverts": 0,
            "error_rate": 0.0, "commits": 1, "followup_fixes": 0}
    base.update(over)
    return base


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


# --- objective auto-assess (ported from test_assess_task.py) ----------------
# Same inputs, same expected verdict strings, imported as score_task.* instead
# of assess_task.*.

class TestVerdict(unittest.TestCase):
    def test_clean_requires_no_failures_no_reverts_low_errors(self):
        self.assertEqual(st.verdict(ev()), "clean")

    def test_failed_test_forces_dirty(self):
        self.assertEqual(st.verdict(ev(tests_failed=3)), "dirty")

    def test_revert_forces_dirty(self):
        self.assertEqual(st.verdict(ev(reverts=1)), "dirty")

    def test_followup_fix_forces_dirty(self):
        self.assertEqual(st.verdict(ev(followup_fixes=1)), "dirty")

    def test_high_error_rate_is_dirty(self):
        self.assertEqual(st.verdict(ev(error_rate=0.5)), "dirty")

    def test_error_rate_at_the_threshold_is_still_clean(self):
        self.assertEqual(st.verdict(ev(error_rate=st.ERROR_RATE_MAX)), "clean")

    def test_no_signal_is_unknown_never_clean(self):
        self.assertEqual(
            st.verdict({"tests_detected": False, "tests_failed": 0, "reverts": 0,
                        "error_rate": None, "commits": 0, "followup_fixes": 0}),
            "unknown")

    def test_commits_alone_are_signal_enough_for_clean(self):
        self.assertEqual(
            st.verdict({"tests_detected": False, "tests_failed": 0, "reverts": 0,
                        "error_rate": None, "commits": 2, "followup_fixes": 0}),
            "clean")

    def test_empty_evidence_is_unknown(self):
        self.assertEqual(st.verdict({}), "unknown")


class TestMetricsFor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shard = pathlib.Path(self.tmp) / "2026-07.jsonl"
        rows = [
            {"kind": "task", "task_id": "agent-aaa", "tests": {"detected": True, "passed": 3, "failed": 0},
             "tool_errors": 0, "error_rate": 0.0, "turns": 8, "duration_s": 12.0},
            {"kind": "task", "task_id": "agent-bbb", "tests": {"detected": True, "passed": 1, "failed": 2},
             "tool_errors": 4, "error_rate": 0.4, "turns": 30, "duration_s": 99.0},
            {"kind": "session", "task_id": "session-zzz"},
        ]
        shard.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finds_the_matching_task_record(self):
        rec = st.metrics_for(self.tmp, "agent-bbb")
        self.assertEqual(rec["tests"]["failed"], 2)

    def test_missing_id_returns_none(self):
        self.assertIsNone(st.metrics_for(self.tmp, "agent-nope"))

    def test_ignores_non_task_records(self):
        self.assertIsNone(st.metrics_for(self.tmp, "session-zzz"))

    def test_missing_directory_returns_none(self):
        self.assertIsNone(st.metrics_for(self.tmp + "-gone", "agent-aaa"))


class TestGitEvidence(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self._git("init", "-q")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "user.name", "T")
        self._commit("feat: first thing", "a.txt", "one")
        self._commit("Revert \"feat: first thing\"", "a.txt", "two")
        self._commit("fix: patch the first thing", "a.txt", "three")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _git(self, *args):
        return subprocess.run(["git"] + list(args), cwd=self.repo,
                              capture_output=True, text=True)

    def _commit(self, subject, name, body):
        (pathlib.Path(self.repo) / name).write_text(body)
        self._git("add", name)
        self._git("commit", "-q", "-m", subject)

    def test_counts_commits_in_window(self):
        g = st.git_evidence(self.repo, since=None, until=None, files=None)
        self.assertGreaterEqual(g["commits"], 3)

    def test_counts_reverts(self):
        self.assertEqual(st.git_evidence(self.repo, None, None, None)["reverts"], 1)

    def test_counts_followup_fixes(self):
        self.assertEqual(st.git_evidence(self.repo, None, None, None)["followup_fixes"], 1)

    def test_non_repo_yields_zeroes_not_a_crash(self):
        empty = tempfile.mkdtemp()
        try:
            g = st.git_evidence(empty, None, None, None)
            self.assertEqual(g["commits"], 0)
            self.assertEqual(g["reverts"], 0)
        finally:
            shutil.rmtree(empty, ignore_errors=True)


class TestAutoAssess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.metrics_dir = self.tmp
        shard = pathlib.Path(self.tmp) / "2026-07.jsonl"
        shard.write_text(json.dumps(
            {"kind": "task", "task_id": "agent-aaa",
             "tests": {"detected": True, "passed": 3, "failed": 0},
             "tool_errors": 0, "error_rate": 0.0, "turns": 8, "duration_s": 12.0}) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _plan(self, agent_id, status="done"):
        return {"schema": pt.SCHEMA, "task_id": "wo-20260701-testtask-abcdef",
                "task": "t", "created": "2026-07-01T00:00:00Z", "git_branch": "main",
                "steps": [{"id": "p1", "goal": "g", "agent": "dba", "skills": [],
                           "status": status, "agent_task_id": agent_id,
                           "return": {"ok": status == "done"}, "assessment": None}]}

    def _plan_with_one_done_step(self):
        return self._plan("agent-aaa", status="done")

    def _plan_with_one_failed_step(self):
        return self._plan("agent-aaa", status="failed")

    def test_assess_fills_assessment_on_every_step(self):
        plan = self._plan_with_one_done_step()
        st.auto_assess(plan, self.metrics_dir, repo=None)
        step = plan["steps"][0]
        self.assertIn("evidence", step["assessment"])
        self.assertIn(step["assessment"]["verdict"], ("clean", "dirty", "unknown"))

    def test_failed_step_cannot_assess_clean(self):
        plan = self._plan_with_one_failed_step()
        st.auto_assess(plan, self.metrics_dir, repo=None)
        self.assertEqual(plan["steps"][0]["assessment"]["verdict"], "dirty")

    def test_assess_fills_evidence_and_verdict_clean(self):
        plan = self._plan_with_one_done_step()
        st.auto_assess(plan, self.metrics_dir, repo=None)
        step = plan["steps"][0]
        self.assertEqual(step["assessment"]["evidence"]["tests_failed"], 0)
        self.assertEqual(step["assessment"]["verdict"], "clean")

    def test_missing_metrics_record_yields_unknown_not_clean(self):
        plan = self._plan("agent-missing")
        st.auto_assess(plan, self.metrics_dir, repo=None)
        self.assertEqual(plan["steps"][0]["assessment"]["verdict"], "unknown")

    def test_step_with_no_agent_id_is_unknown(self):
        plan = self._plan(None)
        st.auto_assess(plan, self.metrics_dir, repo=None)
        self.assertEqual(plan["steps"][0]["assessment"]["verdict"], "unknown")


class TestEvidenceScaleMapping(unittest.TestCase):
    def test_clean_maps_to_proven(self):
        self.assertEqual(st.evidence_scale_for("clean"), "proven")

    def test_dirty_maps_to_asserted_not_partial(self):
        # dirty means a real problem was found, not merely "no strong signal" —
        # asserted ("no verifiable evidence backs the outcome claim") is closer
        # in spirit than partial, and a caller who wants a rework=minor|major
        # flag reads that from the per-step assessment, not this scale alone.
        self.assertEqual(st.evidence_scale_for("dirty"), "asserted")

    def test_unknown_maps_to_asserted(self):
        self.assertEqual(st.evidence_scale_for("unknown"), "asserted")


class TestAutoCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state = pathlib.Path(self.tmp) / "state"
        self.metrics = pathlib.Path(self.tmp) / "metrics"
        self.metrics.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "score_task.py")] + list(args),
            capture_output=True, text=True)

    def _plant_task_metric(self, task_id, passed=3, failed=0, tool_errors=0,
                           error_rate=0.0):
        hm._append_record(str(self.metrics), {
            "schema": 1, "kind": "task", "task_id": task_id,
            "tests": {"detected": True, "passed": passed, "failed": failed},
            "tool_errors": tool_errors, "error_rate": error_rate,
            "ts_end": st._now_iso(),
        })

    def _save_plan(self, task_id, steps):
        pt.save(str(self.state), {
            "schema": pt.SCHEMA, "task_id": task_id, "task": "t",
            "created": "2026-07-01T00:00:00Z", "git_branch": "main",
            "steps": steps})

    def _newest_shard_records(self):
        shards = sorted(self.metrics.glob("*.jsonl"))
        self.assertTrue(shards, "no metrics shard was written")
        return [json.loads(ln) for ln in shards[-1].read_text().splitlines()
                if ln.strip()]

    def test_auto_writes_assessment_and_appends_score_record(self):
        task_id = "wo-20260701-autotask-abcdef"
        self._plant_task_metric("agent-aaa")
        self._save_plan(task_id, [{
            "id": "p1", "goal": "g", "agent": "dba", "skills": [],
            "status": "done", "agent_task_id": "agent-aaa",
            "return": {"ok": True, "files_touched": []}, "assessment": None,
        }])

        r = self._run("--auto", task_id, "--state-dir", str(self.state),
                      "--metrics-dir", str(self.metrics))
        self.assertEqual(r.returncode, 0, r.stderr)

        plan = pt.load(str(self.state), task_id)
        assessment = plan["steps"][0]["assessment"]
        self.assertIsNotNone(assessment)
        self.assertEqual(assessment["verdict"], "clean")

        scores = [rec for rec in self._newest_shard_records()
                  if rec["kind"] == "score"
                  and rec["task_id"] == "session-" + task_id]
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0]["scales"]["evidence"], "proven")

    def test_auto_flags_rework_on_followup_fix(self):
        repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repo, ignore_errors=True)

        def _git(*args):
            subprocess.run(["git"] + list(args), cwd=repo,
                           capture_output=True, text=True)

        _git("init", "-q")
        _git("config", "user.email", "t@example.com")
        _git("config", "user.name", "T")
        (pathlib.Path(repo) / "a.txt").write_text("one")
        _git("add", "a.txt")
        _git("commit", "-q", "-m", "feat: first thing")
        (pathlib.Path(repo) / "a.txt").write_text("two")
        _git("add", "a.txt")
        _git("commit", "-q", "-m", "fix: patch the first thing")

        task_id = "wo-20260701-fixtask-abcdef"
        self._save_plan(task_id, [{
            "id": "p1", "goal": "g", "agent": "dba", "skills": [],
            "status": "done", "agent_task_id": None,
            "return": {"ok": True, "files_touched": ["a.txt"]}, "assessment": None,
        }])

        r = self._run("--auto", task_id, "--state-dir", str(self.state),
                      "--metrics-dir", str(self.metrics), "--repo", repo)
        self.assertEqual(r.returncode, 0, r.stderr)

        scores = [rec for rec in self._newest_shard_records()
                  if rec["kind"] == "score"
                  and rec["task_id"] == "session-" + task_id]
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0]["scales"]["rework"], "minor")
        self.assertEqual(scores[0]["scales"]["evidence"], "asserted")


if __name__ == "__main__":
    unittest.main()
