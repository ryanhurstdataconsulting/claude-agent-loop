"""Tests for classify_visibility — the default-deny visibility classifier (P5).

Written TDD-first: this module imports ``classify_visibility`` before the tool
exists (RED = ModuleNotFoundError), then drives it GREEN.

SAFETY: these tests NEVER read the real ``~/.claude/learning/CLIENT_MARKERS.txt``.
Every case supplies a synthetic markers file (or ``markers=None`` to simulate a
missing one). The fixtures below carry no real client name, host, or datum.

Coverage:
  * a marker hit in the path OR the content → CLIENT (matched markers reported);
  * no marker but a structural risk signal (``/Users/<name>``, an email, a
    ``user@host`` ssh target, an IP) → UNSURE;
  * clean generic content → GENERIC;
  * a missing markers file → every input UNSURE, fail-CLOSED (never GENERIC);
  * exit codes: 0 (all GENERIC) · 3 (any CLIENT/UNSURE) · 2 (usage error).
"""
import io
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import classify_visibility as cv  # noqa: E402

# Synthetic markers — nothing real. "widgetco" stands in for a client name.
MARKERS = ["widgetco", "widget-internal", "jane doe"]


def _markers_file(lines):
    td = tempfile.TemporaryDirectory()
    p = pathlib.Path(td.name) / "CLIENT_MARKERS.txt"
    body = "# a comment line that names widgetco must not count as a marker\n\n"
    p.write_text(body + "\n".join(lines) + "\n", encoding="utf-8")
    return td, p


class TestClassifyCore(unittest.TestCase):
    def test_marker_in_content_is_client(self):
        verdict, detail = cv.classify("we ship to widgetco tomorrow",
                                      "notes.md", MARKERS)
        self.assertEqual(verdict, "CLIENT")
        self.assertIn("widgetco", detail)

    def test_marker_in_path_is_client(self):
        verdict, detail = cv.classify("totally generic body",
                                      "reports/widgetco-summary.md", MARKERS)
        self.assertEqual(verdict, "CLIENT")
        self.assertIn("widgetco", detail)

    def test_marker_match_is_case_insensitive(self):
        verdict, _ = cv.classify("WidgetCo shipped it", "x.md", MARKERS)
        self.assertEqual(verdict, "CLIENT")

    def test_structural_userpath_is_unsure(self):
        verdict, detail = cv.classify("path is /Users/janedoe/work/x",
                                      "x.md", MARKERS)
        self.assertEqual(verdict, "UNSURE")
        self.assertIn("structural", detail)

    def test_structural_email_is_unsure(self):
        verdict, _ = cv.classify("reach me at someone@example.com",
                                 "x.md", MARKERS)
        self.assertEqual(verdict, "UNSURE")

    def test_structural_ssh_host_is_unsure(self):
        verdict, _ = cv.classify("ssh deploy@build01.internal for the run",
                                 "x.md", MARKERS)
        self.assertEqual(verdict, "UNSURE")

    def test_structural_ip_is_unsure(self):
        verdict, _ = cv.classify("bind to 10.1.2.3 on boot", "x.md", MARKERS)
        self.assertEqual(verdict, "UNSURE")

    def test_clean_generic_content(self):
        verdict, detail = cv.classify(
            "A generic tool that lints a table. 12 rows checked.",
            "tools/lint_table.py", MARKERS)
        self.assertEqual(verdict, "GENERIC")

    def test_missing_markers_fails_closed_unsure(self):
        # markers=None models a missing markers file — must NOT be GENERIC.
        verdict, detail = cv.classify("perfectly generic text", "x.md", None)
        self.assertEqual(verdict, "UNSURE")
        self.assertIn("no-markers-file", detail)

    def test_marker_beats_structural(self):
        # Both a marker and a structural signal present → CLIENT wins.
        verdict, detail = cv.classify("widgetco at /Users/janedoe/x",
                                      "x.md", MARKERS)
        self.assertEqual(verdict, "CLIENT")


class TestLoadMarkers(unittest.TestCase):
    def test_comments_and_blanks_ignored(self):
        td, p = _markers_file(MARKERS)
        self.addCleanup(td.cleanup)
        loaded = cv.load_markers(p)
        self.assertEqual(loaded, MARKERS)

    def test_missing_file_returns_none(self):
        self.assertIsNone(
            cv.load_markers(pathlib.Path("/nonexistent/CLIENT_MARKERS.txt")))


class TestCli(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cv.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def _clean_file(self, body="a generic line, 12 rows\n", name="clean.py"):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        p = pathlib.Path(td.name) / name
        p.write_text(body, encoding="utf-8")
        return p

    def test_all_generic_exits_zero(self):
        td, mp = _markers_file(MARKERS)
        self.addCleanup(td.cleanup)
        p = self._clean_file()
        rc, out, _ = self._run(["--markers", str(mp), str(p)])
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("GENERIC\t"), out)

    def test_client_exits_three(self):
        td, mp = _markers_file(MARKERS)
        self.addCleanup(td.cleanup)
        p = self._clean_file(body="serving widgetco now\n")
        rc, out, _ = self._run(["--markers", str(mp), str(p)])
        self.assertEqual(rc, 3)
        self.assertIn("CLIENT\t", out)

    def test_unsure_exits_three(self):
        td, mp = _markers_file(MARKERS)
        self.addCleanup(td.cleanup)
        p = self._clean_file(body="ip is 192.168.0.9 here\n")
        rc, out, _ = self._run(["--markers", str(mp), str(p)])
        self.assertEqual(rc, 3)
        self.assertIn("UNSURE\t", out)

    def test_missing_markers_file_exits_three_and_warns(self):
        p = self._clean_file()
        rc, out, err = self._run(["--markers", "/nonexistent/M.txt", str(p)])
        self.assertEqual(rc, 3)
        self.assertIn("UNSURE\t", out)
        self.assertTrue(err.strip(), "expected a warning on stderr")

    def test_text_mode(self):
        td, mp = _markers_file(MARKERS)
        self.addCleanup(td.cleanup)
        rc, out, _ = self._run(["--markers", str(mp), "--text",
                                "generic content"])
        self.assertEqual(rc, 0)
        self.assertIn("GENERIC\t", out)

    def test_no_input_is_usage_error_exit_two(self):
        td, mp = _markers_file(MARKERS)
        self.addCleanup(td.cleanup)
        rc, _, _ = self._run(["--markers", str(mp)])
        self.assertEqual(rc, 2)

    def test_output_line_is_tab_delimited(self):
        td, mp = _markers_file(MARKERS)
        self.addCleanup(td.cleanup)
        p = self._clean_file(body="serving widgetco\n")
        rc, out, _ = self._run(["--markers", str(mp), str(p)])
        first = out.splitlines()[0]
        parts = first.split("\t")
        self.assertEqual(len(parts), 3, first)
        self.assertEqual(parts[0], "CLIENT")


if __name__ == "__main__":
    unittest.main()
