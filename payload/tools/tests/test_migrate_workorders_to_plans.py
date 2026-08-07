#!/usr/bin/env python3
"""Tests for migrate_workorders_to_plans.py — schema-1 work orders ->
schema-2 plans.

Hermetic: every test builds its own tempdir state/base/archive directories,
so the suite never touches the live ~/.claude tree.
"""
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import migrate_workorders_to_plans as mig  # noqa: E402
import plan_task  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "workorders_schema1"


class _FixtureMixin:
    def _minimal_old_wo_dict(self, part_status="pending"):
        return {
            "schema": 1, "plan_id": "wo-20260805-x-111111", "task": "do a thing",
            "source": "direct", "plan_doc": None, "forced": False,
            "created": "2026-08-05T10:00:00Z", "project": "p", "git_branch": "main",
            "parts": [{
                "part_id": "p1", "goal": "the goal", "status": part_status,
                "role": "generalist", "role_score": 0, "skills": [], "model": "opus",
                "agent_task_id": None, "log": None,
                "evidence": None, "verdict": None, "score": None,
            }],
        }

    def _minimal_old_wo(self, part_status="pending"):
        return self._minimal_old_wo_dict(part_status=part_status)

    def _old_wo_with_evidence_verdict(self, evidence, verdict):
        """A minimal old work order with independently-set evidence/verdict,
        to exercise all four assessment permutations (both present, either
        one missing, both missing)."""
        old = self._minimal_old_wo_dict(part_status="done")
        old["parts"][0]["evidence"] = evidence
        old["parts"][0]["verdict"] = verdict
        return old


class TestMigrateOne(_FixtureMixin, unittest.TestCase):
    def test_maps_every_field(self):
        old = {
            "schema": 1, "plan_id": "wo-20260805-x-111111", "task": "do a thing",
            "source": "plan", "plan_doc": "doc.md", "forced": False,
            "created": "2026-08-05T10:00:00Z", "project": "p", "git_branch": "main",
            "parts": [{
                "part_id": "p1", "goal": "the goal", "status": "done",
                "role": "generalist", "role_score": 0, "skills": [], "model": "opus",
                "agent_task_id": "agent-abc", "log": {"ok": True, "summary": "did it"},
                "evidence": {"tests_detected": False}, "verdict": "clean", "score": None,
            }],
        }
        new = mig.migrate_one(old)
        self.assertEqual(new["schema"], 2)
        self.assertEqual(new["task_id"], "wo-20260805-x-111111")
        self.assertEqual(new["supervisor_reasoning"], "")
        self.assertEqual(new["source"], "plan")
        self.assertEqual(new["plan_doc"], "doc.md")
        self.assertEqual(new["created"], "2026-08-05T10:00:00Z")
        self.assertEqual(new["project"], "p")
        self.assertEqual(new["git_branch"], "main")
        step = new["steps"][0]
        self.assertEqual(step["id"], "p1")
        self.assertEqual(step["goal"], "the goal")
        self.assertEqual(step["agent"], "generalist")
        self.assertEqual(step["agent_score"], 0)
        self.assertEqual(step["skills"], [])
        self.assertEqual(step["model"], "opus")
        self.assertEqual(step["agent_task_id"], "agent-abc")
        self.assertEqual(step["status"], "done")
        self.assertEqual(step["return"], {"ok": True, "summary": "did it"})
        self.assertEqual(step["assessment"], {"evidence": {"tests_detected": False}, "verdict": "clean"})
        self.assertEqual(step["depends_on"], [])
        self.assertIsNone(step["budget_tokens"])
        self.assertIs(step["worktree"], False)
        self.assertNotIn("score", step)
        self.assertNotIn("forced", new)

    def test_assigned_status_becomes_pending(self):
        old = self._minimal_old_wo(part_status="assigned")
        new = mig.migrate_one(old)
        self.assertEqual(new["steps"][0]["status"], "pending")

    def test_pending_step_gets_empty_brief(self):
        old = self._minimal_old_wo(part_status="assigned")
        new = mig.migrate_one(old)
        self.assertEqual(new["steps"][0]["brief"], "")

    # -- assessment: all four evidence/verdict presence permutations --------
    # (test_maps_every_field above already covers "both present" with a
    # realistic payload; this one confirms it in isolation too so the four
    # cases read as one deliberate set.)
    def test_both_evidence_and_verdict_present_yields_real_assessment(self):
        old = self._old_wo_with_evidence_verdict({"tests_detected": False}, "clean")
        new = mig.migrate_one(old)
        self.assertEqual(new["steps"][0]["assessment"],
                          {"evidence": {"tests_detected": False}, "verdict": "clean"})

    def test_evidence_present_verdict_none_yields_none_assessment(self):
        # The partial-missing case: if the AND in the implementation ever
        # regressed to an OR, this would start returning a real assessment
        # dict with verdict=None instead of None.
        old = self._old_wo_with_evidence_verdict({"tests_detected": False}, None)
        new = mig.migrate_one(old)
        self.assertIsNone(new["steps"][0]["assessment"])

    def test_verdict_present_evidence_none_yields_none_assessment(self):
        # The other partial-missing case, same regression risk as above.
        old = self._old_wo_with_evidence_verdict(None, "clean")
        new = mig.migrate_one(old)
        self.assertIsNone(new["steps"][0]["assessment"])

    def test_both_evidence_and_verdict_none_yields_none_assessment(self):
        old = self._old_wo_with_evidence_verdict(None, None)
        new = mig.migrate_one(old)
        self.assertIsNone(new["steps"][0]["assessment"])

    def test_closed_at_carries_over_when_present(self):
        old = self._minimal_old_wo_dict(part_status="done")
        old["closed_at"] = "2026-08-05T12:00:00Z"
        new = mig.migrate_one(old)
        self.assertEqual(new["closed_at"], "2026-08-05T12:00:00Z")

    def test_closed_at_absent_when_not_present(self):
        old = self._minimal_old_wo_dict(part_status="pending")
        new = mig.migrate_one(old)
        self.assertNotIn("closed_at", new)


    def test_termination_present_and_inert_on_every_migrated_plan(self):
        new = mig.migrate_one(self._minimal_old_wo_dict())
        self.assertEqual(new["termination"],
                         {"success_when": "", "max_steps": None})


class TestMigrateAll(_FixtureMixin, unittest.TestCase):
    def _run(self, state_dir, base_dir, archive_dir, dry_run=False):
        """migrate_all with its progress output captured, not on stdout."""
        buf = io.StringIO()
        summaries, failures = mig.migrate_all(
            str(state_dir), str(base_dir), str(archive_dir),
            dry_run=dry_run, out=buf)
        return summaries, failures, buf.getvalue()

    def test_writes_date_partitioned_files_and_archives_source(self):
        with tempfile.TemporaryDirectory() as root:
            state_dir = pathlib.Path(root) / "workorders"
            state_dir.mkdir()
            (state_dir / "wo-20260805-x-111111.json").write_text(
                json.dumps(self._minimal_old_wo_dict()))
            base_dir = pathlib.Path(root) / "plans"
            archive_dir = pathlib.Path(root) / "workorders_archive"
            summaries, failures, _ = self._run(state_dir, base_dir, archive_dir)
            self.assertEqual(len(summaries), 1)
            self.assertEqual(failures, [])
            self.assertTrue((base_dir / "2026-08-05" / "wo-20260805-x-111111.json").is_file())
            self.assertTrue((archive_dir / "wo-20260805-x-111111.json").is_file())
            self.assertFalse((state_dir / "wo-20260805-x-111111.json").is_file())

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            state_dir = pathlib.Path(root) / "workorders"
            state_dir.mkdir()
            (state_dir / "wo-20260805-x-111111.json").write_text(
                json.dumps(self._minimal_old_wo_dict()))
            base_dir = pathlib.Path(root) / "plans"
            self._run(state_dir, base_dir, pathlib.Path(root) / "archive",
                      dry_run=True)
            self.assertFalse(base_dir.exists())
            self.assertTrue((state_dir / "wo-20260805-x-111111.json").is_file())

    def test_no_dependency_fabricated_for_multi_part_orders(self):
        old = self._minimal_old_wo_dict()
        old["parts"] = old["parts"] * 2
        old["parts"][0]["part_id"], old["parts"][1]["part_id"] = "p1", "p2"
        new = mig.migrate_one(old)
        for step in new["steps"]:
            self.assertEqual(step["depends_on"], [])

    def test_summary_shape(self):
        with tempfile.TemporaryDirectory() as root:
            state_dir = pathlib.Path(root) / "workorders"
            state_dir.mkdir()
            (state_dir / "wo-20260805-x-111111.json").write_text(
                json.dumps(self._minimal_old_wo_dict()))
            base_dir = pathlib.Path(root) / "plans"
            archive_dir = pathlib.Path(root) / "workorders_archive"
            summaries, _, _ = self._run(state_dir, base_dir, archive_dir)
            self.assertEqual(summaries[0]["task_id"], "wo-20260805-x-111111")
            self.assertEqual(summaries[0]["step_count"], 1)
            self.assertTrue(str(summaries[0]["new_path"]).endswith(
                "plans/2026-08-05/wo-20260805-x-111111.json"))

    def test_archive_dir_created_if_absent(self):
        with tempfile.TemporaryDirectory() as root:
            state_dir = pathlib.Path(root) / "workorders"
            state_dir.mkdir()
            (state_dir / "wo-20260805-x-111111.json").write_text(
                json.dumps(self._minimal_old_wo_dict()))
            base_dir = pathlib.Path(root) / "plans"
            archive_dir = pathlib.Path(root) / "nested" / "workorders_archive"
            self.assertFalse(archive_dir.exists())
            self._run(state_dir, base_dir, archive_dir)
            self.assertTrue((archive_dir / "wo-20260805-x-111111.json").is_file())

    def test_progress_prints_per_file_as_it_happens(self):
        with tempfile.TemporaryDirectory() as root:
            state_dir = pathlib.Path(root) / "workorders"
            state_dir.mkdir()
            (state_dir / "wo-20260805-x-111111.json").write_text(
                json.dumps(self._minimal_old_wo_dict()))
            _, _, printed = self._run(state_dir,
                                      pathlib.Path(root) / "plans",
                                      pathlib.Path(root) / "archive")
            self.assertIn("wo-20260805-x-111111 -> ", printed)
            self.assertIn("(1 step)", printed)


class TestMigrateAllFailureIsolation(_FixtureMixin, unittest.TestCase):
    """One bad file must not abort a one-shot run over live user data."""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.state = self.root / "workorders"
        self.state.mkdir()
        self.base = self.root / "plans"
        self.archive = self.root / "workorders_archive"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, name, text):
        (self.state / name).write_text(text)

    def _good(self, task_id):
        old = self._minimal_old_wo_dict()
        old["plan_id"] = task_id
        self._write(task_id + ".json", json.dumps(old))

    def _run(self):
        buf = io.StringIO()
        summaries, failures = mig.migrate_all(
            str(self.state), str(self.base), str(self.archive), out=buf)
        return summaries, failures, buf.getvalue()

    def test_malformed_json_does_not_abort_the_run(self):
        self._good("wo-20260805-a-111111")
        self._write("wo-20260805-bad-222222.json", "{not json at all")
        self._good("wo-20260805-c-333333")

        summaries, failures, printed = self._run()

        self.assertEqual([s["task_id"] for s in summaries],
                         ["wo-20260805-a-111111", "wo-20260805-c-333333"])
        self.assertEqual(len(failures), 1)
        self.assertIn("wo-20260805-bad-222222.json", failures[0]["file"])
        self.assertIn("JSONDecodeError", failures[0]["error"])
        self.assertIn("FAILED wo-20260805-bad-222222.json", printed)
        self.assertIn("left in place", printed)

    def test_a_failed_file_is_left_in_place_not_archived(self):
        self._write("wo-20260805-bad-222222.json", "{not json at all")
        self._run()
        self.assertTrue((self.state / "wo-20260805-bad-222222.json").is_file())
        self.assertFalse((self.archive / "wo-20260805-bad-222222.json").exists())

    def test_good_files_still_land_when_a_neighbour_fails(self):
        self._good("wo-20260805-a-111111")
        self._write("wo-20260805-bad-222222.json", "{not json at all")
        self._run()
        self.assertTrue(
            (self.base / "2026-08-05" / "wo-20260805-a-111111.json").is_file())
        self.assertTrue(
            (self.archive / "wo-20260805-a-111111.json").is_file())

    def test_undated_plan_id_is_a_reported_failure_not_a_crash(self):
        old = self._minimal_old_wo_dict()
        old["plan_id"] = "not-a-wo-id"
        self._write("undated.json", json.dumps(old))
        summaries, failures, printed = self._run()
        self.assertEqual(summaries, [])
        self.assertEqual(len(failures), 1)
        self.assertIn("does not carry an embedded", failures[0]["error"])

    def test_missing_plan_id_is_a_reported_failure(self):
        old = self._minimal_old_wo_dict()
        del old["plan_id"]
        self._write("noid.json", json.dumps(old))
        _, failures, _ = self._run()
        self.assertEqual(len(failures), 1)
        self.assertIn("no plan_id", failures[0]["error"])

    def test_non_object_json_is_a_reported_failure(self):
        self._write("list.json", json.dumps([1, 2, 3]))
        _, failures, _ = self._run()
        self.assertEqual(len(failures), 1)
        self.assertIn("not a JSON object", failures[0]["error"])

    def test_cli_exits_non_zero_and_recaps_when_a_file_fails(self):
        self._good("wo-20260805-a-111111")
        self._write("wo-20260805-bad-222222.json", "{not json at all")
        r = subprocess.run(
            [sys.executable, str(TOOLS / "migrate_workorders_to_plans.py"),
             "--state-dir", str(self.state), "--base-dir", str(self.base),
             "--archive-dir", str(self.archive)],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("1 file(s) migrated, 1 failed", r.stdout)
        self.assertIn("wo-20260805-bad-222222.json", r.stderr)
        self.assertIn("fix and re-run", r.stderr)

    def test_cli_exits_zero_when_every_file_migrates(self):
        self._good("wo-20260805-a-111111")
        r = subprocess.run(
            [sys.executable, str(TOOLS / "migrate_workorders_to_plans.py"),
             "--state-dir", str(self.state), "--base-dir", str(self.base),
             "--archive-dir", str(self.archive)],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 file(s) migrated, 0 failed", r.stdout)

    def test_cli_dry_run_says_would_not_did(self):
        self._good("wo-20260805-a-111111")
        r = subprocess.run(
            [sys.executable, str(TOOLS / "migrate_workorders_to_plans.py"),
             "--state-dir", str(self.state), "--base-dir", str(self.base),
             "--archive-dir", str(self.archive), "--dry-run"],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[dry-run] 1 file(s) would migrate, 0 would fail",
                      r.stdout)
        self.assertFalse(self.base.exists())


# --- fixture copies of REAL work orders --------------------------------------
# The spec's Testing section requires the migration script be tested "against a
# fixture copy of the ... real work-order files, asserting no data loss on the
# fields the new schema still carries." Since the real migration run is still
# deferred, this is the only standing pre-flight check before deployment.
#
# tests/fixtures/workorders_schema1/ holds five sanitized copies of live files,
# one per distinct shape found across the 24 real orders: a fully-closed order
# with a null git_branch and multiple parts, a closed order on a feature
# branch, an open order whose parts are all still "assigned" with no
# log/evidence/verdict, an open order that DOES carry evidence+verdict while
# every log is null, and the smallest real order (2 parts). Sanitizing replaced
# absolute home paths and truncated prose bulk; every key, type, and structural
# shape is byte-for-byte what the live files carry.
FIELD_MAP = [
    # (schema-1 top-level key, schema-2 top-level key)
    ("plan_id", "task_id"), ("task", "task"), ("source", "source"),
    ("plan_doc", "plan_doc"), ("created", "created"), ("project", "project"),
    ("git_branch", "git_branch"),
]
STEP_MAP = [
    # (schema-1 part key, schema-2 step key)
    ("part_id", "id"), ("goal", "goal"), ("role", "agent"),
    ("role_score", "agent_score"), ("skills", "skills"), ("model", "model"),
    ("agent_task_id", "agent_task_id"), ("log", "return"),
]


class TestRealWorkOrderFixtures(unittest.TestCase):
    def setUp(self):
        self.files = sorted(FIXTURES.glob("*.json"))

    def test_fixtures_are_present(self):
        self.assertGreaterEqual(len(self.files), 5,
                                "real-shape fixtures are missing from %s" % FIXTURES)

    def test_every_fixture_is_schema_1_with_parts(self):
        for path in self.files:
            with self.subTest(fixture=path.name):
                old = json.loads(path.read_text())
                self.assertEqual(old["schema"], 1)
                self.assertTrue(old["parts"])

    def test_the_five_real_shapes_are_all_represented(self):
        shapes = set()
        for path in self.files:
            old = json.loads(path.read_text())
            statuses = {p["status"] for p in old["parts"]}
            shapes.add(("closed" if "closed_at" in old else "open",
                        old["git_branch"] is None,
                        tuple(sorted(statuses)),
                        any(p.get("evidence") for p in old["parts"]),
                        any(p.get("log") for p in old["parts"])))
        # closed+null-branch, closed+feature-branch, open with no evidence,
        # open WITH evidence but no log — the shapes the live tree actually has.
        self.assertIn(("open", False, ("assigned",), False, False), shapes)
        self.assertIn(("open", False, ("assigned",), True, False), shapes)
        self.assertIn(("closed", True, ("done",), True, True), shapes)
        self.assertIn(("closed", False, ("done",), True, True), shapes)

    def test_no_data_loss_on_any_carried_field(self):
        for path in self.files:
            with self.subTest(fixture=path.name):
                old = json.loads(path.read_text())
                new = mig.migrate_one(old)

                for old_key, new_key in FIELD_MAP:
                    self.assertEqual(new[new_key], old[old_key],
                                     "%s -> %s lost data" % (old_key, new_key))
                self.assertEqual(new["schema"], 2)
                self.assertEqual(new["supervisor_reasoning"], "")
                self.assertEqual(new["termination"],
                                 {"success_when": "", "max_steps": None})
                self.assertEqual(("closed_at" in new), ("closed_at" in old))
                if "closed_at" in old:
                    self.assertEqual(new["closed_at"], old["closed_at"])
                self.assertNotIn("forced", new)
                self.assertNotIn("parts", new)

                self.assertEqual(len(new["steps"]), len(old["parts"]))
                for part, step in zip(old["parts"], new["steps"]):
                    for old_key, new_key in STEP_MAP:
                        self.assertEqual(step[new_key], part[old_key],
                                         "%s: %s -> %s lost data"
                                         % (part["part_id"], old_key, new_key))
                    self.assertNotIn("score", step)
                    self.assertNotIn("evidence", step)
                    self.assertNotIn("verdict", step)
                    self.assertEqual(step["depends_on"], [])
                    self.assertIsNone(step["budget_tokens"])
                    self.assertIs(step["worktree"], False)
                    self.assertEqual(step["brief"], "")

    def test_assessment_reconstructs_evidence_and_verdict_exactly(self):
        seen_real, seen_none = False, False
        for path in self.files:
            old = json.loads(path.read_text())
            new = mig.migrate_one(old)
            for part, step in zip(old["parts"], new["steps"]):
                if part["evidence"] is not None and part["verdict"] is not None:
                    self.assertEqual(step["assessment"]["evidence"],
                                     part["evidence"])
                    self.assertEqual(step["assessment"]["verdict"],
                                     part["verdict"])
                    seen_real = True
                else:
                    self.assertIsNone(step["assessment"])
                    seen_none = True
        self.assertTrue(seen_real, "no fixture exercised a real assessment")
        self.assertTrue(seen_none, "no fixture exercised a null assessment")

    def test_every_assigned_part_becomes_pending_and_nothing_else_moves(self):
        for path in self.files:
            with self.subTest(fixture=path.name):
                old = json.loads(path.read_text())
                new = mig.migrate_one(old)
                for part, step in zip(old["parts"], new["steps"]):
                    expected = "pending" if part["status"] == "assigned" \
                        else part["status"]
                    self.assertEqual(step["status"], expected)

    def test_migrate_all_over_every_fixture_writes_and_archives_all_of_them(self):
        with tempfile.TemporaryDirectory() as root:
            state = pathlib.Path(root) / "workorders"
            state.mkdir()
            for path in self.files:
                shutil.copy(str(path), str(state / path.name))
            base = pathlib.Path(root) / "plans"
            archive = pathlib.Path(root) / "workorders_archive"

            buf = io.StringIO()
            summaries, failures = mig.migrate_all(
                str(state), str(base), str(archive), out=buf)

            self.assertEqual(failures, [], buf.getvalue())
            self.assertEqual(len(summaries), len(self.files))
            self.assertEqual(len(list(state.glob("*.json"))), 0)
            self.assertEqual(len(list(archive.glob("*.json"))), len(self.files))

            # Every migrated plan is loadable by the tool that owns the schema,
            # partitioned by the date embedded in its own id, with its step
            # count intact.
            for path, summary in zip(self.files, summaries):
                old = json.loads(path.read_text())
                loaded = plan_task.load(str(base), old["plan_id"])
                self.assertEqual(len(loaded["steps"]), len(old["parts"]))
                self.assertEqual(summary["step_count"], len(old["parts"]))
                self.assertIn(plan_task.date_partition_for(old["plan_id"]),
                              summary["new_path"])


if __name__ == "__main__":
    unittest.main()
