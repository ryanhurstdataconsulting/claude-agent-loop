#!/usr/bin/env python3
"""Tests for make_brief.py — rendering a dispatchable subagent brief."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import make_brief as mb  # noqa: E402
import obs_emit  # noqa: E402
import plan_task as pt  # noqa: E402


def wo(**over):
    base = {
        "schema": pt.SCHEMA,
        "plan_id": "wo-20260730-x-abc123",
        "task": "the whole task",
        "source": "plan",
        "parts": [{
            "part_id": "p1", "goal": "author the Airflow DAG",
            "role": "data-engineer", "role_score": 6,
            "skills": ["airflow-dag-authoring", "idempotent-backfill-authoring"],
            "model": "opus", "status": "assigned", "agent_task_id": None,
            "log": None, "evidence": None, "verdict": None, "score": None,
        }],
    }
    base.update(over)
    return base


class TestIdentifiers(unittest.TestCase):
    def test_plan_and_part_ids_present(self):
        out = mb.render(wo(), "p1")
        self.assertIn("wo-20260730-x-abc123", out)
        self.assertIn("p1", out)

    def test_goal_present(self):
        self.assertIn("author the Airflow DAG", mb.render(wo(), "p1"))

    def test_parent_task_present_for_context(self):
        self.assertIn("the whole task", mb.render(wo(), "p1"))

    def test_role_named(self):
        self.assertIn("data-engineer", mb.render(wo(), "p1"))


class TestSkills(unittest.TestCase):
    def test_every_declared_skill_rendered(self):
        out = mb.render(wo(), "p1")
        self.assertIn("airflow-dag-authoring", out)
        self.assertIn("idempotent-backfill-authoring", out)

    def test_generalist_renders_without_a_skill_list(self):
        w = wo()
        w["parts"][0].update(role="generalist", skills=[], model="session")
        out = mb.render(w, "p1")
        self.assertIn("generalist", out)
        self.assertIn("no role skills", out.lower())


class TestReturnContract(unittest.TestCase):
    def test_return_schema_demanded(self):
        out = mb.render(wo(), "p1")
        for key in ("plan_id", "part_id", "ok", "summary", "skills_used"):
            self.assertIn(key, out, key)

    def test_ok_false_is_explained(self):
        # The agent must know that omitting ok:true is recorded as a failure.
        self.assertIn("ok", mb.render(wo(), "p1"))
        self.assertIn("false", mb.render(wo(), "p1").lower())

    def test_embedded_schema_is_valid_json(self):
        out = mb.render(wo(), "p1")
        start = out.index("{", out.index("```json"))
        depth, end = 0, None
        for i, ch in enumerate(out[start:], start):
            depth += (ch == "{") - (ch == "}")
            if depth == 0:
                end = i + 1
                break
        self.assertIsNotNone(end)
        json.loads(out[start:end])


class TestCarriedRules(unittest.TestCase):
    def test_grammar_rule_carried(self):
        self.assertIn("grammar", mb.render(wo(), "p1").lower())

    def test_evidence_rule_carried(self):
        self.assertIn("evidence", mb.render(wo(), "p1").lower())


class TestTraceparentHeader(unittest.TestCase):
    def test_brief_includes_traceparent_and_run_id(self):
        out = mb.render(wo(), "p1")
        self.assertIn("traceparent :", out)
        self.assertIn("run_id      : wo-20260730-x-abc123", out)
        expected_trace = obs_emit.trace_id_for("wo-20260730-x-abc123")
        self.assertIn(expected_trace, out)

    def test_traceparent_is_a_valid_w3c_shape(self):
        # Per the W3C Trace Context spec, an all-zero parent-id (span-id)
        # segment is explicitly invalid and conformant consumers MUST reject
        # the whole header. Assert the full shape, not just the trace_id
        # substring, so a regression back to the invalid form is caught.
        out = mb.render(wo(), "p1")
        self.assertRegex(out, r"traceparent : 00-[0-9a-f]{32}-[0-9a-f]{16}-01")
        self.assertNotIn("-0000000000000000-", out)


class TestErrors(unittest.TestCase):
    def test_unknown_part_raises(self):
        with self.assertRaises(KeyError):
            mb.render(wo(), "p9")

    def test_unassigned_part_raises(self):
        w = wo()
        w["parts"][0].update(status="pending", role=None)
        with self.assertRaises(mb.BriefError):
            mb.render(w, "p1")


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        pt.save(self.tmp, wo())

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(TOOLS / "make_brief.py"), "--state-dir", self.tmp] + list(args),
            capture_output=True, text=True)

    def test_cli_renders(self):
        r = self._run("wo-20260730-x-abc123", "p1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("airflow-dag-authoring", r.stdout)

    def test_cli_unknown_part_exits_nonzero(self):
        r = self._run("wo-20260730-x-abc123", "p9")
        self.assertNotEqual(r.returncode, 0)

    def test_cli_unknown_plan_exits_nonzero(self):
        r = self._run("wo-nope", "p1")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
