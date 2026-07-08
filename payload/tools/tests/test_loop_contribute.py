#!/usr/bin/env python3
"""Tests for loop_contribute.py — gate-cleared local resources auto-push to a
contrib/* branch (never main); CLIENT/UNSURE content never leaves the machine."""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
CONTRIB = TOOLS / "loop_contribute.py"

GENERIC_SKILL = """---
name: retry-budget-design
description: Use when an integration needs a retry budget so retries cannot amplify an outage.
---

# retry-budget-design

## Overview
Caps total retry volume so a downstream outage is not amplified by the callers.
"""

CLIENT_SKILL = GENERIC_SKILL.replace(
    "amplified by the callers", "amplified (built for the acmecorp-internal rollout)")


def run(args, env=None):
    import os
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, str(CONTRIB)] + args,
                          capture_output=True, text=True, env=e)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        g = lambda cwd, *a: subprocess.run(  # noqa: E731
            ["git", "-C", str(cwd)] + list(a), capture_output=True, text=True)
        # bare origin + framework clone with a payload skeleton on main
        self.origin = self.tmp / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.origin)])
        self.repo = self.tmp / "repo"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.repo)])
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            g(self.repo, "config", k, v)
        g(self.repo, "checkout", "-b", "main")
        (self.repo / "payload" / "skills").mkdir(parents=True)
        (self.repo / "payload" / "MANIFEST").write_text(
            "# manifest\n# --- skills ---\nlink-dir skills/existing\n")
        g(self.repo, "add", "-A")
        g(self.repo, "commit", "-m", "init")
        g(self.repo, "push", "-u", "origin", "main")
        # local ~/.claude with one candidate local skill
        self.claude = self.tmp / "claude"
        (self.claude / "skills" / "retry-budget-design").mkdir(parents=True)
        (self.claude / "skills" / "retry-budget-design" / "SKILL.md").write_text(GENERIC_SKILL)
        (self.claude / "learning").mkdir()
        self.markers = self.claude / "learning" / "CLIENT_MARKERS.txt"
        self.markers.write_text("acmecorp-internal\n")
        (self.claude / "metrics").mkdir()
        (self.claude / "metrics" / "2026-07.jsonl").write_text(
            json.dumps({"schema": 1, "kind": "task", "task_id": "t1",
                        "resources_deployed": ["retry-budget-design"],
                        "error_rate": 0.1, "tests": {"passed": 7, "failed": 0}}) + "\n")
        self.state = self.claude / "learning" / "contributed.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def contribute(self, extra=None, env=None):
        return run(["--claude-dir", str(self.claude), "--repo", str(self.repo),
                    "--markers-file", str(self.markers)] + (extra or []), env=env)

    def origin_branches(self):
        r = subprocess.run(["git", "-C", str(self.origin), "branch", "--list"],
                           capture_output=True, text=True)
        return r.stdout

    def origin_file(self, branch, path):
        r = subprocess.run(["git", "-C", str(self.origin), "show",
                            "%s:%s" % (branch, path)], capture_output=True, text=True)
        return r.returncode, r.stdout

    def contrib_branch(self):
        for line in self.origin_branches().splitlines():
            name = line.strip().lstrip("* ").strip()
            if name.startswith("contrib/"):
                return name
        return None

    def test_kill_switch(self):
        r = self.contribute(env={"AGENT_LOOP_CONTRIBUTE": "0"})
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("contrib/", self.origin_branches())

    def test_generic_skill_pushes_to_contrib_branch(self):
        r = self.contribute()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        br = self.contrib_branch()
        self.assertIsNotNone(br, "no contrib branch pushed: " + self.origin_branches())
        # the skill landed in payload
        rc, body = self.origin_file(br, "payload/skills/retry-budget-design/SKILL.md")
        self.assertEqual(rc, 0)
        self.assertIn("retry-budget-design", body)
        # MANIFEST gained the link-dir line
        rc, mani = self.origin_file(br, "payload/MANIFEST")
        self.assertIn("link-dir skills/retry-budget-design", mani)
        # a summary with the four sections exists
        rc, ls = self.origin_file(br, "contributions")
        found = None
        r2 = subprocess.run(["git", "-C", str(self.origin), "ls-tree", "-r",
                             "--name-only", br], capture_output=True, text=True)
        for p in r2.stdout.splitlines():
            if p.startswith("contributions/") and p.endswith(".md"):
                found = p
        self.assertIsNotNone(found, r2.stdout)
        rc, summ = self.origin_file(br, found)
        for heading in ("## What changed", "## How it improved the local environment",
                        "## Agent-performance delta",
                        "## How to implement it into the main project"):
            self.assertIn(heading, summ)
        # metrics evidence made it into the summary
        self.assertIn("7 passed", summ)
        # stdout carries the branch reference (the "link")
        self.assertIn(br, r.stdout)
        # main untouched
        rc, _ = self.origin_file("main", "payload/skills/retry-budget-design/SKILL.md")
        self.assertNotEqual(rc, 0)
        # state recorded
        self.assertTrue(self.state.is_file())
        self.assertIn("retry-budget-design", self.state.read_text())

    def test_client_marked_skill_is_withheld(self):
        (self.claude / "skills" / "retry-budget-design" / "SKILL.md").write_text(CLIENT_SKILL)
        r = self.contribute()
        self.assertEqual(r.returncode, 0)
        self.assertIsNone(self.contrib_branch(), "CLIENT content must never push")
        self.assertIn("withheld", r.stdout.lower())

    def test_rerun_is_idempotent(self):
        self.contribute()
        first = self.origin_branches()
        r = self.contribute()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(first, self.origin_branches(), "second run must not re-push")
        self.assertIn("nothing new", r.stdout.lower())

    def test_nudge_counts_pending(self):
        r = self.contribute(["--nudge"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("contribution", r.stdout.lower())
        self.assertNotIn("contrib/", self.origin_branches())  # nudge never pushes

    def test_symlinked_framework_content_ignored(self):
        # a symlink into the repo must not be treated as a local candidate
        (self.claude / "skills" / "linked").symlink_to(self.repo / "payload" / "skills")
        r = self.contribute(["--nudge"])
        self.assertNotIn("linked", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
