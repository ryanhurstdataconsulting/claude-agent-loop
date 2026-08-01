#!/usr/bin/env python3
"""Secret / PII scrub gate — scan staged content (or a bundle) for leaks.

By default this scans the git staging area (``git diff --cached`` names, then
each file's *staged* blob via ``git show :<path>``) so a credential or personal
datum cannot ride into a commit. Pass an explicit file or directory to scan a
handoff bundle before it ships.

Leak classes detected:
  - JWT — three-part ``eyJ...`` tokens
  - BEARER — ``Bearer <token>`` authorization values
  - SECRET — ``password`` / ``api_key`` / ``secret`` / token assignments
  - PEM — ``BEGIN ... PRIVATE KEY`` header blocks
  - AWS-KEY — bare AWS access key IDs (``AKIA...``, ``ASIA...``)
  - DB-URI — ``postgres://user:pass@host`` connection URIs
  - EMAIL — email addresses
  - USERPATH — absolute ``/Users/<name>/`` paths (machine-specific leakage)

Output is ``file:line: <CLASS>  [REDACTED-<CLASS>]`` — the matched secret is
never echoed, in full or in part. Exits non-zero on any hit, zero when clean.

DRY note: the JWT / BEARER / SECRET / DB-URI / EMAIL regexes are reused from the
shared pattern set in ``distill_transcripts.REDACTIONS`` (single source of truth
for credential shapes on this machine). PEM-header and USERPATH detection are
added here because this gate scans line-by-line and wants a bare private-key
header (not a whole block) to fire.

Install as a git pre-commit hook (run inside the target repo):

    printf '#!/bin/sh\\nexec python3 ~/.claude/tools/secret_pii_scrub_gate.py\\n' \\
        > .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

Stdlib only (subprocess drives git).
"""
import collections
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import distill_transcripts as dt  # shared credential-regex source of truth

# --- Pattern set ------------------------------------------------------------
# Pull the reusable shapes from the distiller by label, then add the two the
# distiller does not carry (bare PEM header, /Users/ path).
_DT = dict(dt.REDACTIONS)

# Bare private-key header — the distiller's PEM regex needs a full BEGIN/END
# block, but a leaked header alone is signal enough for a line scanner.
_PEM_HEADER = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")

# Absolute per-user path — bakes a machine-specific username into an artifact.
_USER_PATH = re.compile(r"/Users/[^/\s\"'<>]+(?:/[^\s\"'<>]*)?")

# AWS access key ID — a fixed-prefix, fixed-length identifier (4-char type
# prefix + 16 upper-alphanumerics). It names an account and a principal, so it
# is a leak on its own, and it appears bare rather than as `key = value`, which
# is why the generic SECRET assignment pattern never sees it. The prefix list
# is AWS's published set (AKIA long-term, ASIA temporary session, and the
# resource-identifier prefixes that share the shape).
_AWS_KEY_ID = re.compile(
    r"\b(?:AKIA|ABIA|ACCA|AGPA|AIDA|AIPA|ANPA|ANVA|APKA|AROA|ASIA)"
    r"[A-Z0-9]{16}\b"
)

# Order matters: earlier patterns consume their span so later ones cannot
# double-count it. PEM and the postgres URI go before the generic scanners.
PATTERNS = [
    ("PEM", _PEM_HEADER),
    ("AWS-KEY", _AWS_KEY_ID),
    ("JWT", _DT["JWT"]),
    ("BEARER", _DT["TOKEN"]),
    ("DB-URI", _DT["DB-URI"]),
    ("SECRET", _DT["SECRET"]),
    ("EMAIL", _DT["EMAIL"]),
    ("USERPATH", _USER_PATH),
]

Finding = collections.namedtuple("Finding", ["file", "line", "cls"])


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def scan_text(text, filename):
    """Return a list of Finding(file, line, cls) for ``text``.

    Each line is redacted pattern-by-pattern; every substitution records one
    finding. The matched secret is discarded immediately — it is never stored
    on the Finding, so it cannot leak downstream.
    """
    findings = []
    for lineno, line in enumerate(text.splitlines(), 1):
        working = line
        for cls, rx in PATTERNS:
            def _repl(_m, _cls=cls, _ln=lineno):
                findings.append(Finding(filename, _ln, _cls))
                return f"[REDACTED-{_cls}]"
            working = rx.sub(_repl, working)
    return findings


def format_finding(f):
    """Render a Finding as ``file:line: CLASS  [REDACTED-CLASS]`` (no secret)."""
    return f"{f.file}:{f.line}: {f.cls}  [REDACTED-{f.cls}]"


def _decode(data):
    """Decode bytes to text, or return None if the blob looks binary."""
    if b"\x00" in data:
        return None
    return data.decode("utf-8", "replace")


def scan_file(path):
    p = pathlib.Path(path)
    try:
        data = p.read_bytes()
    except OSError:
        return []
    text = _decode(data)
    if text is None:
        return []
    return scan_text(text, str(path))


def scan_path(path):
    """Scan a file, or every file under a directory (skipping .git and binaries)."""
    p = pathlib.Path(path)
    if p.is_dir():
        findings = []
        for sub in sorted(p.rglob("*")):
            if sub.is_file() and ".git" not in sub.parts:
                findings += scan_file(sub)
        return findings
    return scan_file(p)


def _git(args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True)


def staged_files(cwd=None):
    """Names of files added/copied/modified/renamed in the index."""
    res = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd)
    if res.returncode != 0:
        return []
    return [p for p in res.stdout.decode("utf-8", "replace").split("\x00") if p]


def _staged_content(path, cwd=None):
    res = _git(["show", f":{path}"], cwd)
    if res.returncode != 0:
        return None
    return _decode(res.stdout)


def scan_staged(cwd=None):
    findings = []
    for name in staged_files(cwd):
        text = _staged_content(name, cwd)
        if text is not None:
            findings += scan_text(text, name)
    return findings


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        findings = []
        for arg in argv:
            findings += scan_path(arg)
        scope = "paths"
    else:
        findings = scan_staged()
        scope = "staged"

    for f in findings:
        print(format_finding(f))
    status = "FAIL" if findings else "OK"
    print(
        f"secret_pii_scrub_gate ({scope}): {status} "
        f"— {_plural(len(findings), 'finding')}",
        file=sys.stderr,
    )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
