#!/usr/bin/env python3
"""Tests for route_role.py — deterministic task -> role routing."""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
ROUTER = TOOLS / "route_role.py"
REPO = TOOLS.parent.parent

ROLE_A = """---
name: dba
description: Database administration.
role: dba
routes:
  - slow query · EXPLAIN ANALYZE · query plan
  - index · autovacuum · pgBouncer
skills:
  - explain-analyze-query-tuning
  - index-strategy-design
mcps:
  - postgres-readonly
---
# dba
"""

ROLE_B = """---
name: product-manager
description: Product management.
role: product-manager
routes:
  - PRD · product spec · requirements document
  - roadmap · OKR · prioritize the backlog
skills:
  - write-a-prd
mcps: []
---
# product-manager
"""


def run(args):
    return subprocess.run([sys.executable, str(ROUTER)] + args,
                          capture_output=True, text=True)


class Routing(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.roles = self.tmp / "roles"
        self.roles.mkdir()
        (self.roles / "dba.md").write_text(ROLE_A)
        (self.roles / "product-manager.md").write_text(ROLE_B)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def route(self, task):
        r = run(["--roles-dir", str(self.roles), "--json", task])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_routes_db_task_to_dba(self):
        d = self.route("this slow query needs an EXPLAIN ANALYZE pass")
        self.assertEqual(d["role"], "dba")
        self.assertIn("explain-analyze-query-tuning", d["skills"])
        self.assertIn("postgres-readonly", d["mcps"])
        self.assertTrue(d["matched"])

    def test_routes_prd_task_to_pm(self):
        d = self.route("turn this feature brief into a PRD with a roadmap")
        self.assertEqual(d["role"], "product-manager")

    def test_unmatched_falls_back_to_generalist(self):
        d = self.route("water the office plants")
        self.assertEqual(d["role"], "generalist")
        self.assertEqual(d["skills"], [])

    def test_case_insensitive(self):
        d = self.route("SLOW QUERY against the warehouse")
        self.assertEqual(d["role"], "dba")

    def test_human_line_output(self):
        r = run(["--roles-dir", str(self.roles), "index bloat and autovacuum lag"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("Role — dba", r.stdout)
        self.assertIn("skills:", r.stdout)

    def test_malformed_role_file_tolerated(self):
        (self.roles / "broken.md").write_text("not frontmatter")
        d = self.route("slow query plan")
        self.assertEqual(d["role"], "dba")  # still routes despite the bad file

    def test_empty_task_is_generalist(self):
        d = self.route("")
        self.assertEqual(d["role"], "generalist")


class RepoRoles(unittest.TestCase):
    """Golden routes against the repo's real role files."""

    def route(self, task):
        r = run(["--roles-dir", str(REPO / "payload" / "agents" / "roles"),
                 "--json", task])
        return json.loads(r.stdout)

    def test_golden_routes(self):
        cases = [
            ("design an A/B test with a power analysis", "data-scientist"),
            ("author an Airflow DAG for the nightly pipeline", "data-engineer"),
            ("this slow query needs EXPLAIN ANALYZE", "dba"),
            ("run a Well-Architected review of our VPC design", "cloud-architect"),
            ("write a PRD and prioritize the backlog", "product-manager"),
            ("run a heuristic evaluation and map the user journey", "product-designer"),
            ("our Lighthouse score tanked — audit the Core Web Vitals", "frontend-engineer"),
            ("scaffold a REST endpoint with request validation", "backend-engineer"),
            ("set up a Fastlane release pipeline for the iOS app", "mobile-engineer"),
            ("write an RTOS task and a peripheral driver for the sensor", "embedded-engineer"),
            ("draft an ADR for the service boundary split", "software-architect"),
            ("harden the Dockerfile and set up the GitOps deployment", "devops-engineer"),
            ("define SLOs and an error budget for the API", "sre"),
            ("threat-model this diff and wire SAST scanning into CI", "security-engineer"),
            ("triage these flaky tests and author an E2E suite", "qa-engineer"),
            ("write the release notes and update the Diátaxis docs", "technical-writer"),
            ("draft the performance review from my 1:1 notes", "engineering-manager"),
        ]
        for task, want in cases:
            got = self.route(task)["role"]
            self.assertEqual(got, want, "task %r -> %r (want %r)" % (task, got, want))


if __name__ == "__main__":
    unittest.main(verbosity=1)
