"""Tests for lint_heuristics — the HEURISTICS.md rule-grammar linter (P6).

Written TDD-first: this module imports ``lint_heuristics`` before the tool
exists (RED = ModuleNotFoundError), then drives it GREEN. It clones the shape of
``test_lint_scales.py`` (tempdir workspace, per-violation coverage with line
numbers) and additionally asserts the shipped seed ``learning/HEURISTICS.md``
passes clean and that ``parse_heuristics`` extracts the eight seed rules.
"""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import lint_heuristics as lh  # noqa: E402

SEED = pathlib.Path(__file__).resolve().parents[2] / "learning" / "HEURISTICS.md"

# The canonical field order (name, sample value), used to build test blocks.
FIELDS_IN_ORDER = [
    ("WHEN", "something happens"),
    ("WINDOW", "last 10 tasks"),
    ("THRESHOLD", "mean error_rate > 0.25"),
    ("THEN", "improve-now"),
    ("CONFIDENCE", "seed"),
    ("LAST-REVIEWED", "2026-07-06"),
]


def build_rule(hid="H1", slug="sample-rule", fields=None):
    """A `## H<id> — <slug>` block with the given ordered (name, value) fields."""
    fields = FIELDS_IN_ORDER if fields is None else fields
    lines = ["## %s — %s" % (hid, slug)]
    for name, val in fields:
        lines.append("- %s: %s" % (name, val))
    return "\n".join(lines) + "\n"


class TestLintHeuristics(unittest.TestCase):
    def _lint(self, text):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        p = pathlib.Path(td.name) / "HEURISTICS.md"
        p.write_text(text)
        return lh.lint(p)

    # --- the shipped seed -----------------------------------------------------

    def test_seed_file_passes(self):
        self.assertEqual(lh.lint(SEED), [])

    def test_parse_seed_returns_seven_active_and_one_planned(self):
        rules = lh.parse_heuristics(SEED)
        active = [r for r in rules if not r["retired"] and not r["planned"]]
        planned = [r for r in rules if r["planned"]]
        # H5 (route-cost-outlier) is parked under ## Planned — its metric is not
        # in the store yet — so it is parsed as PLANNED, not ACTIVE.
        self.assertEqual([r["id"] for r in active],
                         ["H1", "H2", "H3", "H4", "H6", "H7", "H8"])
        self.assertEqual([r["id"] for r in planned], ["H5"])
        by_id = {r["id"]: r for r in active}
        # THEN action parses to its first token even with a trailing parenthetical.
        self.assertEqual(by_id["H1"]["then"], "improve-now")
        self.assertEqual(by_id["H4"]["then"], "improve-now")   # "(files a ...)" stripped
        self.assertEqual(by_id["H8"]["then"], "no-action")     # "(recorded ...)" stripped
        self.assertEqual(by_id["H3"]["then"], "theme-note")

    # --- per-violation coverage, each with a line number ----------------------

    def test_missing_field_flagged_with_header_line(self):
        # Drop WINDOW. Header is on line 2 ("# Title" on line 1).
        fields = [f for f in FIELDS_IN_ORDER if f[0] != "WINDOW"]
        text = "# Title\n" + build_rule(fields=fields)
        errs = self._lint(text)
        self.assertTrue(any("WINDOW" in e and "line 2" in e for e in errs), errs)

    def test_out_of_order_field_flagged_with_line(self):
        # Swap WINDOW and THRESHOLD; the offending field sits at line 5.
        fields = [FIELDS_IN_ORDER[0], FIELDS_IN_ORDER[2], FIELDS_IN_ORDER[1]] \
            + FIELDS_IN_ORDER[3:]
        text = "# Title\n" + build_rule(fields=fields)
        errs = self._lint(text)
        self.assertTrue(any("out of order" in e and "line 5" in e for e in errs), errs)

    def test_bad_then_flagged(self):
        fields = [("WHEN", "x"), ("WINDOW", "last 10 tasks"),
                  ("THRESHOLD", "x"), ("THEN", "frobnicate"),
                  ("CONFIDENCE", "seed"), ("LAST-REVIEWED", "2026-07-06")]
        errs = self._lint(build_rule(fields=fields))
        self.assertTrue(any("THEN" in e and "frobnicate" in e for e in errs), errs)

    def test_duplicate_id_flagged_with_line(self):
        text = build_rule(hid="H1") + build_rule(hid="H1", slug="other")
        errs = self._lint(text)
        self.assertTrue(any("duplicate" in e.lower() and "H1" in e for e in errs),
                        errs)

    def test_bad_confidence_flagged(self):
        fields = [("WHEN", "x"), ("WINDOW", "last 10 tasks"),
                  ("THRESHOLD", "x"), ("THEN", "theme-note"),
                  ("CONFIDENCE", "bogus"), ("LAST-REVIEWED", "2026-07-06")]
        errs = self._lint(build_rule(fields=fields))
        self.assertTrue(any("CONFIDENCE" in e and "bogus" in e for e in errs), errs)

    def test_malformed_date_flagged(self):
        fields = [("WHEN", "x"), ("WINDOW", "last 10 tasks"),
                  ("THRESHOLD", "x"), ("THEN", "no-action"),
                  ("CONFIDENCE", "seed"), ("LAST-REVIEWED", "not-a-date")]
        errs = self._lint(build_rule(fields=fields))
        self.assertTrue(any("LAST-REVIEWED" in e and "ISO" in e for e in errs), errs)

    def test_retired_section_tolerated(self):
        # An active, complete rule plus a retired section whose rule is
        # deliberately incomplete (only WHEN) must lint clean.
        text = (build_rule(hid="H1")
                + "\n## Retired\n"
                + "## H2 — legacy-rule\n- WHEN: kept only for the record\n")
        self.assertEqual(self._lint(text), [])

    def test_retired_id_still_reserved(self):
        # A retired rule's id still collides with an active reuse of that id.
        text = (build_rule(hid="H1")
                + "\n## Retired\n"
                + build_rule(hid="H1", slug="old"))
        errs = self._lint(text)
        self.assertTrue(any("duplicate" in e.lower() and "H1" in e for e in errs),
                        errs)

    def test_unknown_section_header_flagged(self):
        text = "## Bogus Section\n" + build_rule(hid="H1")
        errs = self._lint(text)
        self.assertTrue(any("line 1" in e for e in errs), errs)

    def test_missing_file_flagged(self):
        errs = lh.lint(pathlib.Path("/nonexistent/HEURISTICS.md"))
        self.assertTrue(any("missing" in e for e in errs), errs)

    # --- evaluator integrity (I2a) -------------------------------------------

    def test_active_rule_without_evaluator_flagged(self):
        # A self-added ACTIVE rule id with no registered engine evaluator must
        # FAIL lint — the autocommit lint gate refuses it instead of committing
        # a rule that the engine would silently skip at eval time.
        errs = self._lint("# Title\n" + build_rule(hid="H9", slug="invented"))
        self.assertTrue(
            any("H9" in e and "evaluator" in e.lower() for e in errs), errs)

    def test_planned_rule_without_evaluator_tolerated(self):
        # A rule under ## Planned is exempt from the evaluator-integrity check.
        text = (build_rule(hid="H1")
                + "\n## Planned (not yet computable)\n"
                + build_rule(hid="H9", slug="future-rule"))
        self.assertEqual(self._lint(text), [])


if __name__ == "__main__":
    unittest.main()
