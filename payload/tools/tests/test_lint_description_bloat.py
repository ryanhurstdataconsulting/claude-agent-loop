import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import lint_description_bloat as ldb

SHORT_DESC = "Use when doing X — short and to the point."
LONG_DESC = " ".join(["word"] * 101)
LONG_BULLET_DESC = " ".join(["word"] * 41)
SHORT_BULLET_DESC = "short bullet description"


class TestLintDescriptionBloat(unittest.TestCase):
    def _ws(self, skills):
        """skills: dict of name -> SKILL.md text. Returns root dir."""
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = pathlib.Path(td.name)
        for name, text in skills.items():
            d = root / name
            d.mkdir()
            (d / "SKILL.md").write_text(text)
        return root

    def _skill(self, name, description):
        return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"

    def test_short_description_passes(self):
        root = self._ws({"alpha": self._skill("alpha", SHORT_DESC)})
        self.assertEqual(ldb.lint(root), [])

    def test_long_description_flagged(self):
        root = self._ws({"alpha": self._skill("alpha", LONG_DESC)})
        errs = ldb.lint(root)
        self.assertTrue(any("alpha" in e and "101 words" in e for e in errs))

    def test_folded_list_description_counted(self):
        text = (
            "---\nname: alpha\ndescription:\n"
            + "\n".join(f"  - {w}" for w in ["word"] * 101)
            + "\n---\n\n# alpha\n"
        )
        root = self._ws({"alpha": text})
        errs = ldb.lint(root)
        self.assertTrue(any("alpha" in e and "101 words" in e for e in errs))

    def test_unparseable_frontmatter_skipped_not_crashed(self):
        text = (
            "---\nname: alpha\ndescription: >\n"
            "  This is prose that continues onto\n"
            "  a second indented line without dashes.\n"
            "---\n\n# alpha\n"
        )
        root = self._ws({"alpha": text})
        self.assertEqual(ldb.lint(root), [])

    def test_missing_description_skipped(self):
        text = "---\nname: alpha\n---\n\n# alpha\n"
        root = self._ws({"alpha": text})
        self.assertEqual(ldb.lint(root), [])

    def test_catalog_short_bullet_passes(self):
        root = self._ws({})
        (root / "CATALOG.md").write_text(
            f"## Core framework skills\n\n- **`alpha`** — {SHORT_BULLET_DESC}\n"
        )
        self.assertEqual(ldb.lint(root), [])

    def test_catalog_long_bullet_flagged(self):
        root = self._ws({})
        (root / "CATALOG.md").write_text(
            f"## Core framework skills\n\n- **`alpha`** — {LONG_BULLET_DESC}\n"
        )
        errs = ldb.lint(root)
        self.assertTrue(any("alpha" in e and "41 words" in e for e in errs))

    def test_catalog_star_prefixed_bullet_parsed(self):
        root = self._ws({})
        (root / "CATALOG.md").write_text(
            f"## PM\n\n- ★ **`write-a-prd`** — {LONG_BULLET_DESC}\n"
        )
        errs = ldb.lint(root)
        self.assertTrue(any("write-a-prd" in e and "41 words" in e for e in errs))

    def test_catalog_non_bullet_lines_ignored(self):
        root = self._ws({})
        (root / "CATALOG.md").write_text(
            "# Skill catalog\n\n**170 skills across 34 categories.**\n\n"
            "## Core framework skills\n\n"
        )
        self.assertEqual(ldb.lint(root), [])

    def test_missing_catalog_ignored(self):
        root = self._ws({"alpha": self._skill("alpha", SHORT_DESC)})
        self.assertEqual(ldb.lint(root), [])


if __name__ == "__main__":
    unittest.main()
