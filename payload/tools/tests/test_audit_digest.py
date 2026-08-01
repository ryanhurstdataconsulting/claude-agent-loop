#!/usr/bin/env python3
"""Tests for audit_digest — the digest/alert/nudge surfacing layer for the
repo-security-audit scheduler.

Hermetic: every case builds its store under ``tempfile.mkdtemp()`` and tears
it down. Fixtures mirror the REAL run-log schema ``audit_run.sh``'s
``_write_run_log`` writes (schema, package, package_path, verdict, head_sha,
findings{critical,high,medium,low}, run_at, gates, note, ...) — read straight
from the shell function, not guessed at. No package name here is a real
client package.
"""
import datetime
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import audit_digest as ad  # noqa: E402  (path set up above)
import prose_grammar_gate as pg  # noqa: E402


def make_run(package, date, verdict="ok", critical=0, high=0, medium=0, low=0,
             run_at=None, note=None, no_findings=False):
    """Build a run-log record shaped exactly like ``_write_run_log`` writes."""
    return {
        "schema": 1,
        "package": package,
        "package_path": "/workspace/" + package,
        "date": date,
        "verdict": verdict,
        "head_sha": "abc123def",
        "branch": ("audit/security-" + date) if verdict == "ok" else None,
        "commit": "deadbeef" if verdict == "ok" else None,
        "findings": None if no_findings else {
            "critical": critical, "high": high, "medium": medium, "low": low,
        },
        "run_at": run_at or (date + "T03:00:00Z"),
        "duration_seconds": 118,
        "num_turns": 6,
        "max_turns": 40,
        "timeout_seconds": 3600,
        "cli_exit": 0,
        "gates": {"secret_pii_scrub": "pass", "prose_grammar": "pass"},
        "note": note,
    }


def write_run(root, run):
    """Persist ``run`` at ``<root>/audit/runs/<pkg>/<date>.json``, plus a
    realistic ``state.json`` sibling on a successful run — the digest reader
    must skip that sibling rather than mistake it for a run record."""
    run_dir = pathlib.Path(root) / "audit" / "runs" / run["package"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / (run["date"] + ".json")).write_text(
        json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if run["verdict"] == "ok":
        (run_dir / "state.json").write_text(
            json.dumps({
                "last_audit_date": run["run_at"],
                "last_audited_sha": run["head_sha"],
                "package": run["package"],
                "branch": run["branch"],
                "verdict": "ok",
            }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class TestSeverityAlert(unittest.TestCase):
    def test_critical_alerts(self):
        self.assertIsNotNone(ad.severity_alert(
            {"package": "p", "findings": {"critical": 1, "high": 0}}))

    def test_high_alerts(self):
        self.assertIsNotNone(ad.severity_alert(
            {"package": "p", "findings": {"critical": 0, "high": 2}}))

    def test_medium_and_low_do_not_alert(self):
        self.assertIsNone(ad.severity_alert(
            {"package": "p", "findings": {"critical": 0, "high": 0,
                                          "medium": 5, "low": 9}}))

    def test_alert_names_the_package_and_count(self):
        msg = ad.severity_alert({"package": "acme", "findings": {"critical": 2, "high": 0}})
        self.assertIn("acme", msg)
        self.assertIn("2", msg)

    def test_ok_verdict_zero_findings_does_not_alert(self):
        self.assertIsNone(ad.severity_alert(make_run("acme", "2026-07-30")))

    def test_blocked_verdict_alerts_even_at_zero_findings(self):
        run = make_run("acme", "2026-07-30", verdict="blocked",
                       note="secret_pii_scrub_gate refused the audit output")
        msg = ad.severity_alert(run)
        self.assertIsNotNone(msg)
        self.assertIn("acme", msg)

    def test_failed_verdict_alerts_with_null_findings(self):
        # A crashed CLI never produces parseable findings — the real writer
        # leaves `findings: null` on a failed run. Zero findings must not
        # read as "nothing to see" here.
        run = make_run("acme", "2026-07-30", verdict="failed",
                       no_findings=True, note="claude CLI not found")
        msg = ad.severity_alert(run)
        self.assertIsNotNone(msg)
        self.assertIn("acme", msg)

    def test_many_mediums_never_escalate(self):
        # The whole point of the severity split: volume of Medium/Low never
        # crosses the line that only Critical/High (or blocked/failed) cross.
        run = make_run("acme", "2026-07-30", medium=40, low=100)
        self.assertIsNone(ad.severity_alert(run))


class TestRender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_since_none_includes_everything(self):
        write_run(self.tmp, make_run("acme", "2026-07-29"))
        write_run(self.tmp, make_run("widget", "2026-07-30", critical=1))
        text = ad.render(self.tmp, None)
        self.assertIn("acme", text)
        self.assertIn("widget", text)
        self.assertIn("Total runs in window: 2", text)

    def test_since_filters_older_runs(self):
        write_run(self.tmp, make_run("acme", "2026-07-29", run_at="2026-07-29T03:00:00Z"))
        write_run(self.tmp, make_run("widget", "2026-07-30", run_at="2026-07-30T03:00:00Z"))
        text = ad.render(self.tmp, "2026-07-29T12:00:00Z")
        self.assertNotIn("acme", text)
        self.assertIn("widget", text)

    def test_separates_alerts_from_routine(self):
        write_run(self.tmp, make_run("acme", "2026-07-30", critical=3))
        write_run(self.tmp, make_run("widget", "2026-07-30", medium=2))
        text = ad.render(self.tmp, None)
        self.assertIn("## Alerts (1)", text)
        self.assertIn("## Routine (1)", text)
        alerts_section = text.split("## Routine")[0]
        self.assertIn("acme", alerts_section)
        self.assertNotIn("widget", alerts_section)

    def test_blocked_and_failed_land_in_alerts_not_routine(self):
        write_run(self.tmp, make_run("acme", "2026-07-30", verdict="blocked",
                                     note="prose_grammar_gate refused the audit output"))
        text = ad.render(self.tmp, None)
        self.assertIn("## Alerts (1)", text)
        self.assertIn("## Routine (0)", text)

    def test_state_json_is_never_read_as_a_run(self):
        write_run(self.tmp, make_run("acme", "2026-07-30"))
        text = ad.render(self.tmp, None)
        self.assertIn("Total runs in window: 1", text)

    def test_no_runs_is_not_an_error(self):
        text = ad.render(self.tmp, None)
        self.assertIn("Total runs in window: 0", text)
        self.assertIn("## Alerts (0)", text)
        self.assertIn("## Routine (0)", text)

    def test_generated_prose_passes_grammar_gate(self):
        write_run(self.tmp, make_run("acme", "2026-07-30", critical=1))
        write_run(self.tmp, make_run("widget", "2026-07-30", medium=3))
        write_run(self.tmp, make_run("gizmo", "2026-07-30", verdict="failed",
                                     no_findings=True, note="claude CLI not found"))
        text = ad.render(self.tmp, None)
        findings = pg.lint_text(text)
        self.assertEqual(findings, [], findings)


class TestWriteDigest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_writes_a_markdown_file_under_digests(self):
        write_run(self.tmp, make_run("acme", "2026-07-30", critical=1))
        path = ad.write_digest(self.tmp)
        p = pathlib.Path(path)
        self.assertTrue(p.is_file())
        self.assertEqual(p.parent, pathlib.Path(self.tmp) / "audit" / "digests")
        self.assertIn("acme", p.read_text(encoding="utf-8"))

    def test_advances_last_digest_marker(self):
        write_run(self.tmp, make_run("acme", "2026-07-30"))
        ad.write_digest(self.tmp)
        marker = pathlib.Path(self.tmp) / "audit" / "digests" / ".last-digest"
        self.assertTrue(marker.is_file())
        self.assertTrue(marker.read_text(encoding="utf-8").strip())

    def test_second_call_windows_off_the_first(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        earlier = (now - datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        later = (now + datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

        write_run(self.tmp, make_run("acme", "2020-01-01", run_at=earlier))
        ad.write_digest(self.tmp)

        write_run(self.tmp, make_run("widget", "2020-01-02", run_at=later))
        path = ad.write_digest(self.tmp)
        text = pathlib.Path(path).read_text(encoding="utf-8")
        self.assertIn("widget", text)
        self.assertNotIn("acme", text)


class TestNudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_no_digest_no_nudge(self):
        self.assertEqual(ad.nudge(self.tmp), "")

    def test_unread_digest_produces_one_line(self):
        write_run(self.tmp, make_run("acme", "2026-07-30", critical=1))
        ad.write_digest(self.tmp)
        line = ad.nudge(self.tmp)
        self.assertEqual(len(line.splitlines()), 1)
        self.assertIn("audit", line.lower())

    def test_nudge_is_self_consuming(self):
        # Reported once, then silent — the same shape as the loop-close
        # section's "consume the artifact after reporting it" behaviour, so a
        # routine digest never nags every session until acted on.
        write_run(self.tmp, make_run("acme", "2026-07-30"))
        ad.write_digest(self.tmp)
        first = ad.nudge(self.tmp)
        self.assertNotEqual(first, "")
        second = ad.nudge(self.tmp)
        self.assertEqual(second, "")

    def test_a_later_digest_is_unread_again(self):
        write_run(self.tmp, make_run("acme", "2026-07-30"))
        ad.write_digest(self.tmp)
        self.assertNotEqual(ad.nudge(self.tmp), "")
        self.assertEqual(ad.nudge(self.tmp), "")

        digests_dir = pathlib.Path(self.tmp) / "audit" / "digests"
        future = (datetime.datetime.now(datetime.timezone.utc)
                 + datetime.timedelta(days=10)).strftime("%Y-%m-%d")
        (digests_dir / (future + ".md")).write_text("# stub\n", encoding="utf-8")
        self.assertNotEqual(ad.nudge(self.tmp), "")


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _run(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ad.main(list(argv) + ["--root", self.tmp])
        return rc, buf.getvalue()

    def test_default_action_writes_and_prints_path(self):
        write_run(self.tmp, make_run("acme", "2026-07-30", critical=1))
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertTrue(pathlib.Path(out.strip()).is_file())

    def test_nudge_flag_prints_line_when_unread(self):
        write_run(self.tmp, make_run("acme", "2026-07-30", critical=1))
        self._run()
        rc, out = self._run("--nudge")
        self.assertEqual(rc, 0)
        self.assertIn("audit", out.lower())

    def test_nudge_flag_silent_with_no_digest(self):
        rc, out = self._run("--nudge")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
