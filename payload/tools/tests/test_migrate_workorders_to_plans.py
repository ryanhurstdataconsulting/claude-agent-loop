#!/usr/bin/env python3
"""Tests for migrate_workorders_to_plans.py — schema-1 work orders ->
schema-2 plans.

Hermetic: every test builds its own tempdir state/base/archive directories,
so the suite never touches the live ~/.claude tree.
"""
import json
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import migrate_workorders_to_plans as mig  # noqa: E402


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

    def test_missing_evidence_or_verdict_yields_none_assessment(self):
        old = self._minimal_old_wo(part_status="pending")
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


class TestMigrateAll(_FixtureMixin, unittest.TestCase):
    def test_writes_date_partitioned_files_and_archives_source(self):
        with tempfile.TemporaryDirectory() as root:
            state_dir = pathlib.Path(root) / "workorders"
            state_dir.mkdir()
            (state_dir / "wo-20260805-x-111111.json").write_text(
                json.dumps(self._minimal_old_wo_dict()))
            base_dir = pathlib.Path(root) / "plans"
            archive_dir = pathlib.Path(root) / "workorders_archive"
            summaries = mig.migrate_all(str(state_dir), str(base_dir), str(archive_dir))
            self.assertEqual(len(summaries), 1)
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
            mig.migrate_all(str(state_dir), str(base_dir),
                            str(pathlib.Path(root) / "archive"), dry_run=True)
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
            summaries = mig.migrate_all(str(state_dir), str(base_dir), str(archive_dir))
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
            mig.migrate_all(str(state_dir), str(base_dir), str(archive_dir))
            self.assertTrue((archive_dir / "wo-20260805-x-111111.json").is_file())


if __name__ == "__main__":
    unittest.main()
