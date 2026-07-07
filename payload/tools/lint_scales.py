#!/usr/bin/env python3
"""Lint the task-outcome scales registry: row format, ids, levels, budget.

Sibling of ``lint_registry.py`` — same CLI shape (a single optional path arg,
defaulting to ``$HOME/.claude/learning/SCALES.md``) and the same summary line.
Stdlib only.

Row grammar (one scale per line)::

    | scale-id | levels | applies-to | description |

Rules enforced:

* **scale-id** — kebab-case (``[a-z0-9]`` words joined by single hyphens),
  unique across the file.
* **levels** — at least two tokens joined by ``>`` (best>worst); each token is
  a single lowercase word (digits and internal hyphens allowed, no spaces).
* **applies-to** / **description** — non-empty.
* **budget** — at most 40 scale rows.
* **sections** — only the two known headers may introduce rows:
  ``## Core (framework seed)`` and ``## Extended (learned on this machine)``.
* A row that is not four ``|``-delimited cells is a malformed row.

Every per-row error carries the 1-based line number of the offending row. The
two whole-file checks — a missing file and the row-budget overflow — have no
single line to point at and are reported without one. Exit 0 when clean, 1
otherwise, after printing ``lint_scales: OK|FAIL (N error(s))``.
"""
import pathlib
import re
import sys

KNOWN_SECTIONS = {
    "## Core (framework seed)",
    "## Extended (learned on this machine)",
}
BUDGET = 40

# A kebab-case token: lowercase alphanumeric words joined by single hyphens.
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# A level token has the same shape (single lowercase word, no spaces).
LEVEL_TOKEN = KEBAB
# A markdown separator row (`|---|---|`) — ignored like in lint_registry.
SEPARATOR = re.compile(r"^\|[\s\-|]+\|$")


def _split_row(line):
    """Cells of a pipe-delimited row, or None if it is not one.

    ``| a | b | c | d |`` -> ``['a', 'b', 'c', 'd']``. A line that does not
    open and close with a pipe (leading/trailing cells non-empty) is not a
    table row.
    """
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return None
    parts = s.split("|")
    if parts[0].strip() or parts[-1].strip():
        return None
    return [c.strip() for c in parts[1:-1]]


def _check_levels(field):
    """Return an error fragment for a bad levels field, or None if valid."""
    tokens = field.split(">")
    if len(tokens) < 2:
        return "levels must have >=2 tokens joined by '>': %r" % field
    for tok in tokens:
        if not LEVEL_TOKEN.match(tok):
            return "invalid level token %r in levels %r" % (tok, field)
    return None


def lint(path):
    """Return a list of error strings for the scales file at ``path``."""
    path = pathlib.Path(path)
    if not path.is_file():
        return ["missing %s" % path]

    errs = []
    ids_seen = {}          # scale-id -> first-seen line number
    row_count = 0
    current_section = None
    in_comment = False

    for i, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()

        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if not line:
            continue
        if line.startswith("<!--"):
            if "-->" not in line:
                in_comment = True
            continue
        if line.startswith("## "):
            if line not in KNOWN_SECTIONS:
                errs.append("line %d: unknown section header: %r" % (i, line))
            else:
                current_section = line
            continue
        if line.startswith("#"):
            continue                       # doc title / other heading — allowed
        if not line.startswith("|"):
            continue                       # free prose — allowed
        if SEPARATOR.match(line):
            continue                       # markdown separator row

        cells = _split_row(line)
        if cells is None:
            errs.append("line %d: malformed row: %r" % (i, raw))
            continue
        if len(cells) != 4:
            errs.append("line %d: malformed row (expected 4 cells, got %d): %r"
                        % (i, len(cells), raw))
            continue
        if cells[0] == "scale-id":
            continue                       # optional header row

        row_count += 1
        sid, levels, applies, desc = cells

        if current_section is None:
            errs.append("line %d: scale row before any known section header" % i)

        if not sid:
            errs.append("line %d: empty scale id" % i)
        elif not KEBAB.match(sid):
            errs.append("line %d: scale id not kebab-case: %r" % (i, sid))
        elif sid in ids_seen:
            errs.append("line %d: duplicate scale id %r (first at line %d)"
                        % (i, sid, ids_seen[sid]))
        else:
            ids_seen[sid] = i

        if not levels:
            errs.append("line %d: empty levels field" % i)
        else:
            problem = _check_levels(levels)
            if problem:
                errs.append("line %d: %s" % (i, problem))

        if not applies:
            errs.append("line %d: empty applies-to field" % i)
        if not desc:
            errs.append("line %d: empty description field" % i)

    if row_count > BUDGET:
        errs.append("%d scale rows; budget is %d" % (row_count, BUDGET))
    return errs


def parse_scales(path):
    """Return ``{scale-id: [levels]}`` for well-formed rows (lenient).

    Used by ``score_task.py`` to validate a ``--scale name=level`` against the
    registry. Malformed rows are silently skipped here — reporting them is the
    linter's job, not this extractor's.
    """
    path = pathlib.Path(path)
    scales = {}
    in_comment = False
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if line.startswith("<!--"):
            if "-->" not in line:
                in_comment = True
            continue
        if not line.startswith("|") or SEPARATOR.match(line):
            continue
        cells = _split_row(line)
        if not cells or len(cells) != 4:
            continue
        sid, levels = cells[0], cells[1]
        if sid == "scale-id" or not KEBAB.match(sid):
            continue
        tokens = levels.split(">")
        if len(tokens) < 2:
            continue
        scales[sid] = tokens
    return scales


def main():
    path = (pathlib.Path(sys.argv[1]) if len(sys.argv) > 1
            else pathlib.Path.home() / ".claude" / "learning" / "SCALES.md")
    errs = lint(path)
    for e in errs:
        print("LINT: %s" % e)
    print("lint_scales: %s (%d error(s))" % ("FAIL" if errs else "OK", len(errs)))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
