"""Tests for the machine-prose grammar gate (Resource Loop Phase 5).

Covers the number-aware indefinite-article helper, the pluralize helper, and
the standalone linter. Written before the implementation, per TDD.
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import prose_grammar as pg
import prose_grammar_gate as gate

GATE_PATH = pathlib.Path(__file__).resolve().parents[1] / "prose_grammar_gate.py"

# (label, input, expected) — the acceptance bar from Ryan's standing grammar
# rule, exercised across int, float, and str number inputs.
ARTICLE_CASES = [
    ("8.1 as str", "8.1", "an"),
    ("8.1 as float", 8.1, "an"),
    ("32.2 as str", "32.2", "a"),
    ("32.2 as float", 32.2, "a"),
    ("11 as str", "11", "an"),
    ("11 as int", 11, "an"),
    ("18 as str", "18", "an"),
    ("18 as int", 18, "an"),
    ("80 as str", "80", "an"),
    ("80 as int", 80, "an"),
    ("5.0 as str", "5.0", "a"),
    ("5.0 as float", 5.0, "a"),
    ("8 as str", "8", "an"),
    ("8 as int", 8, "an"),
    ("1 as str", "1", "a"),
    ("1 as int", 1, "a"),
    ("100 as str", "100", "a"),
    ("100 as int", 100, "a"),
    ("11th ordinal", "11th", "an"),
    ("one (word)", "one", "a"),
    ("hour (silent h)", "hour", "an"),
    ("university (yu sound)", "university", "a"),
    ("FBI (initialism)", "FBI", "an"),
]


class TestIndefiniteArticle(unittest.TestCase):
    def test_acceptance_cases(self):
        for label, value, expected in ARTICLE_CASES:
            with self.subTest(case=label):
                self.assertEqual(pg.indefinite_article(value), expected)

    def test_number_types_agree(self):
        # int, float, and str spellings of the same number agree.
        self.assertEqual(pg.indefinite_article(8), "an")
        self.assertEqual(pg.indefinite_article(8.0), "an")
        self.assertEqual(pg.indefinite_article("8"), "an")
        self.assertEqual(pg.indefinite_article(5), "a")
        self.assertEqual(pg.indefinite_article(5.0), "a")
        self.assertEqual(pg.indefinite_article("5"), "a")


class TestPluralize(unittest.TestCase):
    def test_counts_and_irregular(self):
        cases = [
            (1, "officer", None, "1 officer"),
            (2, "officer", None, "2 officers"),
            (0, "goal", None, "0 goals"),
            (2, "person", "people", "2 people"),
            (1, "person", "people", "1 person"),
        ]
        for count, singular, plural, expected in cases:
            with self.subTest(count=count, singular=singular):
                self.assertEqual(pg.pluralize(count, singular, plural), expected)


CLEAN_TEXT = (
    "The team scored an 8.1 and a 32.2 in the match.\n"
    "Its rating held; there were 2 officers on duty.\n"
    "The Warriors' win sealed an 11th title.\n"
)

DIRTY_TEXT = (
    "The play earned a 8.1 rating with an 32.2 lead.\n"
    "The Warriors's win was its a good result.\n"
    "Too  many spaces here.\n"
)


class TestLinter(unittest.TestCase):
    def test_clean_text_has_no_findings(self):
        self.assertEqual(gate.lint_text(CLEAN_TEXT, "clean.txt"), [])

    def test_dirty_text_flags_every_issue(self):
        findings = gate.lint_text(DIRTY_TEXT, "dirty.txt")
        joined = "\n".join(findings)
        expectations = {
            'article "a" before "8.1"': "8.1" in joined,
            'article "an" before "32.2"': "32.2" in joined,
            'double possessive "Warriors\'s"': "Warriors" in joined,
            "its/it's misuse": any('"its"' in f for f in findings),
            "double space": any("double space" in f for f in findings),
        }
        for label, hit in expectations.items():
            with self.subTest(issue=label):
                self.assertTrue(hit, f"expected the linter to flag: {label}")

    def test_findings_are_file_line_formatted(self):
        findings = gate.lint_text(DIRTY_TEXT, "dirty.txt")
        self.assertTrue(findings)
        for f in findings:
            self.assertTrue(f.startswith("dirty.txt:"), f)

    def test_cli_clean_string_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, str(GATE_PATH), "--string", "The lead was an 8.1 tonight."],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_cli_dirty_string_exits_nonzero(self):
        proc = subprocess.run(
            [sys.executable, str(GATE_PATH), "--string", "The lead was a 8.1 tonight."],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("<string>:1:", proc.stdout)

    def test_cli_reads_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write(DIRTY_TEXT)
            path = fh.name
        self.addCleanup(lambda: pathlib.Path(path).unlink())
        proc = subprocess.run(
            [sys.executable, str(GATE_PATH), path],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(f"{path}:1:", proc.stdout)


# A Markdown block whose fenced code carries defects the linter must NOT flag:
# a space-aligned shell comment (double space), a would-be number article
# ("a 8.1"), and an inline double space — all legal inside code.
FENCED_MD = (
    "Intro prose line is clean.\n"
    "```bash\n"
    "pdftoppm -png OUT/slide   # a 8.1 double  space in code\n"
    "someIdentifier = compute()\n"
    "```\n"
    "Trailing prose line is clean.\n"
)


class TestCodeMasking(unittest.TestCase):
    def test_fenced_code_defects_not_flagged(self):
        # Double space, a number article, and an identifier all sit inside a
        # ```bash block — the linter must report nothing for the whole doc.
        self.assertEqual(gate.lint_text(FENCED_MD, "doc.md"), [])

    def test_tilde_fence_also_masked(self):
        text = "Clean line.\n~~~\nbad  spacing and a 8.1 here\n~~~\nClean.\n"
        self.assertEqual(gate.lint_text(text, "doc.md"), [])

    def test_inline_code_double_space_not_flagged(self):
        # Double space *inside* backticks is code, not prose.
        self.assertEqual(gate.lint_text("See the `a  b` token.\n", "doc.md"), [])

    def test_prose_double_space_outside_code_still_flagged(self):
        # The same defect in prose (outside any code) must still fail the gate.
        findings = gate.lint_text("This has a  real gap.\n", "doc.md")
        self.assertTrue(any("double space" in f for f in findings), findings)

    def test_prose_defect_after_code_block_still_flagged(self):
        # Masking a fenced block must not swallow a defect on a later prose line.
        text = FENCED_MD + "The Warriors's win was clean.\n"
        findings = gate.lint_text(text, "doc.md")
        self.assertTrue(any("Warriors" in f for f in findings), findings)
        # ...and the flag points at the prose line, not a code line.
        self.assertTrue(all(":3:" not in f for f in findings), findings)


# Column-alignment padding — a run of spaces lining up a trailing description
# after an inline-code span — is Markdown formatting, not a prose double space,
# and must not be flagged. Regression for the CATALOG BROWSING list in
# ~/.claude/CLAUDE.md, where `/cmd` entries are space-padded to a shared em-dash.
ALIGNED_LIST = (
    "- `/catalog:list`                — show all subagents\n"
    "- `/catalog:search <term>`       — keyword search\n"
)


class TestAlignmentPadding(unittest.TestCase):
    def test_code_span_then_aligned_emdash_not_flagged(self):
        # After inline-code masking these become `_   …   —`; the run is
        # followed by an em-dash (non-word), so it is alignment, not prose.
        self.assertEqual(gate.lint_text(ALIGNED_LIST, "doc.md"), [])

    def test_padding_before_emdash_not_flagged(self):
        # A space run followed by punctuation is not "between words".
        self.assertEqual(gate.lint_text("The list item  — a note.\n", "doc.md"), [])

    def test_double_space_after_period_still_flagged(self):
        # Ryan's "no double spaces" rule still holds between sentences.
        findings = gate.lint_text("Done.  Next sentence.\n", "doc.md")
        self.assertTrue(any("double space" in f for f in findings), findings)

    def test_double_space_between_words_still_flagged(self):
        findings = gate.lint_text("A real  gap here.\n", "doc.md")
        self.assertTrue(any("double space" in f for f in findings), findings)


class TestConfidentArticle(unittest.TestCase):
    def test_all_caps_word_not_flagged(self):
        # MATCH/ROUTE are words in caps, not initialisms — do not "correct".
        for s in ("We played a MATCH today.", "Take a ROUTE north."):
            self.assertEqual(gate.lint_text(s, "doc.md"), [], s)

    def test_toolname_and_hyphenated_caps_not_flagged(self):
        for s in ("Run an ffmpeg pipeline.", "It was an API-side bug."):
            self.assertEqual(gate.lint_text(s, "doc.md"), [], s)

    def test_number_article_mismatch_still_flagged(self):
        findings = gate.lint_text("They ran with an 32.2 lead.\n", "doc.md")
        self.assertTrue(any("32.2" in f for f in findings), findings)

    def test_possessive_still_flagged(self):
        findings = gate.lint_text("The Warriors's win sealed it.\n", "doc.md")
        self.assertTrue(any("Warriors" in f for f in findings), findings)

    def test_lowercase_word_article_still_flagged(self):
        # Confident lowercase onsets keep their true-positive behavior.
        self.assertTrue(gate.lint_text("It took a hour.\n", "doc.md"))
        self.assertTrue(gate.lint_text("She is an university dean.\n", "doc.md"))

    def test_helper_confidence_boundaries(self):
        self.assertEqual(pg.article_onset_confident("32.2"), "a")
        self.assertEqual(pg.article_onset_confident("8.1"), "an")
        self.assertEqual(pg.article_onset_confident("hour"), "an")
        self.assertEqual(pg.article_onset_confident("university"), "a")
        self.assertIsNone(pg.article_onset_confident("MATCH"))
        self.assertIsNone(pg.article_onset_confident("ffmpeg"))
        self.assertIsNone(pg.article_onset_confident("API-side"))


if __name__ == "__main__":
    unittest.main()
