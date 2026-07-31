#!/usr/bin/env python3
"""Tests for assess_task.py — the objective assessment channel.

The point of this tool is that no model touches the verdict, so the tests here
are a truth table plus real fixtures: a real metrics shard on disk and a real
temporary git repository.
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

import assess_task as at  # noqa: E402
import plan_task as pt  # noqa: E402


def ev(**over):
    base = {"tests_detected": True, "tests_failed": 0, "reverts": 0,
            "error_rate": 0.0, "commits": 1, "followup_fixes": 0}
    base.update(over)
    return base


class TestVerdict(unittest.TestCase):
    def test_clean_requires_no_failures_no_reverts_low_errors(self):
        self.assertEqual(at.verdict(ev()), "clean")

    def test_failed_test_forces_dirty(self):
        self.assertEqual(at.verdict(ev(tests_failed=3)), "dirty")

    def test_revert_forces_dirty(self):
        self.assertEqual(at.verdict(ev(reverts=1)), "dirty")

    def test_followup_fix_forces_dirty(self):
        self.assertEqual(at.verdict(ev(followup_fixes=1)), "dirty")

    def test_high_error_rate_is_dirty(self):
        self.assertEqual(at.verdict(ev(error_rate=0.5)), "dirty")

    def test_error_rate_at_the_threshold_is_still_clean(self):
        self.assertEqual(at.verdict(ev(error_rate=at.ERROR_RATE_MAX)), "clean")

    def test_no_signal_is_unknown_never_clean(self):
        self.assertEqual(
            at.verdict({"tests_detected": False, "tests_failed": 0, "reverts": 0,
                        "error_rate": None, "commits": 0, "followup_fixes": 0}),
            "unknown")

    def test_commits_alone_are_signal_enough_for_clean(self):
        self.assertEqual(
            at.verdict({"tests_detected": False, "tests_failed": 0, "reverts": 0,
                        "error_rate": None, "commits": 2, "followup_fixes": 0}),
            "clean")

    def test_empty_evidence_is_unknown(self):
        self.assertEqual(at.verdict({}), "unknown")


class TestMetricsLookup(unittest.TestCase):
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
        rec = at.metrics_for(self.tmp, "agent-bbb")
        self.assertEqual(rec["tests"]["failed"], 2)

    def test_missing_id_returns_none(self):
        self.assertIsNone(at.metrics_for(self.tmp, "agent-nope"))

    def test_ignores_non_task_records(self):
        self.assertIsNone(at.metrics_for(self.tmp, "session-zzz"))

    def test_missing_directory_returns_none(self):
        self.assertIsNone(at.metrics_for(self.tmp + "-gone", "agent-aaa"))


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
        g = at.git_evidence(self.repo, since=None, until=None, files=None)
        self.assertGreaterEqual(g["commits"], 3)

    def test_counts_reverts(self):
        self.assertEqual(at.git_evidence(self.repo, None, None, None)["reverts"], 1)

    def test_counts_followup_fixes(self):
        self.assertEqual(at.git_evidence(self.repo, None, None, None)["followup_fixes"], 1)

    def test_non_repo_yields_zeroes_not_a_crash(self):
        empty = tempfile.mkdtemp()
        try:
            g = at.git_evidence(empty, None, None, None)
            self.assertEqual(g["commits"], 0)
            self.assertEqual(g["reverts"], 0)
        finally:
            shutil.rmtree(empty, ignore_errors=True)


class TestAssess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shard = pathlib.Path(self.tmp) / "2026-07.jsonl"
        shard.write_text(json.dumps(
            {"kind": "task", "task_id": "agent-aaa",
             "tests": {"detected": True, "passed": 3, "failed": 0},
             "tool_errors": 0, "error_rate": 0.0, "turns": 8, "duration_s": 12.0}) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wo(self, agent_id):
        return {"schema": pt.SCHEMA, "plan_id": "wo-x", "task": "t",
                "git_branch": "main",
                "parts": [{"part_id": "p1", "goal": "g", "role": "dba",
                           "skills": ["explain-analyze-query-tuning"],
                           "status": "done", "agent_task_id": agent_id,
                           "log": {"ok": True}, "evidence": None,
                           "verdict": None, "score": None}]}

    def test_assess_fills_evidence_and_verdict(self):
        wo = self._wo("agent-aaa")
        at.assess(wo, self.tmp, repo=None)
        p = wo["parts"][0]
        self.assertEqual(p["evidence"]["tests_failed"], 0)
        self.assertEqual(p["verdict"], "clean")

    def test_missing_metrics_record_yields_unknown_not_clean(self):
        wo = self._wo("agent-missing")
        at.assess(wo, self.tmp, repo=None)
        self.assertEqual(wo["parts"][0]["verdict"], "unknown")

    def test_part_with_no_agent_id_is_unknown(self):
        wo = self._wo(None)
        at.assess(wo, self.tmp, repo=None)
        self.assertEqual(wo["parts"][0]["verdict"], "unknown")

    def test_a_failed_log_cannot_assess_clean(self):
        wo = self._wo("agent-aaa")
        wo["parts"][0]["status"] = "failed"
        at.assess(wo, self.tmp, repo=None)
        self.assertEqual(wo["parts"][0]["verdict"], "dirty")


class TestSubagentsRow(unittest.TestCase):
    def test_row_cites_plan_id_role_and_verdict(self):
        wo = {"plan_id": "wo-x", "task": "t"}
        part = {"part_id": "p1", "goal": "author the DAG", "role": "dba",
                "verdict": "dirty", "skills": ["explain-analyze-query-tuning"],
                "evidence": {"tests_failed": 2, "reverts": 0}}
        row = at.subagents_row(wo, part)
        self.assertTrue(row.startswith("|"))
        self.assertIn("wo-x", row)
        self.assertIn("dba", row)
        self.assertIn("dirty", row)

    def test_row_is_single_line(self):
        wo = {"plan_id": "wo-x", "task": "t"}
        part = {"part_id": "p1", "goal": "a goal\nwith a newline", "role": "dba",
                "verdict": "clean", "skills": [], "evidence": {}}
        self.assertEqual(len(at.subagents_row(wo, part).splitlines()), 1)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state = pathlib.Path(self.tmp) / "state"
        self.metrics = pathlib.Path(self.tmp) / "metrics"
        self.metrics.mkdir()
        (self.metrics / "2026-07.jsonl").write_text(json.dumps(
            {"kind": "task", "task_id": "agent-aaa",
             "tests": {"detected": True, "passed": 3, "failed": 0},
             "tool_errors": 0, "error_rate": 0.0}) + "\n")
        pt.save(str(self.state), {
            "schema": pt.SCHEMA, "plan_id": "wo-cli", "task": "t",
            "git_branch": "main",
            "parts": [{"part_id": "p1", "goal": "g", "role": "dba", "skills": [],
                       "status": "done", "agent_task_id": "agent-aaa",
                       "log": {"ok": True}, "evidence": None, "verdict": None,
                       "score": None}]})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "assess_task.py"), "--state-dir",
             str(self.state), "--metrics-dir", str(self.metrics)] + list(args),
            capture_output=True, text=True)

    def test_cli_assesses_and_persists(self):
        r = self._run("wo-cli")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("clean", r.stdout)
        self.assertEqual(pt.load(str(self.state), "wo-cli")["parts"][0]["verdict"], "clean")

    def test_cli_unknown_plan_exits_nonzero(self):
        self.assertNotEqual(self._run("wo-nope").returncode, 0)

    def test_clean_run_proposes_no_row(self):
        r = self._run("wo-cli", "--propose-row")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no SUBAGENTS.md row proposed", r.stdout)

    def test_subagents_row_is_printed_never_written(self):
        # The local-improvement path is proposal-only: a dirty part's row goes to
        # stdout and no project file is created anywhere.
        (self.metrics / "2026-07.jsonl").write_text(json.dumps(
            {"kind": "task", "task_id": "agent-bad",
             "tests": {"detected": True, "passed": 1, "failed": 4},
             "tool_errors": 5, "error_rate": 0.5}) + "\n")
        pt.save(str(self.state), {
            "schema": pt.SCHEMA, "plan_id": "wo-dirty", "task": "t",
            "git_branch": "main",
            "parts": [{"part_id": "p1", "goal": "g", "role": "dba", "skills": [],
                       "status": "done", "agent_task_id": "agent-bad",
                       "log": {"ok": True}, "evidence": None, "verdict": None,
                       "score": None}]})
        before = sorted(str(p) for p in pathlib.Path(self.tmp).rglob("*"))
        r = self._run("wo-dirty", "--propose-row")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dirty", r.stdout)
        self.assertIn("| dba |", r.stdout)
        after = sorted(str(p) for p in pathlib.Path(self.tmp).rglob("*"))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
