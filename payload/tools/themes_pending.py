#!/usr/bin/env python3
"""Count unprocessed (NEW) rows in the loop-themes log — fast, stdlib-only.

The SessionStart hook calls this on every session start, so it must be
trivially fast and must never fail: a missing or unreadable file counts as
zero, and there is no work beyond one sequential read.

A theme row is one line of the ``LOOP_THEMES.md`` table::

    | status | date | project | theme-tag | note | metrics-ref |

Only rows whose status is ``NEW`` are unprocessed. ``PROMOTED:<slug>`` and
``DISMISSED:<reason>`` rows have already been acted on; the title, the header
row, the separator, comments, and any malformed line are all ignored. The whole
test is "the stripped line starts with ``| NEW |``" — cheap and exact.

Usage::

    themes_pending.py [--file PATH]           # print the integer count
    themes_pending.py --list [--file PATH]    # print the NEW rows verbatim

Default file: ``$HOME/.claude/learning/LOOP_THEMES.md``. Exit code is always 0.
"""
import argparse
import pathlib
import sys

# Invariant: LOOP_THEMES.md is a FLAT pipe-table — one theme per single line, no
# fenced code blocks and no multi-line prose rows — so a line-prefix test is
# sufficient here and no markdown parser is ever needed.
#
# The canonical NEW-status cell as writers emit it: pipe, space, NEW, space,
# pipe. "| NEWISH |" and "|NEW|" (no spaces) deliberately do not match — a row
# that is not in the writer format is treated as malformed and skipped.
NEW_PREFIX = "| NEW |"


def new_rows(path):
    """Return the NEW theme rows at ``path`` verbatim (newline-stripped).

    A missing or unreadable file yields an empty list — the hook reads that as
    "nothing pending," never as an error.
    """
    path = pathlib.Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [raw for raw in text.splitlines()
            if raw.strip().startswith(NEW_PREFIX)]


def default_file():
    """The live themes log under the user's ``~/.claude``."""
    return pathlib.Path.home() / ".claude" / "learning" / "LOOP_THEMES.md"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Count unprocessed NEW rows in LOOP_THEMES.md.")
    ap.add_argument("--file", default=None,
                    help="themes file (default: "
                         "$HOME/.claude/learning/LOOP_THEMES.md)")
    ap.add_argument("--list", dest="list_rows", action="store_true",
                    help="print the NEW rows verbatim instead of the count")
    args = ap.parse_args(argv)

    path = pathlib.Path(args.file) if args.file else default_file()
    rows = new_rows(path)
    if args.list_rows:
        for row in rows:
            print(row)
    else:
        print(len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
