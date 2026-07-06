#!/usr/bin/env python3
"""Standalone grammar gate for machine-generated, client-facing prose.

Scans a file (or stdin, or a literal ``--string``) for the grammar defects that
have shipped in live production output, prints ``file:line: issue`` for each,
and exits non-zero on any hit. Wire it into a project's test suite so generated
text that regresses fails a test.

Checks:
- wrong indefinite article before the next token, numbers included
  ("a 8.1" → "an 8.1", "an 32.2" → "a 32.2"). The article check fires only
  when the next token's spoken onset is *certain* (numbers and plain lowercase
  words); ALL-CAPS words, initialisms, and tool-names ("a MATCH", "an ffmpeg",
  "an API-side") are left alone rather than guessed at;
- its/it's and their/there/they're misuse (conservative heuristics);
- double spaces inside a line;
- the "<plural noun>'s" double possessive ("Warriors's" → "Warriors'").

Markdown code is exempt: fenced code blocks (```/~~~) and inline-code spans
(`...`) are blanked before any check runs, so shell comments and identifiers
are never mistaken for prose. Line numbers are preserved.

Stdlib only. Imports the shared ``prose_grammar`` helper module.
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from prose_grammar import article_onset_confident, pluralize

# Article scan: an "a"/"an" followed by whitespace and a next token.
_ARTICLE = re.compile(r"\b(an?)\b(\s+)(\S+)", re.IGNORECASE)
_STRIP = ".,;:!?\"'()[]{}"

# Markdown code masking. Prose rules must not fire inside code — a
# space-aligned shell comment is not a "double space", and a code identifier
# is not a mispronounced word. Before any check runs, fenced code blocks
# (```/~~~) and inline-code spans (`...`) are blanked, with the line count
# preserved so reported line numbers stay accurate.
_FENCE = re.compile(r"(`{3,}|~{3,})")
_INLINE_CODE_SPAN = re.compile(r"(`+)([^`]*?)\1")


def _blank_fenced_blocks(lines):
    """Blank whole fenced-code-block lines (fences + content) to ``""``.

    One output line per input line, so line numbers are unchanged. A block
    opens on a ```` ``` ````/``~~~`` fence and closes on a fence of the same
    character at least as long with nothing else on the line (CommonMark).
    """
    out = []
    fence = None  # (char, length) while inside a block; None otherwise
    for line in lines:
        stripped = line.lstrip()
        m = _FENCE.match(stripped)
        if fence is None:
            if m:
                fence = (m.group(1)[0], len(m.group(1)))
                out.append("")  # opening fence line
            else:
                out.append(line)
        else:
            out.append("")  # content or closing fence — always blanked
            if (m and m.group(1)[0] == fence[0]
                    and len(m.group(1)) >= fence[1]
                    and stripped[len(m.group(1)):].strip() == ""):
                fence = None
    return out


def _blank_inline_code(line):
    """Replace inline-code spans with a single ``_`` placeholder.

    ``_`` is non-space (introduces no double space) and non-alphanumeric (the
    article check skips it), so masking never manufactures a new finding.
    """
    return _INLINE_CODE_SPAN.sub("_", line)

# "its" followed by one of these reads as "it is/has" → likely "it's".
_IT_IS_FOLLOWERS = {
    "a", "an", "the", "been", "not", "no", "going", "gonna", "too", "so",
    "very", "just", "also", "now", "still", "already", "really", "probably",
    "actually", "clear", "important", "possible", "likely", "great",
}
_ITS = re.compile(r"\bits\s+([A-Za-z']+)", re.IGNORECASE)
_ITS_APOS_POSSESSIVE = re.compile(r"\bit's\s+(own)\b", re.IGNORECASE)

# "their" before a verb reads as "there is/are" or "they are".
_THEIR_VERB = re.compile(
    r"\btheir\s+(is|are|was|were|been|will|would|has|have|had|going|gonna)\b",
    re.IGNORECASE,
)
# "there"/"they're" before a possessed noun should be "their".
_POSSESSED_NOUN = (
    r"(own|team|teams|coach|coaches|player|players|parents|goals|scores|"
    r"families|home|house|names|roster)"
)
_THERE_NOUN = re.compile(r"\bthere\s+" + _POSSESSED_NOUN + r"\b", re.IGNORECASE)
_THEYRE_NOUN = re.compile(r"\bthey're\s+" + _POSSESSED_NOUN + r"\b", re.IGNORECASE)

# Double space *between words* inside a line — the check's stated purpose. A
# word char must follow the run, so column-alignment padding (spaces lining a
# trailing `— description` up after an inline-code span) is left alone while a
# genuine "the  cat" gap, and even a double space between sentences, still fire.
# Leading indentation is excluded by the preceding-non-space lookbehind.
_DOUBLE_SPACE = re.compile(r"(?<=\S) {2,}(?=\w)")

# Capitalized plural-looking noun taking "'s" — the double possessive. Singular
# nouns and names that legitimately end in "s" are whitelisted out.
_DOUBLE_POSSESSIVE = re.compile(r"\b([A-Z][a-z]+s)'s\b")
_SINGULAR_S = {
    "james", "chris", "charles", "boss", "bass", "class", "glass", "gas",
    "lens", "bus", "jesus", "texas", "kansas", "arkansas", "paris",
}


def _check_articles(line, filename, lineno):
    findings = []
    for m in _ARTICLE.finditer(line):
        used = m.group(1).lower()
        token = m.group(3).strip(_STRIP)
        if not token or not re.search(r"[A-Za-z0-9]", token):
            continue
        expected = article_onset_confident(token)
        if expected is None:
            # Onset not confidently known (ALL-CAPS word, initialism,
            # tool-name) — suppress rather than risk corrupting correct text.
            continue
        if expected != used:
            findings.append(
                f'{filename}:{lineno}: article: "{used}" before "{token}" '
                f'— use "{expected} {token}"'
            )
    return findings


def _check_homophones(line, filename, lineno):
    findings = []
    for m in _ITS.finditer(line):
        if m.group(1).lower() in _IT_IS_FOLLOWERS:
            findings.append(
                f'{filename}:{lineno}: "its" before "{m.group(1)}" '
                f'— did you mean "it\'s" (it is/has)?'
            )
    if _ITS_APOS_POSSESSIVE.search(line):
        findings.append(
            f'{filename}:{lineno}: "it\'s own" '
            f'— did you mean the possessive "its own"?'
        )
    if _THEIR_VERB.search(line):
        findings.append(
            f'{filename}:{lineno}: "their" before a verb '
            f'— did you mean "there" or "they\'re"?'
        )
    if _THERE_NOUN.search(line) or _THEYRE_NOUN.search(line):
        findings.append(
            f'{filename}:{lineno}: possessive expected '
            f'— did you mean "their"?'
        )
    return findings


def _check_spacing(line, filename, lineno):
    if _DOUBLE_SPACE.search(line):
        return [f"{filename}:{lineno}: double space between words"]
    return []


def _check_possessive(line, filename, lineno):
    findings = []
    for m in _DOUBLE_POSSESSIVE.finditer(line):
        base = m.group(1)
        if base.lower() in _SINGULAR_S:
            continue
        findings.append(
            f'{filename}:{lineno}: double possessive: "{m.group(0)}" '
            f'— a plural noun takes a trailing apostrophe only ("{base}\'")'
        )
    return findings


def lint_text(text: str, filename: str = "<string>") -> list:
    """Return a list of ``file:line: issue`` strings for ``text``."""
    findings = []
    lines = _blank_fenced_blocks(text.splitlines())
    for lineno, line in enumerate(lines, 1):
        line = _blank_inline_code(line)
        findings += _check_articles(line, filename, lineno)
        findings += _check_homophones(line, filename, lineno)
        findings += _check_spacing(line, filename, lineno)
        findings += _check_possessive(line, filename, lineno)
    return findings


def lint_file(path: str) -> list:
    return lint_text(pathlib.Path(path).read_text(encoding="utf-8"), path)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    findings = []
    if "--string" in argv:
        i = argv.index("--string")
        findings = lint_text(argv[i + 1], "<string>")
    elif not argv or argv == ["-"]:
        findings = lint_text(sys.stdin.read(), "<stdin>")
    else:
        for path in argv:
            findings += lint_file(path)

    for f in findings:
        print(f)
    status = "FAIL" if findings else "OK"
    print(
        f"prose_grammar_gate: {status} ({pluralize(len(findings), 'issue')})",
        file=sys.stderr,
    )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
