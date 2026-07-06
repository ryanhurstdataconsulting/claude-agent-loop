import pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import lint_registry as lr

GOOD = "# Registry\n| alpha | skill | Use for X |\n| beta | tool | Use for Y |\n"


class TestLint(unittest.TestCase):
    def _ws(self, registry_text, guide_names):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = pathlib.Path(td.name)
        (root / "guides").mkdir()
        (root / "REGISTRY.md").write_text(registry_text)
        (root / "guides" / "_TEMPLATE.md").write_text("# template")
        for n in guide_names:
            (root / "guides" / f"{n}.md").write_text(f"# Guide — {n}")
        return root

    def test_clean_registry_passes(self):
        self.assertEqual(lr.lint(self._ws(GOOD, ["alpha", "beta"])), [])

    def test_separator_and_header_rows_ignored(self):
        text = "| name | category | trigger |\n|---|---|---|\n| alpha | skill | X |\n"
        self.assertEqual(lr.lint(self._ws(text, ["alpha"])), [])

    def test_bad_category_flagged(self):
        errs = lr.lint(self._ws("| alpha | wizard | X |\n", ["alpha"]))
        self.assertTrue(any("category" in e for e in errs))

    def test_missing_guide_flagged(self):
        errs = lr.lint(self._ws(GOOD, ["alpha"]))
        self.assertTrue(any("beta" in e and "guide" in e for e in errs))

    def test_orphan_guide_flagged(self):
        errs = lr.lint(self._ws(GOOD, ["alpha", "beta", "gamma"]))
        self.assertTrue(any("gamma" in e for e in errs))

    def test_duplicate_names_flagged(self):
        errs = lr.lint(self._ws("| alpha | skill | X |\n| alpha | tool | Y |\n", ["alpha"]))
        self.assertTrue(any("duplicate" in e.lower() for e in errs))

    def test_budget_enforced(self):
        rows = "\n".join(f"| r{i} | tool | t |" for i in range(151))
        errs = lr.lint(self._ws(rows, [f"r{i}" for i in range(151)]))
        self.assertTrue(any("150" in e for e in errs))

    def test_missing_registry_flagged(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = pathlib.Path(td.name)
        (root / "guides").mkdir()
        errs = lr.lint(root)
        self.assertTrue(any("missing" in e for e in errs))

    def test_malformed_row_flagged(self):
        errs = lr.lint(self._ws("| only-two | cols |\n", []))
        self.assertTrue(any("malformed" in e for e in errs))

    def test_empty_trigger_flagged(self):
        errs = lr.lint(self._ws("| alpha | skill |  |\n", ["alpha"]))
        self.assertTrue(any("trigger" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
