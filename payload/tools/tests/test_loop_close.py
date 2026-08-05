#!/usr/bin/env python3
"""Tests for loop_close.py — unattended link, assess, emit, and mark.

This tool runs from a hook with nobody watching, so the tests care most about
the ways it could quietly do the wrong thing: closing an unfinished work order,
double-counting a closed one, or emitting a record that claims success it cannot
evidence.
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


def wo(plan_id="wo-x", statuses=("done",), **over):
    d = {
        "schema": pt.SCHEMA, "plan_id": plan_id, "task": "t", "source": "plan",
        "created": "2026-07-30T18:00:00Z", "project": "proj", "git_branch": "main",
        "parts": [{"part_id": "p%d" % (i + 1), "goal": "goal %d" % (i + 1),
                   "status": s, "role": "dba", "role_score": 4,
                   "skills": ["explain-analyze-query-tuning"], "model": "sonnet",
                   "agent_task_id": None, "log": {"ok": s == "done"},
                   "evidence": None, "verdict": None, "score": None}
                  for i, s in enumerate(statuses)],
    }
    d.update(over)
    return d


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state = str(pathlib.Path(self.tmp) / "state")
        self.metrics = str(pathlib.Path(self.tmp) / "metrics")
        self.projects = str(pathlib.Path(self.tmp) / "projects")
        pathlib.Path(self.metrics).mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def shard_rows(self):
        rows = []
        for f in pathlib.Path(self.metrics).glob("*.jsonl"):
            for line in f.read_text().splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def make_transcript(self, agent_id, body):
        d = pathlib.Path(self.projects) / "someproj" / "sid" / "subagents"
        d.mkdir(parents=True, exist_ok=True)
        (d / ("%s.jsonl" % agent_id)).write_text(json.dumps({"text": body}) + "\n")


class TestReadiness(unittest.TestCase):
    def test_all_terminal_is_ready(self):
        self.assertTrue(lc.is_ready(wo(statuses=("done", "failed"))))

    def test_an_open_part_is_not_ready(self):
        self.assertFalse(lc.is_ready(wo(statuses=("done", "assigned"))))

    def test_pending_part_is_not_ready(self):
        self.assertFalse(lc.is_ready(wo(statuses=("pending",))))

    def test_no_parts_is_not_ready(self):
        self.assertFalse(lc.is_ready(wo(statuses=())))

    def test_closed_detection(self):
        self.assertFalse(lc.is_closed(wo()))
        self.assertTrue(lc.is_closed(wo(closed_at="2026-07-30T19:00:00Z")))


class TestLink(TempCase):
    def test_links_part_to_its_transcript(self):
        self.make_transcript("agent-abc123", "plan_id : wo-x  part_id : p1 ...")
        w = wo()
        self.assertEqual(lc.link(w, self.projects), 1)
        self.assertEqual(w["parts"][0]["agent_task_id"], "agent-abc123")

    def test_requires_both_identifiers(self):
        # A transcript naming p1 but a DIFFERENT plan must not match.
        self.make_transcript("agent-wrong", "plan_id : wo-other  part_id : p1")
        w = wo()
        self.assertEqual(lc.link(w, self.projects), 0)
        self.assertIsNone(w["parts"][0]["agent_task_id"])

    def test_no_transcript_leaves_it_unlinked(self):
        w = wo()
        self.assertEqual(lc.link(w, self.projects), 0)
        self.assertIsNone(w["parts"][0]["agent_task_id"])

    def test_existing_link_is_not_overwritten(self):
        self.make_transcript("agent-new", "plan_id : wo-x part_id : p1")
        w = wo()
        w["parts"][0]["agent_task_id"] = "agent-original"
        self.assertEqual(lc.link(w, self.projects), 0)
        self.assertEqual(w["parts"][0]["agent_task_id"], "agent-original")

    def test_missing_projects_dir_is_survivable(self):
        w = wo()
        self.assertEqual(lc.link(w, self.projects + "-gone"), 0)


class TestRecords(unittest.TestCase):
    def test_source_is_workorder_not_scraped(self):
        w = wo()
        w["parts"][0]["evidence"] = {"tests_detected": True, "tests_passed": 2,
                                     "tests_failed": 0, "error_rate": 0.0}
        rec = lc.task_records(w)[0]
        self.assertEqual(rec["resources_source"], "workorder")
        self.assertEqual(rec["kind"], "task")

    def test_resources_carry_role_and_skills(self):
        rec = lc.task_records(wo())[0]
        self.assertIn("dba", rec["resources_deployed"])
        self.assertIn("explain-analyze-query-tuning", rec["resources_deployed"])

    def test_generalist_role_is_not_recorded_as_a_resource(self):
        w = wo()
        w["parts"][0]["role"] = "generalist"
        w["parts"][0]["skills"] = []
        rec = lc.task_records(w)[0]
        self.assertEqual(rec["resources_deployed"], [])
        self.assertTrue(rec["bare"])

    def test_skills_the_agent_reported_are_merged_in(self):
        w = wo()
        w["parts"][0]["log"] = {"ok": True, "skills_used": ["token-efficiency"]}
        self.assertIn("token-efficiency", lc.task_records(w)[0]["resources_deployed"])

    def test_falls_back_to_a_synthetic_task_id_when_unlinked(self):
        rec = lc.task_records(wo())[0]
        self.assertEqual(rec["task_id"], "wo-x-p1")


class TestCloseOne(TempCase):
    def test_emits_one_record_per_part_and_stamps(self):
        w = wo(statuses=("done", "done"))
        s = lc.close_one(w, self.metrics, self.projects)
        self.assertEqual(s["parts"], 2)
        rows = self.shard_rows()
        task_rows = [r for r in rows if r["kind"] == "task"]
        run_rows = [r for r in rows if r["kind"] == "run"]
        self.assertEqual(len(task_rows), 2)
        self.assertEqual(len(run_rows), 2)
        self.assertTrue(w.get("closed_at"))

    def test_dry_run_emits_nothing_and_does_not_stamp(self):
        w = wo()
        lc.close_one(w, self.metrics, self.projects, dry_run=True)
        self.assertEqual(self.shard_rows(), [])
        self.assertIsNone(w.get("closed_at"))

    def test_unmeasured_part_records_unknown_not_clean(self):
        w = wo()
        lc.close_one(w, self.metrics, self.projects)
        self.assertEqual(w["parts"][0]["verdict"], "unknown")
        self.assertEqual(self.shard_rows()[0]["verdict"], "unknown")

    def test_failed_part_records_dirty(self):
        w = wo(statuses=("failed",))
        lc.close_one(w, self.metrics, self.projects)
        self.assertEqual(w["parts"][0]["verdict"], "dirty")

    def test_verdict_counts_are_summarised(self):
        w = wo(statuses=("done", "failed"))
        s = lc.close_one(w, self.metrics, self.projects)
        self.assertEqual(s["verdicts"].get("dirty"), 1)


class TestReadyScan(TempCase):
    def test_scan_skips_open_and_closed(self):
        pt.save(self.state, wo(plan_id="wo-ready", statuses=("done",)))
        pt.save(self.state, wo(plan_id="wo-open", statuses=("assigned",)))
        pt.save(self.state, wo(plan_id="wo-done", statuses=("done",),
                               closed_at="2026-07-30T19:00:00Z"))
        ids = [w["plan_id"] for w in lc.ready_work_orders(self.state)]
        self.assertEqual(ids, ["wo-ready"])

    def test_missing_state_dir_is_empty_not_an_error(self):
        self.assertEqual(lc.ready_work_orders(self.state + "-gone"), [])

    def test_malformed_work_order_is_skipped_not_fatal(self):
        pathlib.Path(self.state).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(self.state) / "wo-bad.json").write_text("{not json")
        pt.save(self.state, wo(plan_id="wo-ok", statuses=("done",)))
        ids = [w["plan_id"] for w in lc.ready_work_orders(self.state)]
        self.assertEqual(ids, ["wo-ok"])


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
        w = wo(plan_id="wo-1", statuses=("done",))
        w["parts"][0]["agent_task_id"] = "agent-aaa"
        w["parts"][0]["verdict"] = "clean"
        w["parts"][0]["evidence"] = {"tests_detected": True, "tests_passed": 5,
                                      "tests_failed": 0, "commits": 1}
        records = lc.run_records(w)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["schema"], "run.v1")
        self.assertEqual(rec["kind"], "run")
        self.assertEqual(rec["run_kind"], "subagent")
        self.assertEqual(rec["task_id"], "agent-aaa")
        self.assertEqual(rec["outcome"], "success")
        self.assertEqual(rec["stop_reason"], "completed")
        self.assertEqual(rec["plan_id"], "wo-1")
        self.assertEqual(rec["part_id"], "p1")
        self.assertIsNone(rec["parent_task_id"])
        self.assertIsInstance(rec["trace_id"], str)
        self.assertEqual(len(rec["trace_id"]), 32)

    def test_outcome_failure_on_test_failures(self):
        w = wo(plan_id="wo-1", statuses=("done",))
        w["parts"][0]["agent_task_id"] = "agent-bbb"
        w["parts"][0]["verdict"] = "dirty"
        w["parts"][0]["evidence"] = {"tests_detected": True, "tests_passed": 2,
                                      "tests_failed": 3}
        rec = lc.run_records(w)[0]
        self.assertEqual(rec["outcome"], "failure")

    def test_outcome_partial_on_soft_dirty_signal_only(self):
        w = wo(plan_id="wo-1", statuses=("done",))
        w["parts"][0]["agent_task_id"] = "agent-ccc"
        w["parts"][0]["verdict"] = "dirty"
        w["parts"][0]["evidence"] = {"followup_fixes": 1}
        rec = lc.run_records(w)[0]
        self.assertEqual(rec["outcome"], "partial")

    def test_outcome_partial_on_unknown_verdict(self):
        w = wo(plan_id="wo-1", statuses=("done",))
        w["parts"][0]["agent_task_id"] = "agent-ddd"
        w["parts"][0]["verdict"] = "unknown"
        w["parts"][0]["evidence"] = {}
        rec = lc.run_records(w)[0]
        self.assertEqual(rec["outcome"], "partial")

    def test_trace_id_matches_obs_emit_for_same_plan_id(self):
        import obs_emit
        w = wo(plan_id="wo-shared", statuses=("done",))
        w["parts"][0]["agent_task_id"] = "agent-eee"
        w["parts"][0]["verdict"] = "clean"
        w["parts"][0]["evidence"] = {}
        rec = lc.run_records(w)[0]
        self.assertEqual(rec["trace_id"], obs_emit.trace_id_for("wo-shared"))

    def test_emit_writes_run_records_into_shard(self):
        w = wo(plan_id="wo-1", statuses=("done",))
        w["parts"][0]["agent_task_id"] = "agent-fff"
        w["parts"][0]["verdict"] = "clean"
        w["parts"][0]["evidence"] = {}
        records = lc.task_records(w) + lc.run_records(w)
        lc.emit(str(self.metrics_dir), records)
        lines = self._shard_lines()
        kinds = sorted(r["kind"] for r in lines)
        self.assertEqual(kinds, ["run", "task"])


class TestNoDoubleCount(TempCase):
    def test_second_close_all_emits_nothing_further(self):
        pt.save(self.state, wo(plan_id="wo-1", statuses=("done",)))
        lc.main(["--all", "--state-dir", self.state, "--metrics-dir", self.metrics,
                 "--projects-dir", self.projects])
        first = len(self.shard_rows())
        lc.main(["--all", "--state-dir", self.state, "--metrics-dir", self.metrics,
                 "--projects-dir", self.projects])
        self.assertEqual(len(self.shard_rows()), first)


class TestCli(TempCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "loop_close.py"), "--state-dir", self.state,
             "--metrics-dir", self.metrics, "--projects-dir", self.projects] + list(args),
            capture_output=True, text=True)

    def test_all_with_nothing_ready_is_quiet_success(self):
        r = self._run("--all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing ready", r.stdout)

    def test_all_closes_and_reports(self):
        pt.save(self.state, wo(plan_id="wo-cli", statuses=("done",)))
        r = self._run("--all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("closed wo-cli", r.stdout)

    def test_unknown_plan_id_exits_nonzero(self):
        self.assertNotEqual(self._run("wo-nope").returncode, 0)

    def test_already_closed_exits_nonzero(self):
        pt.save(self.state, wo(plan_id="wo-c", statuses=("done",),
                               closed_at="2026-07-30T19:00:00Z"))
        self.assertNotEqual(self._run("wo-c").returncode, 0)

    def test_json_output_parses(self):
        pt.save(self.state, wo(plan_id="wo-j", statuses=("done",)))
        r = self._run("--all", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)[0]["plan_id"], "wo-j")


if __name__ == "__main__":
    unittest.main()
