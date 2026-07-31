#!/usr/bin/env python3
"""Tests for plan_task.py — the work-order lifecycle (DECOMPOSE, ASSIGN, LOG).

Hermetic: every test builds its own role fixtures and state directory in a
tempdir, so the suite never reads the live ~/.claude tree.
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

import plan_task as pt  # noqa: E402

ROLE_DATA_ENGINEER = """---
name: data-engineer
description: Data pipelines.
role: data-engineer
routes:
  - pipeline · DAG · Airflow · orchestration · backfill
skills:
  - airflow-dag-authoring
  - idempotent-backfill-authoring
mcps:
  - postgres-readonly
---
# data-engineer
"""

ROLE_DBA = """---
name: dba
description: Database administration.
role: dba
routes:
  - slow query · EXPLAIN ANALYZE · query plan · index
skills:
  - explain-analyze-query-tuning
mcps:
  - postgres-readonly
---
# dba
"""

PLAN_DOC = """# Some Plan

## Global Constraints

Stuff.

## Group One (Tasks 1-2)

### Task 1: Build the parser module

Body text here.

### Task 2: Wire the CLI surface

More body text.

## Self-Review

Not a task heading.
"""


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.roles = pathlib.Path(self.tmp) / "roles"
        self.roles.mkdir()
        (self.roles / "data-engineer.md").write_text(ROLE_DATA_ENGINEER)
        (self.roles / "dba.md").write_text(ROLE_DBA)
        self.state = pathlib.Path(self.tmp) / "state"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestPlanId(unittest.TestCase):
    def test_deterministic_for_same_inputs(self):
        a = pt.plan_id("rebuild the dashboard", "2026-07-30T00:00:00Z")
        b = pt.plan_id("rebuild the dashboard", "2026-07-30T00:00:00Z")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("wo-20260730-rebuild-the-dashboard-"), a)

    def test_differs_when_task_differs(self):
        a = pt.plan_id("task one", "2026-07-30T00:00:00Z")
        b = pt.plan_id("task two", "2026-07-30T00:00:00Z")
        self.assertNotEqual(a, b)

    def test_differs_when_timestamp_differs(self):
        a = pt.plan_id("same task", "2026-07-30T00:00:00Z")
        b = pt.plan_id("same task", "2026-07-30T00:00:01Z")
        self.assertNotEqual(a, b)

    def test_slug_is_bounded_and_safe(self):
        pid = pt.plan_id("A task with / slashes and CAPS and lots of extra words here", "2026-07-30T00:00:00Z")
        self.assertNotIn("/", pid)
        self.assertEqual(pid, pid.lower())
        self.assertLessEqual(len(pid), 80)

    def test_empty_task_still_yields_an_id(self):
        pid = pt.plan_id("", "2026-07-30T00:00:00Z")
        self.assertTrue(pid.startswith("wo-20260730-"))


class TestCreativeGate(unittest.TestCase):
    def test_creative_tasks_detected(self):
        for t in ("build a new dashboard component",
                  "redesign the report layout",
                  "implement the caching layer",
                  "write a new skill for the registry"):
            self.assertTrue(pt.is_creative(t), t)

    def test_mechanical_tasks_not_creative(self):
        for t in ("count the rows in the export",
                  "rename the fixture files",
                  "list every branch on the remote"):
            self.assertFalse(pt.is_creative(t), t)

    def test_creative_direct_source_refused(self):
        with self.assertRaises(pt.CreativeTaskRefused):
            pt.create("build a new skill", source="direct", plan_doc=None,
                      force=False, project="p", branch="b")

    def test_refusal_names_both_superpowers(self):
        try:
            pt.create("design a new architecture", source="direct", plan_doc=None,
                      force=False, project="p", branch="b")
        except pt.CreativeTaskRefused as exc:
            msg = str(exc)
            self.assertIn("superpowers:brainstorming", msg)
            self.assertIn("superpowers:writing-plans", msg)
        else:
            self.fail("expected CreativeTaskRefused")

    def test_force_records_the_override(self):
        wo = pt.create("build a new skill", source="direct", plan_doc=None,
                       force=True, project="p", branch="b")
        self.assertTrue(wo["forced"])
        self.assertEqual(wo["source"], "direct")

    def test_plan_source_needs_no_force(self):
        wo = pt.create("build a new skill", source="plan", plan_doc="d.md",
                       force=False, project="p", branch="b")
        self.assertFalse(wo["forced"])
        self.assertEqual(wo["plan_doc"], "d.md")

    def test_mechanical_direct_source_allowed(self):
        wo = pt.create("count the rows in the export", source="direct",
                       plan_doc=None, force=False, project="p", branch="b")
        self.assertEqual(wo["source"], "direct")


class TestPlanDocParse(unittest.TestCase):
    def test_extracts_task_headings_in_order(self):
        self.assertEqual(pt.parse_plan_doc(PLAN_DOC),
                         ["Build the parser module", "Wire the CLI surface"])

    def test_ignores_non_task_headings(self):
        self.assertNotIn("Self-Review", " ".join(pt.parse_plan_doc(PLAN_DOC)))

    def test_no_headings_is_an_error(self):
        with self.assertRaises(pt.PlanParseError):
            pt.parse_plan_doc("# Plan\nno task headings here\n")

    def test_empty_document_is_an_error(self):
        with self.assertRaises(pt.PlanParseError):
            pt.parse_plan_doc("")


class TestSchemaGuard(TempCase):
    def test_unknown_schema_rejected(self):
        self.state.mkdir(parents=True)
        bad = self.state / "wo-bad.json"
        bad.write_text(json.dumps({"schema": 99, "plan_id": "wo-bad", "parts": []}))
        with self.assertRaises(pt.WorkOrderError):
            pt.load(str(self.state), "wo-bad")

    def test_missing_work_order_rejected(self):
        self.state.mkdir(parents=True)
        with self.assertRaises(pt.WorkOrderError):
            pt.load(str(self.state), "wo-nope")

    def test_malformed_json_rejected(self):
        self.state.mkdir(parents=True)
        (self.state / "wo-bad.json").write_text("{not json")
        with self.assertRaises(pt.WorkOrderError):
            pt.load(str(self.state), "wo-bad")

    def test_round_trip(self):
        wo = pt.create("count the rows", source="direct", plan_doc=None,
                       force=False, project="p", branch="b")
        wo["parts"] = [{"part_id": "p1", "goal": "g", "status": "pending"}]
        pt.save(str(self.state), wo)
        back = pt.load(str(self.state), wo["plan_id"])
        self.assertEqual(back["parts"][0]["goal"], "g")


class TestAssign(TempCase):
    def _wo(self, goals):
        return {"schema": pt.SCHEMA, "plan_id": "wo-x", "task": "t",
                "parts": [{"part_id": "p%d" % (i + 1), "goal": g, "status": "pending"}
                          for i, g in enumerate(goals)]}

    def test_each_part_routed_independently(self):
        wo = self._wo(["author an Airflow DAG with a backfill",
                       "run EXPLAIN ANALYZE on the slow query"])
        pt.assign(wo, roles_dir=str(self.roles))
        self.assertEqual(wo["parts"][0]["role"], "data-engineer")
        self.assertEqual(wo["parts"][1]["role"], "dba")

    def test_assign_sets_status_and_skills(self):
        wo = self._wo(["author an Airflow DAG with a backfill"])
        pt.assign(wo, roles_dir=str(self.roles))
        p = wo["parts"][0]
        self.assertEqual(p["status"], "assigned")
        self.assertIn("airflow-dag-authoring", p["skills"])
        self.assertGreater(p["role_score"], 0)

    def test_unroutable_part_is_generalist_with_no_skills(self):
        wo = self._wo(["zzz"])
        pt.assign(wo, roles_dir=str(self.roles))
        self.assertEqual(wo["parts"][0]["role"], "generalist")
        self.assertEqual(wo["parts"][0]["skills"], [])

    def test_assign_is_idempotent(self):
        wo = self._wo(["author an Airflow DAG with a backfill"])
        pt.assign(wo, roles_dir=str(self.roles))
        first = json.dumps(wo, sort_keys=True)
        pt.assign(wo, roles_dir=str(self.roles))
        self.assertEqual(first, json.dumps(wo, sort_keys=True))

    def test_assign_does_not_reopen_a_done_part(self):
        wo = self._wo(["author an Airflow DAG with a backfill"])
        wo["parts"][0]["status"] = "done"
        pt.assign(wo, roles_dir=str(self.roles))
        self.assertEqual(wo["parts"][0]["status"], "done")


class TestModelTier(unittest.TestCase):
    def test_creation_routes_to_opus(self):
        self.assertEqual(pt.model_for("write the report narrative"), "opus")
        self.assertEqual(pt.model_for("implement the parser"), "opus")

    def test_mechanical_routes_to_sonnet(self):
        self.assertEqual(pt.model_for("extract the ids and count them"), "sonnet")
        self.assertEqual(pt.model_for("rename every fixture file"), "sonnet")

    def test_planning_routes_to_session(self):
        self.assertEqual(pt.model_for("review the architecture and synthesize"), "session")

    def test_no_match_defaults_to_session(self):
        self.assertEqual(pt.model_for("zzz"), "session")

    def test_tie_breaks_toward_the_more_capable_tier(self):
        # "write" (creation, 1) and "count" (mechanical, 1) tie -> opus wins.
        self.assertEqual(pt.model_for("write and count"), "opus")


class TestLog(unittest.TestCase):
    def _wo(self):
        return {"schema": pt.SCHEMA, "plan_id": "wo-x", "task": "t",
                "parts": [{"part_id": "p1", "goal": "g", "status": "assigned"}]}

    def test_log_sets_done(self):
        wo = self._wo()
        pt.log_part(wo, "p1", {"ok": True, "summary": "did it"})
        self.assertEqual(wo["parts"][0]["status"], "done")
        self.assertEqual(wo["parts"][0]["log"]["summary"], "did it")

    def test_log_ok_false_sets_failed(self):
        wo = self._wo()
        pt.log_part(wo, "p1", {"ok": False, "summary": "blocked"})
        self.assertEqual(wo["parts"][0]["status"], "failed")

    def test_log_missing_ok_is_failed_not_done(self):
        # A log that does not assert success must never be read as success.
        wo = self._wo()
        pt.log_part(wo, "p1", {"summary": "ambiguous"})
        self.assertEqual(wo["parts"][0]["status"], "failed")

    def test_log_records_agent_task_id(self):
        wo = self._wo()
        pt.log_part(wo, "p1", {"ok": True, "agent_task_id": "agent-abc"})
        self.assertEqual(wo["parts"][0]["agent_task_id"], "agent-abc")

    def test_unknown_part_id_raises(self):
        with self.assertRaises(KeyError):
            pt.log_part(self._wo(), "nope", {"ok": True})


class TestCli(TempCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "plan_task.py"), "--state-dir",
             str(self.state), "--roles-dir", str(self.roles)] + list(args),
            capture_output=True, text=True)

    def test_new_mechanical_task_succeeds(self):
        r = self._run("--new", "count the rows in the export")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("wo-", r.stdout)

    def test_new_creative_task_exits_3(self):
        r = self._run("--new", "build a new dashboard")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("superpowers:brainstorming", r.stderr)

    def test_new_creative_task_with_force_succeeds(self):
        r = self._run("--new", "build a new dashboard", "--force")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_from_plan_creates_parts(self):
        doc = pathlib.Path(self.tmp) / "plan.md"
        doc.write_text(PLAN_DOC)
        r = self._run("--from-plan", str(doc), "--task", "the whole thing")
        self.assertEqual(r.returncode, 0, r.stderr)
        pid = r.stdout.strip().splitlines()[0].split()[-1]
        wo = pt.load(str(self.state), pid)
        self.assertEqual(len(wo["parts"]), 2)
        self.assertEqual(wo["source"], "plan")

    def test_from_plan_with_no_headings_fails(self):
        doc = pathlib.Path(self.tmp) / "empty.md"
        doc.write_text("# nothing here\n")
        r = self._run("--from-plan", str(doc), "--task", "t")
        self.assertNotEqual(r.returncode, 0)

    def test_classify_reports_a_creative_prompt(self):
        r = self._run("--classify", "build a new coach dashboard")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertTrue(d["creative"])
        self.assertGreaterEqual(d["score"], d["threshold"])

    def test_classify_reports_a_conversational_prompt(self):
        d = json.loads(self._run("--classify", "what did that error mean").stdout)
        self.assertFalse(d["creative"])

    def test_classify_writes_no_state(self):
        # The gate hook calls this on every prompt; it must not create files.
        before = sorted(p.name for p in pathlib.Path(self.tmp).rglob("*"))
        self._run("--classify", "build a new coach dashboard")
        self.assertEqual(before, sorted(p.name for p in pathlib.Path(self.tmp).rglob("*")))

    def test_classify_handles_empty_text(self):
        r = self._run("--classify", "")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(json.loads(r.stdout)["creative"])

    def test_show_renders_the_work_order(self):
        r = self._run("--new", "count the rows in the export")
        pid = r.stdout.strip().splitlines()[0].split()[-1]
        r2 = self._run("--show", pid)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn(pid, r2.stdout)


if __name__ == "__main__":
    unittest.main()
