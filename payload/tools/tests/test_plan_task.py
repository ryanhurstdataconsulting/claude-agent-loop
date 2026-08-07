#!/usr/bin/env python3
"""Tests for plan_task.py — the plan lifecycle (DECOMPOSE, ASSIGN, BRIEF).

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
    """Hermetic roles + state fixture shared by every test class below."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.roles = pathlib.Path(self.tmp) / "roles"
        self.roles.mkdir()
        (self.roles / "data-engineer.md").write_text(ROLE_DATA_ENGINEER)
        (self.roles / "dba.md").write_text(ROLE_DBA)
        self.roles_dir = str(self.roles)
        self.state = pathlib.Path(self.tmp) / "state"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestPlanId(unittest.TestCase):
    def test_deterministic_for_same_inputs(self):
        a = pt.plan_id("rebuild the dashboard", "2026-08-06T00:00:00Z")
        b = pt.plan_id("rebuild the dashboard", "2026-08-06T00:00:00Z")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("wo-20260806-rebuild-the-dashboard-"))

    def test_differs_when_task_differs(self):
        a = pt.plan_id("task one", "2026-08-06T00:00:00Z")
        b = pt.plan_id("task two", "2026-08-06T00:00:00Z")
        self.assertNotEqual(a, b)

    def test_differs_when_timestamp_differs(self):
        a = pt.plan_id("same task", "2026-08-06T00:00:00Z")
        b = pt.plan_id("same task", "2026-08-06T00:00:01Z")
        self.assertNotEqual(a, b)

    def test_slug_is_bounded_and_safe(self):
        pid = pt.plan_id("A task with / slashes and CAPS and lots of extra words here", "2026-08-06T00:00:00Z")
        self.assertNotIn("/", pid)
        self.assertEqual(pid, pid.lower())
        self.assertLessEqual(len(pid), 80)

    def test_empty_task_still_yields_an_id(self):
        pid = pt.plan_id("", "2026-08-06T00:00:00Z")
        self.assertTrue(pid.startswith("wo-20260806-"))


class TestCreateNoGate(TempCase):
    def test_creative_task_no_longer_refused(self):
        # what used to raise CreativeTaskRefused now just succeeds
        plan = pt.create("build a brand new dashboard component", source="direct",
                          plan_doc=None, project="p", branch="b",
                          roles_dir=self.roles_dir)
        self.assertEqual(plan["schema"], 2)
        self.assertEqual(len(plan["steps"]), 1)

    def test_no_force_kwarg_exists(self):
        import inspect
        self.assertNotIn("force", inspect.signature(pt.create).parameters)

    def test_creative_score_removed(self):
        self.assertFalse(hasattr(pt, "creative_score"))
        self.assertFalse(hasattr(pt, "CreativeTaskRefused"))


class TestCreateAssignsAndBriefs(TempCase):
    # setUp() builds self.roles_dir exactly as TempCase (formerly TestAssign's
    # own setUp) does — the fixture is shared, not duplicated per class.
    def test_new_step_arrives_already_assigned_and_briefed(self):
        plan = pt.create("write the quarterly data pipeline", source="direct",
                          plan_doc=None, project="p", branch="b",
                          roles_dir=self.roles_dir)
        step = plan["steps"][0]
        self.assertIsNotNone(step["agent"])
        self.assertIsInstance(step["brief"], str)
        self.assertIn(plan["task_id"], step["brief"])
        self.assertIn(step["id"], step["brief"])
        self.assertEqual(step["status"], "pending")

    def test_from_plan_creates_one_step_per_heading_all_briefed(self):
        doc = "### Task 1: First thing\n### Task 2: Second thing\n"
        plan = pt.create("parent task", source="plan", plan_doc="doc.md",
                          project="p", branch="b", roles_dir=self.roles_dir,
                          goals=pt.parse_plan_doc(doc))
        self.assertEqual(len(plan["steps"]), 2)
        for step in plan["steps"]:
            self.assertTrue(step["brief"])
            self.assertEqual(step["depends_on"], [])
            self.assertIsNone(step["budget_tokens"])
            self.assertFalse(step["worktree"])

    def test_reasoning_defaults_empty_and_is_settable(self):
        plan = pt.create("a task", source="direct", plan_doc=None, project="p",
                          branch="b", roles_dir=self.roles_dir)
        self.assertEqual(plan["supervisor_reasoning"], "")
        plan2 = pt.create("a task", source="direct", plan_doc=None, project="p",
                          branch="b", roles_dir=self.roles_dir,
                          reasoning="routed to generalist, low ambiguity")
        self.assertEqual(plan2["supervisor_reasoning"],
                         "routed to generalist, low ambiguity")


class TestDatePartitionedPersistence(TempCase):
    def test_round_trip_uses_date_from_task_id(self):
        with tempfile.TemporaryDirectory() as base:
            plan = pt.create("x", source="direct", plan_doc=None, project="p",
                             branch="b", roles_dir=self.roles_dir,
                             created="2026-08-06T12:00:00Z")
            pt.save(base, plan)
            expected = pathlib.Path(base) / "2026-08-06" / (plan["task_id"] + ".json")
            self.assertTrue(expected.is_file())
            loaded = pt.load(base, plan["task_id"])
            self.assertEqual(loaded, plan)

    def test_unknown_schema_rejected(self):
        with tempfile.TemporaryDirectory() as base:
            d = pathlib.Path(base) / "2026-08-06"
            d.mkdir(parents=True)
            (d / "wo-20260806-x-abc123.json").write_text('{"schema": 1, "task_id": "wo-20260806-x-abc123"}')
            with self.assertRaises(pt.WorkOrderError):
                pt.load(base, "wo-20260806-x-abc123")

    def test_missing_plan_rejected(self):
        with tempfile.TemporaryDirectory() as base:
            with self.assertRaises(pt.WorkOrderError):
                pt.load(base, "wo-20260806-nope-000000")

    def test_malformed_json_rejected(self):
        with tempfile.TemporaryDirectory() as base:
            d = pathlib.Path(base) / "2026-08-06"
            d.mkdir(parents=True)
            (d / "wo-20260806-bad-abc123.json").write_text("{not json")
            with self.assertRaises(pt.WorkOrderError):
                pt.load(base, "wo-20260806-bad-abc123")


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


class TestAssign(TempCase):
    def _plan(self, goals):
        return {"schema": pt.SCHEMA, "task_id": "wo-x", "task": "t",
                "steps": [{"id": "p%d" % (i + 1), "goal": g, "status": "pending"}
                          for i, g in enumerate(goals)]}

    def test_each_step_routed_independently(self):
        plan = self._plan(["author an Airflow DAG with a backfill",
                           "run EXPLAIN ANALYZE on the slow query"])
        pt.assign(plan, roles_dir=self.roles_dir)
        self.assertEqual(plan["steps"][0]["agent"], "data-engineer")
        self.assertEqual(plan["steps"][1]["agent"], "dba")

    def test_assign_sets_skills_and_score(self):
        plan = self._plan(["author an Airflow DAG with a backfill"])
        pt.assign(plan, roles_dir=self.roles_dir)
        step = plan["steps"][0]
        self.assertIn("airflow-dag-authoring", step["skills"])
        self.assertGreater(step["agent_score"], 0)

    def test_unroutable_step_is_generalist_with_no_skills(self):
        plan = self._plan(["zzz"])
        pt.assign(plan, roles_dir=self.roles_dir)
        self.assertEqual(plan["steps"][0]["agent"], "generalist")
        self.assertEqual(plan["steps"][0]["skills"], [])

    def test_assign_is_idempotent(self):
        plan = self._plan(["author an Airflow DAG with a backfill"])
        pt.assign(plan, roles_dir=self.roles_dir)
        first = json.dumps(plan, sort_keys=True)
        pt.assign(plan, roles_dir=self.roles_dir)
        self.assertEqual(first, json.dumps(plan, sort_keys=True))

    def test_assign_does_not_reopen_a_done_step(self):
        plan = self._plan(["author an Airflow DAG with a backfill"])
        plan["steps"][0]["status"] = "done"
        pt.assign(plan, roles_dir=self.roles_dir)
        self.assertEqual(plan["steps"][0]["status"], "done")


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


class TestRecordReturn(TempCase):
    def _plan_with_one_step(self):
        return {"schema": pt.SCHEMA, "task_id": "wo-x", "task": "t",
                "steps": [{"id": "S1", "goal": "g", "status": "pending", "return": None, "agent_task_id": None}]}

    def test_record_sets_done_on_ok_true(self):
        plan = self._plan_with_one_step()
        pt.record_return(plan, "S1", {"ok": True, "summary": "did it"})
        self.assertEqual(plan["steps"][0]["status"], "done")
        self.assertEqual(plan["steps"][0]["return"]["summary"], "did it")

    def test_missing_ok_is_failed_not_done(self):
        plan = self._plan_with_one_step()
        pt.record_return(plan, "S1", {"summary": "ambiguous"})
        self.assertEqual(plan["steps"][0]["status"], "failed")

    def test_ok_false_sets_failed(self):
        plan = self._plan_with_one_step()
        pt.record_return(plan, "S1", {"ok": False, "summary": "nope"})
        self.assertEqual(plan["steps"][0]["status"], "failed")

    def test_agent_task_id_captured(self):
        plan = self._plan_with_one_step()
        pt.record_return(plan, "S1", {"ok": True, "agent_task_id": "agent-abc"})
        self.assertEqual(plan["steps"][0]["agent_task_id"], "agent-abc")

    def test_unknown_step_raises(self):
        plan = self._plan_with_one_step()
        with self.assertRaises(KeyError):
            pt.record_return(plan, "S99", {"ok": True})


class TestLoadReturnPayload(TempCase):
    """--json takes a file path OR inline JSON. The shipped pipeline-relay.sh
    directive tells sessions to pass a file; the old code only ever parsed the
    argument as inline JSON, so following the directive failed with exit 2."""

    def test_file_path_is_read_and_parsed(self):
        p = pathlib.Path(self.tmp) / "ret.json"
        p.write_text(json.dumps({"ok": True, "summary": "did it"}))
        self.assertEqual(pt.load_return_payload(str(p)),
                         {"ok": True, "summary": "did it"})

    def test_inline_json_still_parsed(self):
        self.assertEqual(pt.load_return_payload('{"ok": true}'), {"ok": True})

    def test_file_wins_over_inline_reading(self):
        # A path is never also valid JSON, but assert the precedence explicitly
        # so a future reorder cannot silently start parsing the path as text.
        p = pathlib.Path(self.tmp) / "wins.json"
        p.write_text('{"ok": false, "summary": "from the file"}')
        self.assertEqual(pt.load_return_payload(str(p))["summary"],
                         "from the file")

    def test_prose_with_quotes_and_newlines_survives_the_file_path(self):
        # The exact case that breaks shell-quoted inline JSON: a real return's
        # summary/evidence carries quotes, newlines, and backticks.
        payload = {"ok": True,
                   "summary": 'ran `pytest`, saw "3 passed"\nno failures',
                   "evidence": "$ pytest -q\n3 passed in 0.10s\n"}
        p = pathlib.Path(self.tmp) / "prose.json"
        p.write_text(json.dumps(payload))
        self.assertEqual(pt.load_return_payload(str(p)), payload)

    def test_neither_a_file_nor_json_raises_decode_error(self):
        with self.assertRaises(json.JSONDecodeError):
            pt.load_return_payload("/no/such/file.json")

    def test_very_long_inline_json_is_not_treated_as_a_path(self):
        # An argument longer than the OS filename limit must fall through to
        # inline parsing rather than raising ENAMETOOLONG out of is_file().
        payload = {"ok": True, "summary": "x" * 5000}
        self.assertEqual(pt.load_return_payload(json.dumps(payload)), payload)


class TestTermination(TempCase):
    """The spec's plan-level `termination` block — present and inert in Phase 1,
    the same treatment depends_on / budget_tokens / worktree got."""

    def test_termination_present_and_defaulted_on_every_new_plan(self):
        plan = pt.create("count the rows", "direct", None, "proj", "main",
                         self.roles_dir)
        self.assertEqual(plan["termination"],
                         {"success_when": "", "max_steps": None})

    def test_termination_values_are_settable(self):
        plan = pt.create("count the rows", "direct", None, "proj", "main",
                         self.roles_dir, success_when="every test passes",
                         max_steps=8)
        self.assertEqual(plan["termination"],
                         {"success_when": "every test passes", "max_steps": 8})

    def test_termination_survives_a_save_load_round_trip(self):
        plan = pt.create("count the rows", "direct", None, "proj", "main",
                         self.roles_dir, success_when="green suite", max_steps=3)
        pt.save(str(self.state), plan)
        self.assertEqual(pt.load(str(self.state), plan["task_id"])["termination"],
                         {"success_when": "green suite", "max_steps": 3})


class TestCli(TempCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "plan_task.py"), "--state-dir",
             str(self.state), "--roles-dir", self.roles_dir] + list(args),
            capture_output=True, text=True)

    def test_new_mechanical_task_succeeds(self):
        r = self._run("--new", "count the rows in the export")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("wo-", r.stdout)

    def test_new_creative_task_no_longer_refused(self):
        # what used to exit 3 with a superpowers refusal now just succeeds
        r = self._run("--new", "build a new dashboard")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_new_creates_a_fully_briefed_plan_on_disk(self):
        r = self._run("--new", "count the rows in the export")
        pid = r.stdout.strip().splitlines()[0].split()[-1]
        plan = pt.load(str(self.state), pid)
        step = plan["steps"][0]
        self.assertEqual(step["status"], "pending")
        self.assertTrue(step["brief"])
        self.assertIsNotNone(step["agent"])

    def test_force_flag_removed(self):
        r = self._run("--new", "count the rows", "--force")
        self.assertNotEqual(r.returncode, 0)

    def test_classify_flag_removed(self):
        r = self._run("--classify", "build a new coach dashboard")
        self.assertNotEqual(r.returncode, 0)

    def test_from_plan_creates_steps(self):
        doc = pathlib.Path(self.tmp) / "plan.md"
        doc.write_text(PLAN_DOC)
        r = self._run("--from-plan", str(doc), "--task", "the whole thing")
        self.assertEqual(r.returncode, 0, r.stderr)
        pid = r.stdout.strip().splitlines()[0].split()[-1]
        plan = pt.load(str(self.state), pid)
        self.assertEqual(len(plan["steps"]), 2)
        self.assertEqual(plan["source"], "plan")

    def test_from_plan_with_no_headings_fails(self):
        doc = pathlib.Path(self.tmp) / "empty.md"
        doc.write_text("# nothing here\n")
        r = self._run("--from-plan", str(doc), "--task", "t")
        self.assertNotEqual(r.returncode, 0)

    def test_reasoning_budget_and_worktree_flags_applied(self):
        r = self._run("--new", "count the rows", "--reasoning", "low ambiguity",
                      "--budget-tokens", "500", "--worktree")
        self.assertEqual(r.returncode, 0, r.stderr)
        pid = r.stdout.strip().splitlines()[0].split()[-1]
        plan = pt.load(str(self.state), pid)
        self.assertEqual(plan["supervisor_reasoning"], "low ambiguity")
        self.assertEqual(plan["steps"][0]["budget_tokens"], 500)
        self.assertTrue(plan["steps"][0]["worktree"])

    def test_assign_cli_reroutes_open_steps(self):
        r = self._run("--new", "count the rows in the export")
        pid = r.stdout.strip().splitlines()[0].split()[-1]
        r2 = self._run("--assign", pid)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn(pid, r2.stdout)

    def test_show_renders_the_plan(self):
        r = self._run("--new", "count the rows in the export")
        pid = r.stdout.strip().splitlines()[0].split()[-1]
        r2 = self._run("--show", pid)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn(pid, r2.stdout)

    def test_cli_record_requires_step_and_json(self):
        # Create a plan first
        r = self._run("--new", "count the rows")
        pid = r.stdout.strip().splitlines()[0].split()[-1]
        plan = pt.load(str(self.state), pid)
        step_id = plan["steps"][0]["id"]

        # `--record <id>` with neither --step nor --json should exit 2
        r2 = self._run("--record", pid)
        self.assertNotEqual(r2.returncode, 0)

        # `--record <id> --step <id>` without --json should exit 2
        r3 = self._run("--record", pid, "--step", step_id)
        self.assertNotEqual(r3.returncode, 0)

        # `--record <id> --json <json>` without --step should exit 2
        r4 = self._run("--record", pid, "--json", '{"ok": true}')
        self.assertNotEqual(r4.returncode, 0)

    def test_cli_record_accepts_a_json_file_path(self):
        # pipeline-relay.sh ships `--json <file>` as the directive every
        # writing-plans session follows; it must work end to end.
        r = self._run("--new", "count the rows")
        pid = r.stdout.strip().splitlines()[0].split()[-1]
        step_id = pt.load(str(self.state), pid)["steps"][0]["id"]

        ret = pathlib.Path(self.tmp) / "return.json"
        ret.write_text(json.dumps({
            "ok": True,
            "summary": 'ran `pytest`, saw "3 passed"\nno failures',
            "agent_task_id": "agent-from-file",
        }))
        r2 = self._run("--record", pid, "--step", step_id, "--json", str(ret))
        self.assertEqual(r2.returncode, 0, r2.stderr)

        step = pt.load(str(self.state), pid)["steps"][0]
        self.assertEqual(step["status"], "done")
        self.assertEqual(step["agent_task_id"], "agent-from-file")
        self.assertIn("3 passed", step["return"]["summary"])

    def test_cli_record_accepts_inline_json(self):
        r = self._run("--new", "count the rows")
        pid = r.stdout.strip().splitlines()[0].split()[-1]
        step_id = pt.load(str(self.state), pid)["steps"][0]["id"]
        r2 = self._run("--record", pid, "--step", step_id,
                       "--json", '{"ok": true, "summary": "inline"}')
        self.assertEqual(r2.returncode, 0, r2.stderr)
        step = pt.load(str(self.state), pid)["steps"][0]
        self.assertEqual(step["status"], "done")
        self.assertEqual(step["return"]["summary"], "inline")

    def test_cli_record_rejects_a_bad_path_with_a_stated_reason(self):
        r = self._run("--new", "count the rows")
        pid = r.stdout.strip().splitlines()[0].split()[-1]
        step_id = pt.load(str(self.state), pid)["steps"][0]["id"]
        r2 = self._run("--record", pid, "--step", step_id,
                       "--json", "/no/such/return.json")
        self.assertEqual(r2.returncode, 2)
        self.assertIn("neither a readable file nor valid JSON", r2.stderr)

    def test_termination_flags_applied(self):
        r = self._run("--new", "count the rows", "--success-when",
                      "the suite is green", "--max-steps", "8")
        self.assertEqual(r.returncode, 0, r.stderr)
        pid = r.stdout.strip().splitlines()[0].split()[-1]
        plan = pt.load(str(self.state), pid)
        self.assertEqual(plan["termination"],
                         {"success_when": "the suite is green", "max_steps": 8})


if __name__ == "__main__":
    unittest.main()
