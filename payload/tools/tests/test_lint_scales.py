"""Tests for lint_scales — the SCALES.md row-grammar linter (P3).

Written TDD-first: this module imports ``lint_scales`` before the tool exists
(RED = ModuleNotFoundError), then drives it GREEN. It clones the shape of
``test_lint_registry.py`` (tempdir workspace, per-rule violation coverage) and
additionally asserts the shipped seed ``learning/SCALES.md`` passes clean.
"""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import lint_scales as ls  # noqa: E402

SEED = pathlib.Path(__file__).resolve().parents[2] / "learning" / "SCALES.md"

CORE = "## Core (framework seed)"
EXT = "## Extended (learned on this machine)"


class TestLintScales(unittest.TestCase):
    def _lint(self, text):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        p = pathlib.Path(td.name) / "SCALES.md"
        p.write_text(text)
        return ls.lint(p)

    def test_seed_file_passes(self):
        self.assertEqual(ls.lint(SEED), [])

    def test_both_section_headers_accepted(self):
        text = (f"# Title\n{CORE}\n| a | x>y | any task | desc |\n"
                f"{EXT}\n| b | p>q>r | any task | desc |\n")
        self.assertEqual(self._lint(text), [])

    def test_duplicate_id_flagged_with_line(self):
        text = f"{CORE}\n| a | x>y | t | d |\n| a | p>q | t | d |\n"
        errs = self._lint(text)
        self.assertTrue(any("duplicate" in e.lower() and "line 3" in e
                            for e in errs), errs)

    def test_single_level_flagged_with_line(self):
        text = f"{CORE}\n| a | onlyone | t | d |\n"
        errs = self._lint(text)
        self.assertTrue(any("line 2" in e and ("tokens" in e or ">=2" in e)
                            for e in errs), errs)

    def test_empty_field_flagged_with_line(self):
        text = f"{CORE}\n| a | x>y |  | d |\n"
        errs = self._lint(text)
        self.assertTrue(any("applies-to" in e and "line 2" in e
                            for e in errs), errs)

    def test_over_budget_flagged(self):
        rows = "\n".join(f"| s{i} | x>y | t | d |" for i in range(41))
        errs = self._lint(f"{CORE}\n{rows}\n")
        self.assertTrue(any("40" in e for e in errs), errs)

    def test_malformed_row_flagged_with_line(self):
        text = f"{CORE}\n| only-two | cols |\n"
        errs = self._lint(text)
        self.assertTrue(any("malformed" in e and "line 2" in e
                            for e in errs), errs)

    def test_unknown_section_header_flagged(self):
        text = "## Bogus Section\n| a | x>y | t | d |\n"
        errs = self._lint(text)
        self.assertTrue(any("unknown section" in e.lower() for e in errs), errs)

    def test_non_kebab_id_flagged(self):
        text = f"{CORE}\n| Bad_ID | x>y | t | d |\n"
        errs = self._lint(text)
        self.assertTrue(any("kebab" in e.lower() and "line 2" in e
                            for e in errs), errs)

    def test_level_token_with_space_flagged(self):
        text = f"{CORE}\n| a | good > bad | t | d |\n"
        errs = self._lint(text)
        self.assertTrue(any("line 2" in e and "level" in e.lower()
                            for e in errs), errs)

    def test_missing_file_flagged(self):
        errs = ls.lint(pathlib.Path("/nonexistent/SCALES.md"))
        self.assertTrue(any("missing" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
