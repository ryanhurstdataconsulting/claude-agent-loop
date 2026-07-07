#!/usr/bin/env python3
"""Lint the heuristics rulebook: block grammar, field order, value domains.

Sibling of ``lint_scales.py`` / ``lint_registry.py`` — same CLI shape (one
optional path arg, defaulting to ``$HOME/.claude/learning/HEURISTICS.md``) and
the same summary line ``lint_heuristics: OK|FAIL (N error(s))``. Stdlib only.

Grammar
-------
Each ACTIVE rule is a ``## H<id> — <slug>`` block whose body carries, one per
``- FIELD: value`` line and IN THIS ORDER::

    WHEN, WINDOW, THRESHOLD, THEN, CONFIDENCE, LAST-REVIEWED

with:

* **THEN** in {improve-now, theme-note, no-action} — its first token, so a
  trailing parenthetical clarification ("improve-now (files a stub)") is fine;
* **CONFIDENCE** in {seed, low, medium, high};
* **LAST-REVIEWED** an ISO date (``YYYY-MM-DD``).

H-ids are unique across the whole file (an id stays reserved even after the rule
is retired). A ``## Retired`` section and a ``## Planned`` section may follow the
active rules; rules under either are parsed — so their ids remain reserved and
dup-checked — but are NOT required to be complete, and are EXEMPT from the
evaluator-integrity check below (a planned rule has no engine evaluator yet).

Every ACTIVE rule id must have a registered evaluator in ``heuristics_eval``
(``EVALUABLE_RULES``): a self-added rule id that the engine cannot evaluate FAILS
lint here, so the loop's autocommit gate refuses it instead of committing a rule
that would then be silently skipped at eval time.

``parse_heuristics(path)`` is the lenient extractor the evaluator reuses;
``lint(path)`` is the strict validator. Every per-rule error carries the 1-based
line number of the offending header or field line. The one whole-file check — a
missing file — has no single line to point at and is reported without one. Exit
0 when clean, 1 otherwise.
"""
import datetime
import pathlib
import re
import sys

REQUIRED_FIELDS = ["WHEN", "WINDOW", "THRESHOLD", "THEN", "CONFIDENCE",
                   "LAST-REVIEWED"]
REQUIRED_SET = set(REQUIRED_FIELDS)
THEN_VALUES = {"improve-now", "theme-note", "no-action"}
CONFIDENCE_VALUES = {"seed", "low", "medium", "high"}

# The dash class covers em dash, en dash, and hyphen so authored variants parse.
_DASH = "—–-"
RULE_HEADER = re.compile(r"^##\s+(H\w+)\s+[%s]\s+(.+?)\s*$" % _DASH)
RETIRED_HEADER = re.compile(r"^##\s+Retired\b.*$")
PLANNED_HEADER = re.compile(r"^##\s+Planned\b.*$")
FIELD_LINE = re.compile(r"^-\s+([A-Z][A-Z-]*)\s*:\s*(.*)$")
SECTION = re.compile(r"^##\s+")


def _evaluable_rules():
    """The rule ids the engine can actually evaluate, imported LAZILY from
    ``heuristics_eval`` (which imports THIS module at load time, so a top-level
    import would be circular). Returns ``None`` if the engine is unavailable, in
    which case the evaluator-integrity check degrades to a no-op rather than
    raising a false positive."""
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import heuristics_eval as he  # noqa: E402
        return set(he.EVALUABLE_RULES)
    except Exception:
        return None


def _iter_lines(text):
    """Yield (lineno, stripped_line), skipping HTML comment spans.

    Mirrors ``lint_scales`` comment handling so a ``## H<id>`` example inside the
    file's grammar comment is never mistaken for a rule.
    """
    in_comment = False
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if line.startswith("<!--"):
            if "-->" not in line:
                in_comment = True
            continue
        yield i, line


def _then_token(value):
    """The first whitespace-delimited token of a THEN value, or None if empty."""
    parts = value.split()
    return parts[0] if parts else None


def parse_heuristics(path):
    """Return a list of rule dicts (lenient — reused by ``heuristics_eval``).

    Each dict::

        {"id", "slug", "header_line", "retired" (bool), "planned" (bool),
         "fields": {NAME: value}, "field_lines": {NAME: lineno},
         "field_order": [NAME, ...], "then": <first THEN token or None>}

    Malformed blocks are included best-effort so the evaluator can skip them
    rather than crash; validation is the linter's job, not this extractor's.
    """
    path = pathlib.Path(path)
    rules = []
    in_retired = False
    in_planned = False
    current = None
    for i, line in _iter_lines(path.read_text()):
        mh = RULE_HEADER.match(line)
        if mh:
            current = {
                "id": mh.group(1), "slug": mh.group(2).strip(),
                "header_line": i, "retired": in_retired, "planned": in_planned,
                "fields": {}, "field_lines": {}, "field_order": [],
                "then": None,
            }
            rules.append(current)
            continue
        if RETIRED_HEADER.match(line):
            in_retired, in_planned = True, False   # sections are mutually exclusive
            current = None
            continue
        if PLANNED_HEADER.match(line):
            in_planned, in_retired = True, False
            current = None
            continue
        if SECTION.match(line):
            current = None            # some other `## ` heading closes the block
            continue
        mf = FIELD_LINE.match(line)
        if mf and current is not None:
            name, val = mf.group(1), mf.group(2).strip()
            current["fields"][name] = val
            current["field_lines"][name] = i
            current["field_order"].append(name)
            if name == "THEN":
                current["then"] = _then_token(val)
    return rules


def _is_iso_date(value):
    try:
        datetime.datetime.strptime(value.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def lint(path):
    """Return a list of error strings for the heuristics file at ``path``."""
    path = pathlib.Path(path)
    if not path.is_file():
        return ["missing %s" % path]
    text = path.read_text()
    errs = []

    # 1. Flag any `## ` heading that is neither a valid rule header nor a
    #    recognized section marker (Retired / Planned) — a typo'd rule header or
    #    an unknown section.
    for i, line in _iter_lines(text):
        if SECTION.match(line):
            if (RULE_HEADER.match(line) or RETIRED_HEADER.match(line)
                    or PLANNED_HEADER.match(line)):
                continue
            errs.append("line %d: unknown section header or malformed rule "
                        "header: %r" % (i, line))

    rules = parse_heuristics(path)
    ids_seen = {}
    pos = {name: k for k, name in enumerate(REQUIRED_FIELDS)}
    evaluable = _evaluable_rules()

    for r in rules:
        rid, hline = r["id"], r["header_line"]
        if rid in ids_seen:
            errs.append("line %d: duplicate rule id %s (first at line %d)"
                        % (hline, rid, ids_seen[rid]))
        else:
            ids_seen[rid] = hline
        if not r["slug"]:
            errs.append("line %d: rule %s has no slug" % (hline, rid))

        # Retired and Planned rules keep only a reserved id — do not require
        # completeness, and are EXEMPT from the evaluator-integrity check.
        if r["retired"] or r["planned"]:
            continue

        # Every ACTIVE rule must have a registered engine evaluator; a self-added
        # rule id the engine cannot evaluate is refused here (I2a).
        if evaluable is not None and rid not in evaluable:
            errs.append("line %d: rule %s is ACTIVE but has no registered "
                        "evaluator in heuristics_eval — a new rule id needs an "
                        "owner code change, or move it to ## Planned"
                        % (hline, rid))

        # Required fields present.
        for f in REQUIRED_FIELDS:
            if f not in r["fields"]:
                errs.append("line %d: rule %s is missing required field %s"
                            % (hline, rid, f))

        # Required fields in canonical order (ignoring any extra fields).
        prev = -1
        for name in r["field_order"]:
            if name not in REQUIRED_SET:
                continue
            p = pos[name]
            if p < prev:
                errs.append("line %d: field %s is out of order (expected order: "
                            "%s)" % (r["field_lines"][name], name,
                                     ", ".join(REQUIRED_FIELDS)))
            prev = p

        # Value domains.
        if "THEN" in r["fields"]:
            tok = r["then"]
            if tok not in THEN_VALUES:
                errs.append("line %d: THEN %r not in {%s}"
                            % (r["field_lines"]["THEN"], tok,
                               ", ".join(sorted(THEN_VALUES))))
        if "CONFIDENCE" in r["fields"]:
            ctok = _then_token(r["fields"]["CONFIDENCE"])
            if ctok not in CONFIDENCE_VALUES:
                errs.append("line %d: CONFIDENCE %r not in {%s}"
                            % (r["field_lines"]["CONFIDENCE"], ctok,
                               ", ".join(sorted(CONFIDENCE_VALUES))))
        if "LAST-REVIEWED" in r["fields"]:
            dv = r["fields"]["LAST-REVIEWED"]
            if not _is_iso_date(dv):
                errs.append("line %d: LAST-REVIEWED %r is not an ISO date "
                            "(YYYY-MM-DD)" % (r["field_lines"]["LAST-REVIEWED"],
                                              dv))
    return errs


def main():
    path = (pathlib.Path(sys.argv[1]) if len(sys.argv) > 1
            else pathlib.Path.home() / ".claude" / "learning" / "HEURISTICS.md")
    errs = lint(path)
    for e in errs:
        print("LINT: %s" % e)
    print("lint_heuristics: %s (%d error(s))"
          % ("FAIL" if errs else "OK", len(errs)))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
