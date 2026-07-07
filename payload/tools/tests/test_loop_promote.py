"""Tests for loop_promote — the read-only learning-vs-seed diff tool (P5).

Written TDD-first: imports ``loop_promote`` before it exists (RED). The tool
must show a unified diff of the LOCAL learning files against the repo SEEDS,
print the owner-review instructions, and NEVER write a byte to either side.
"""
import io
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import loop_promote as lp  # noqa: E402

SEED_SCALES = ("## Core (framework seed)\n"
               "| outcome | great>good>bad>horrible | any task | seed |\n"
               "## Extended (learned on this machine)\n")
SEED_HEUR = "# Heuristics\n\n## H1 — seed-rule\n- WHEN: x\n"


class TestLoopPromote(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        base = pathlib.Path(self.td.name)
        self.learning = base / "learning"
        self.seeds = base / "seeds"
        self.learning.mkdir()
        self.seeds.mkdir()
        # Seeds.
        (self.seeds / "SCALES.md").write_text(SEED_SCALES, encoding="utf-8")
        (self.seeds / "HEURISTICS.md").write_text(SEED_HEUR, encoding="utf-8")
        # Local: SCALES diverged (a learned Extended row), HEURISTICS identical.
        self.local_scales = SEED_SCALES + \
            "| intake-speed | fast>ok>slow | intake | learned locally |\n"
        (self.learning / "SCALES.md").write_text(self.local_scales,
                                                 encoding="utf-8")
        (self.learning / "HEURISTICS.md").write_text(SEED_HEUR, encoding="utf-8")

    def _run(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = lp.main(["--learning-dir", str(self.learning),
                          "--seeds-dir", str(self.seeds)])
        return rc, buf.getvalue()

    def test_diff_shows_local_addition(self):
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("SCALES.md", out)
        # The learned Extended row appears as an addition in the diff.
        self.assertIn("+| intake-speed | fast>ok>slow", out)

    def test_identical_file_reports_no_difference(self):
        rc, out = self._run()
        # HEURISTICS.md is identical to its seed — reported, not diffed.
        self.assertRegex(out, r"(?s)HEURISTICS\.md.*(identical|no diff|no differ)")

    def test_prints_owner_review_instructions(self):
        _, out = self._run()
        self.assertIn("classify_visibility", out)
        self.assertRegex(out.lower(), r"owner|review")

    def test_never_writes(self):
        before_local = (self.learning / "SCALES.md").read_text()
        before_seed = (self.seeds / "SCALES.md").read_text()
        self._run()
        self.assertEqual((self.learning / "SCALES.md").read_text(), before_local)
        self.assertEqual((self.seeds / "SCALES.md").read_text(), before_seed)

    def test_missing_local_file_is_tolerated(self):
        (self.learning / "SCALES.md").unlink()
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("SCALES.md", out)


if __name__ == "__main__":
    unittest.main()
