"""Tests for themes_pending — the NEW-row counter the SessionStart hook calls.

Written TDD-first: this module imports ``themes_pending`` before the tool
exists (RED = ModuleNotFoundError), then drives it GREEN. It covers the
counter (0 on a missing file; only ``| NEW |`` rows counted; header, separator,
comment, PROMOTED, DISMISSED, and malformed lines ignored) and the ``--list``
verbatim output. It also asserts the shipped seed ``learning/LOOP_THEMES.md``
counts zero — the repo seed is header-only.
"""
import io
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import themes_pending as tp  # noqa: E402

SEED = pathlib.Path(__file__).resolve().parents[2] / "learning" / "LOOP_THEMES.md"

HEADER = (
    "# Loop Themes — cross-task pattern log\n"
    "<!-- a comment that even mentions | NEW | must never be counted -->\n"
    "| status | date | project | theme-tag | note | metrics-ref |\n"
    "|---|---|---|---|---|---|\n"
)

# Two well-formed NEW rows, in file order.
NEW1 = ("| NEW | 2026-07-06 | 68_playground | slow-intake | "
        "intake re-derived a known answer | 2026-07#task_id=agent-aaa |")
NEW2 = ("| NEW | 2026-07-05 | 68_challenge_report | flaky-tunnel | "
        "ssh tunnel dropped mid-query | 2026-07#task_id=agent-bbb |")

# Rows that must NOT count.
PROMOTED = "| PROMOTED:slow-intake | 2026-07-01 | x | slow-intake | note | 2026-07#task_id=agent-ccc |"
DISMISSED = "| DISMISSED:one-off | 2026-06-30 | x | fluke | note | 2026-07#task_id=agent-ddd |"
MALFORMED_NOSPACE = "|NEW| 2026-07-04 | x | tag | note | ref |"      # no surrounding spaces
MALFORMED_NEWISH = "| NEWISH | 2026-07-04 | x | tag | note | ref |"  # different status word
MALFORMED_BARE = "NEW without any pipes at all"


def _write(text):
    td = tempfile.TemporaryDirectory()
    p = pathlib.Path(td.name) / "LOOP_THEMES.md"
    p.write_text(text, encoding="utf-8")
    return td, p


class TestThemesCounter(unittest.TestCase):
    def test_missing_file_is_zero(self):
        missing = pathlib.Path("/nonexistent/dir/LOOP_THEMES.md")
        self.assertEqual(tp.new_rows(missing), [])

    def test_seed_counts_zero(self):
        # The repo seed is header-only — no NEW rows yet.
        self.assertEqual(tp.new_rows(SEED), [])

    def test_counts_only_new_rows(self):
        text = (HEADER + NEW1 + "\n" + PROMOTED + "\n" + NEW2 + "\n"
                + DISMISSED + "\n" + MALFORMED_NOSPACE + "\n"
                + MALFORMED_NEWISH + "\n" + MALFORMED_BARE + "\n")
        td, p = _write(text)
        self.addCleanup(td.cleanup)
        self.assertEqual(tp.new_rows(p), [NEW1, NEW2])

    def test_malformed_lines_ignored(self):
        text = (HEADER + MALFORMED_NOSPACE + "\n" + MALFORMED_NEWISH + "\n"
                + MALFORMED_BARE + "\n")
        td, p = _write(text)
        self.addCleanup(td.cleanup)
        self.assertEqual(tp.new_rows(p), [])


class TestThemesCli(unittest.TestCase):
    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = tp.main(argv)
        return rc, buf.getvalue()

    def test_cli_count_prints_integer(self):
        text = HEADER + NEW1 + "\n" + PROMOTED + "\n" + NEW2 + "\n"
        td, p = _write(text)
        self.addCleanup(td.cleanup)
        rc, out = self._run(["--file", str(p)])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "2\n")

    def test_cli_count_missing_file_is_zero(self):
        rc, out = self._run(["--file", "/nonexistent/dir/LOOP_THEMES.md"])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "0\n")

    def test_cli_list_prints_rows_verbatim(self):
        text = HEADER + NEW1 + "\n" + PROMOTED + "\n" + NEW2 + "\n" + DISMISSED + "\n"
        td, p = _write(text)
        self.addCleanup(td.cleanup)
        rc, out = self._run(["--list", "--file", str(p)])
        self.assertEqual(rc, 0)
        self.assertEqual(out, NEW1 + "\n" + NEW2 + "\n")

    def test_cli_list_empty_when_no_new_rows(self):
        td, p = _write(HEADER)
        self.addCleanup(td.cleanup)
        rc, out = self._run(["--list", "--file", str(p)])
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
