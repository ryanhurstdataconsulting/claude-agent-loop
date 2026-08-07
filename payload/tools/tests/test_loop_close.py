#!/usr/bin/env python3
"""Tests for loop_close.py — unattended link, assess, emit, and mark.

This tool runs from a hook with nobody watching, so the tests care most about
the ways it could quietly do the wrong thing: closing an unfinished plan,
double-counting a closed one, or emitting a record that claims success it
cannot evidence.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import loop_close as lc  # noqa: E402
import plan_task as pt  # noqa: E402


def plan(task_id="wo-20260730-x-111111", statuses=("done",), **over):
    d = {
        "schema": pt.SCHEMA, "task_id": task_id, "task": "t", "source": "plan",
        "created": "2026-07-30T18:00:00Z", "project": "proj", "git_branch": "main",
        "steps": [{"id": "p%d" % (i + 1), "goal": "goal %d" % (i + 1),
                   "status": s, "agent": "dba", "agent_score": 4,
                   "skills": ["explain-analyze-query-tuning"], "model": "sonnet",
                   "agent_task_id": None, "return": {"ok": s == "done"},
                   "assessment": None}
                  for i, s in enumerate(statuses)],
    }
    d.update(over)
    return d


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base_dir = str(pathlib.Path(self.tmp) / "plans")
        self.metrics_dir = str(pathlib.Path(self.tmp) / "metrics")
        self.projects_dir = str(pathlib.Path(self.tmp) / "projects")
        pathlib.Path(self.metrics_dir).mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def shard_rows(self):
        rows = []
        for f in pathlib.Path(self.metrics_dir).glob("*.jsonl"):
            for line in f.read_text().splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def make_transcript(self, agent_id, body):
        d = pathlib.Path(self.projects_dir) / "someproj" / "sid" / "subagents"
        d.mkdir(parents=True, exist_ok=True)
        (d / ("%s.jsonl" % agent_id)).write_text(json.dumps({"text": body}) + "\n")


class TestReadiness(unittest.TestCase):
    def test_all_terminal_is_ready(self):
        self.assertTrue(lc.is_ready(plan(statuses=("done", "failed"))))

    def test_an_open_part_is_not_ready(self):
        self.assertFalse(lc.is_ready(plan(statuses=("done", "pending"))))

    def test_pending_part_is_not_ready(self):
        self.assertFalse(lc.is_ready(plan(statuses=("pending",))))

    def test_no_parts_is_not_ready(self):
        self.assertFalse(lc.is_ready(plan(statuses=())))

    def test_closed_detection(self):
        self.assertFalse(lc.is_closed(plan()))
        self.assertTrue(lc.is_closed(plan(closed_at="2026-07-30T19:00:00Z")))


class TestLink(TempCase):
    def test_links_part_to_its_transcript(self):
        self.make_transcript("agent-abc123", "task_id : wo-20260730-x-111111  step_id : p1 ...")
        w = plan()
        self.assertEqual(lc.link(w, self.projects_dir), 1)
        self.assertEqual(w["steps"][0]["agent_task_id"], "agent-abc123")

    def test_requires_both_identifiers(self):
        # A transcript naming p1 but a DIFFERENT task_id must not match.
        self.make_transcript("agent-wrong", "task_id : wo-20260730-other-222222  step_id : p1")
        w = plan()
        self.assertEqual(lc.link(w, self.projects_dir), 0)
        self.assertIsNone(w["steps"][0]["agent_task_id"])

    def test_no_transcript_leaves_it_unlinked(self):
        w = plan()
        self.assertEqual(lc.link(w, self.projects_dir), 0)
        self.assertIsNone(w["steps"][0]["agent_task_id"])

    def test_existing_link_is_not_overwritten(self):
        self.make_transcript("agent-new", "task_id : wo-20260730-x-111111 step_id : p1")
        w = plan()
        w["steps"][0]["agent_task_id"] = "agent-original"
        self.assertEqual(lc.link(w, self.projects_dir), 0)
        self.assertEqual(w["steps"][0]["agent_task_id"], "agent-original")

    def test_missing_projects_dir_is_survivable(self):
        w = plan()
        self.assertEqual(lc.link(w, self.projects_dir + "-gone"), 0)


class TestRecords(unittest.TestCase):
    def test_source_is_workorder_not_scraped(self):
        w = plan()
        w["steps"][0]["assessment"] = {
            "evidence": {"tests_detected": True, "tests_passed": 2,
                         "tests_failed": 0, "error_rate": 0.0},
            "verdict": "clean"}
        rec = lc.task_records(w)[0]
        self.assertEqual(rec["resources_source"], "workorder")
        self.assertEqual(rec["kind"], "task")

    def test_resources_carry_role_and_skills(self):
        rec = lc.task_records(plan())[0]
        self.assertIn("dba", rec["resources_deployed"])
        self.assertIn("explain-analyze-query-tuning", rec["resources_deployed"])

    def test_generalist_role_is_not_recorded_as_a_resource(self):
        w = plan()
        w["steps"][0]["agent"] = "generalist"
        w["steps"][0]["skills"] = []
        rec = lc.task_records(w)[0]
        self.assertEqual(rec["resources_deployed"], [])
        self.assertTrue(rec["bare"])

    def test_skills_the_agent_reported_are_merged_in(self):
        w = plan()
        w["steps"][0]["return"] = {"ok": True, "skills_used": ["token-efficiency"]}
        self.assertIn("token-efficiency", lc.task_records(w)[0]["resources_deployed"])

    def test_falls_back_to_a_synthetic_task_id_when_unlinked(self):
        rec = lc.task_records(plan())[0]
        self.assertEqual(rec["task_id"], "wo-20260730-x-111111-p1")


class TestCloseOne(TempCase):
    def test_emits_one_record_per_part_and_stamps(self):
        w = plan(statuses=("done", "done"))
        s = lc.close_one(w, self.metrics_dir, self.projects_dir)
        self.assertEqual(s["parts"], 2)
        rows = self.shard_rows()
        task_rows = [r for r in rows if r["kind"] == "task"]
        run_rows = [r for r in rows if r["kind"] == "run"]
        self.assertEqual(len(task_rows), 2)
        self.assertEqual(len(run_rows), 2)
        self.assertTrue(w.get("closed_at"))

    def test_dry_run_emits_nothing_and_does_not_stamp(self):
        w = plan()
        lc.close_one(w, self.metrics_dir, self.projects_dir, dry_run=True)
        self.assertEqual(self.shard_rows(), [])
        self.assertIsNone(w.get("closed_at"))

    def test_unmeasured_part_records_unknown_not_clean(self):
        w = plan()
        lc.close_one(w, self.metrics_dir, self.projects_dir)
        self.assertEqual(w["steps"][0]["assessment"]["verdict"], "unknown")
        self.assertEqual(self.shard_rows()[0]["verdict"], "unknown")

    def test_failed_part_records_dirty(self):
        w = plan(statuses=("failed",))
        lc.close_one(w, self.metrics_dir, self.projects_dir)
        self.assertEqual(w["steps"][0]["assessment"]["verdict"], "dirty")

    def test_verdict_counts_are_summarised(self):
        w = plan(statuses=("done", "failed"))
        s = lc.close_one(w, self.metrics_dir, self.projects_dir)
        self.assertEqual(s["verdicts"].get("dirty"), 1)


class TestReadyScan(TempCase):
    def test_scan_skips_open_and_closed(self):
        pt.save(self.base_dir, plan(task_id="wo-20260730-ready-100001", statuses=("done",)))
        pt.save(self.base_dir, plan(task_id="wo-20260730-open-100002", statuses=("pending",)))
        pt.save(self.base_dir, plan(task_id="wo-20260730-done-100003", statuses=("done",),
                                    closed_at="2026-07-30T19:00:00Z"))
        ids = [w["task_id"] for w in lc.ready_plans(self.base_dir)]
        self.assertEqual(ids, ["wo-20260730-ready-100001"])

    def test_missing_state_dir_is_empty_not_an_error(self):
        self.assertEqual(lc.ready_plans(self.base_dir + "-gone"), [])

    def test_malformed_work_order_is_skipped_not_fatal(self):
        d = pathlib.Path(self.base_dir) / "2026-07-30"
        d.mkdir(parents=True, exist_ok=True)
        (d / "wo-20260730-bad-100004.json").write_text("{not json")
        pt.save(self.base_dir, plan(task_id="wo-20260730-ok-100005", statuses=("done",)))
        ids = [w["task_id"] for w in lc.ready_plans(self.base_dir)]
        self.assertEqual(ids, ["wo-20260730-ok-100005"])


class TestRunRecordsSubagent(unittest.TestCase):
    """kind:"run" (subagent) emission — Phase 2."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.metrics_dir = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _shard_lines(self):
        shards = list(self.metrics_dir.glob("*.jsonl"))
        self.assertEqual(len(shards), 1)
        return [json.loads(l) for l in shards[0].read_text().splitlines() if l.strip()]

    def test_one_run_record_per_part_success(self):
        w = plan(task_id="wo-20260730-1-100010", statuses=("done",))
        w["steps"][0]["agent_task_id"] = "agent-aaa"
        w["steps"][0]["assessment"] = {
            "evidence": {"tests_detected": True, "tests_passed": 5,
                         "tests_failed": 0, "commits": 1},
            "verdict": "clean"}
        records = lc.run_records(w)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["schema"], "run.v1")
        self.assertEqual(rec["kind"], "run")
        self.assertEqual(rec["run_kind"], "subagent")
        self.assertEqual(rec["task_id"], "agent-aaa")
        self.assertEqual(rec["outcome"], "success")
        self.assertEqual(rec["stop_reason"], "completed")
        self.assertEqual(rec["plan_id"], "wo-20260730-1-100010")
        self.assertEqual(rec["part_id"], "p1")
        self.assertIsNone(rec["parent_task_id"])
        self.assertIsInstance(rec["trace_id"], str)
        self.assertEqual(len(rec["trace_id"]), 32)

    def test_outcome_failure_on_test_failures(self):
        w = plan(task_id="wo-20260730-1-100011", statuses=("done",))
        w["steps"][0]["agent_task_id"] = "agent-bbb"
        w["steps"][0]["assessment"] = {
            "evidence": {"tests_detected": True, "tests_passed": 2, "tests_failed": 3},
            "verdict": "dirty"}
        rec = lc.run_records(w)[0]
        self.assertEqual(rec["outcome"], "failure")

    def test_outcome_partial_on_soft_dirty_signal_only(self):
        w = plan(task_id="wo-20260730-1-100012", statuses=("done",))
        w["steps"][0]["agent_task_id"] = "agent-ccc"
        w["steps"][0]["assessment"] = {
            "evidence": {"followup_fixes": 1}, "verdict": "dirty"}
        rec = lc.run_records(w)[0]
        self.assertEqual(rec["outcome"], "partial")

    def test_outcome_partial_on_unknown_verdict(self):
        w = plan(task_id="wo-20260730-1-100013", statuses=("done",))
        w["steps"][0]["agent_task_id"] = "agent-ddd"
        w["steps"][0]["assessment"] = {"evidence": {}, "verdict": "unknown"}
        rec = lc.run_records(w)[0]
        self.assertEqual(rec["outcome"], "partial")

    def test_trace_id_matches_obs_emit_for_same_plan_id(self):
        import obs_emit
        w = plan(task_id="wo-20260730-shared-100014", statuses=("done",))
        w["steps"][0]["agent_task_id"] = "agent-eee"
        w["steps"][0]["assessment"] = {"evidence": {}, "verdict": "clean"}
        rec = lc.run_records(w)[0]
        self.assertEqual(rec["trace_id"], obs_emit.trace_id_for("wo-20260730-shared-100014"))

    def test_emit_writes_run_records_into_shard(self):
        w = plan(task_id="wo-20260730-1-100015", statuses=("done",))
        w["steps"][0]["agent_task_id"] = "agent-fff"
        w["steps"][0]["assessment"] = {"evidence": {}, "verdict": "clean"}
        records = lc.task_records(w) + lc.run_records(w)
        lc.emit(str(self.metrics_dir), records)
        lines = self._shard_lines()
        kinds = sorted(r["kind"] for r in lines)
        self.assertEqual(kinds, ["run", "task"])


class TestReadyPlansScansDatePartitions(TempCase):
    def _write_ready_plan(self, base, date, task_id):
        w = plan(task_id=task_id, statuses=("done",))
        # pt.save() derives the date directory from the task_id itself, so
        # the caller-supplied `date` must agree with the id's embedded date.
        pt.save(base, w)

    def test_scans_every_date_subdirectory(self):
        with tempfile.TemporaryDirectory() as base:
            self._write_ready_plan(base, "2026-08-05", "wo-20260805-a-111111")
            self._write_ready_plan(base, "2026-08-06", "wo-20260806-b-222222")
            found = lc.ready_plans(base)
            self.assertEqual({p["task_id"] for p in found},
                             {"wo-20260805-a-111111", "wo-20260806-b-222222"})

    def test_missing_base_dir_is_empty_not_an_error(self):
        self.assertEqual(lc.ready_plans("/no/such/dir"), [])


class TestCloseOneUsesAutoAssess(TempCase):
    def _ready_plan_one_step(self):
        return plan(task_id="wo-20260806-c-333333", statuses=("done",))

    def test_close_one_populates_assessment_via_score_task(self):
        w = self._ready_plan_one_step()
        lc.close_one(w, self.metrics_dir, self.projects_dir)
        self.assertIsNotNone(w["steps"][0]["assessment"])


class TestNoDoubleCount(TempCase):
    def test_second_close_all_emits_nothing_further(self):
        pt.save(self.base_dir, plan(task_id="wo-20260730-1-100020", statuses=("done",)))
        lc.main(["--all", "--base-dir", self.base_dir, "--metrics-dir", self.metrics_dir,
                 "--projects-dir", self.projects_dir])
        first = len(self.shard_rows())
        lc.main(["--all", "--base-dir", self.base_dir, "--metrics-dir", self.metrics_dir,
                 "--projects-dir", self.projects_dir])
        self.assertEqual(len(self.shard_rows()), first)


class TestCli(TempCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "loop_close.py"), "--base-dir", self.base_dir,
             "--metrics-dir", self.metrics_dir, "--projects-dir", self.projects_dir] + list(args),
            capture_output=True, text=True)

    def test_all_with_nothing_ready_is_quiet_success(self):
        r = self._run("--all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing ready", r.stdout)

    def test_all_closes_and_reports(self):
        pt.save(self.base_dir, plan(task_id="wo-20260730-cli-100021", statuses=("done",)))
        r = self._run("--all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("closed wo-20260730-cli-100021", r.stdout)

    def test_unknown_plan_id_exits_nonzero(self):
        self.assertNotEqual(self._run("wo-20260730-nope-999999").returncode, 0)

    def test_already_closed_exits_nonzero(self):
        pt.save(self.base_dir, plan(task_id="wo-20260730-c-100022", statuses=("done",),
                                    closed_at="2026-07-30T19:00:00Z"))
        self.assertNotEqual(self._run("wo-20260730-c-100022").returncode, 0)

    def test_json_output_parses(self):
        pt.save(self.base_dir, plan(task_id="wo-20260730-j-100023", statuses=("done",)))
        r = self._run("--all", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)[0]["plan_id"], "wo-20260730-j-100023")


if __name__ == "__main__":
    unittest.main()
