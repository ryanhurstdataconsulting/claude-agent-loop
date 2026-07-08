#!/usr/bin/env python3
"""Tests for lint_roles.py — role-agent frontmatter, skill/MCP bijection."""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
LINT = TOOLS / "lint_roles.py"
REPO = TOOLS.parent.parent  # repo root (payload/..)

GOOD = """---
name: sample-role
description: Use this agent for sample things.
role: sample-role
routes:
  - sample keyword · another phrase
skills:
  - skill-a
  - skill-b
mcps:
  - mcp-x
---

# sample-role
Body.
"""

REGISTRY = """# index
## MCPs
| mcp-x | mcp | sample server |
"""


def run(args):
    return subprocess.run([sys.executable, str(LINT)] + args,
                          capture_output=True, text=True)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.roles = self.tmp / "roles"
        self.skills = self.tmp / "skills"
        self.roles.mkdir()
        for s in ("skill-a", "skill-b"):
            d = self.skills / s
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text("---\nname: %s\ndescription: x\n---\n" % s)
        self.registry = self.tmp / "REGISTRY.md"
        self.registry.write_text(REGISTRY)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lint(self):
        return run([str(self.roles), "--skills-dir", str(self.skills),
                    "--registry", str(self.registry)])

    def test_clean_role_passes(self):
        (self.roles / "sample-role.md").write_text(GOOD)
        r = self.lint()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK (0 error(s))", r.stdout)

    def test_missing_skill_fails(self):
        (self.roles / "sample-role.md").write_text(GOOD.replace("skill-b", "skill-nope"))
        r = self.lint()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("skill-nope", r.stdout)

    def test_unknown_mcp_fails(self):
        (self.roles / "sample-role.md").write_text(GOOD.replace("mcp-x", "mcp-ghost"))
        r = self.lint()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("mcp-ghost", r.stdout)

    def test_name_filename_mismatch_fails(self):
        (self.roles / "other-name.md").write_text(GOOD)
        r = self.lint()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("other-name", r.stdout)

    def test_empty_routes_fails(self):
        bad = GOOD.replace("routes:\n  - sample keyword · another phrase\n", "routes:\n")
        (self.roles / "sample-role.md").write_text(bad)
        r = self.lint()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("routes", r.stdout.lower())

    def test_empty_mcps_allowed(self):
        ok = GOOD.replace("mcps:\n  - mcp-x\n", "mcps: []\n")
        (self.roles / "sample-role.md").write_text(ok)
        r = self.lint()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_malformed_frontmatter_fails(self):
        (self.roles / "sample-role.md").write_text("no frontmatter at all\n")
        r = self.lint()
        self.assertNotEqual(r.returncode, 0)


class RepoRoles(unittest.TestCase):
    """The repo's real payload roles must lint clean against the real library."""

    def test_payload_roles_lint_clean(self):
        roles = REPO / "payload" / "agents" / "roles"
        if not roles.is_dir():
            self.skipTest("no payload roles dir")
        r = run([str(roles), "--skills-dir", str(REPO / "payload" / "skills"),
                 "--registry", str(REPO / "payload" / "registry" / "REGISTRY.md")])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
