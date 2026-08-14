#!/usr/bin/env python3
"""classify_visibility.py — the default-deny visibility classifier (P5).

The single guard between the loop's auto-write path and the *publishable*
framework repo: given a file (or a ``--text`` string), decide whether its path
and content are safe to ship (``GENERIC``), name a client (``CLIENT``), or carry
a machine-specific risk signal that cannot be cleared automatically
(``UNSURE``). ``loop_autocommit.sh`` refuses to land anything but ``GENERIC`` in
the framework tree.

**DEFAULT-DENY is the whole design.** A caller MUST treat ``UNSURE`` exactly as
it treats ``CLIENT`` — route it to a local-only file, never to ``payload/``.
Fail CLOSED, never open: a missing *or empty* markers file (one that holds zero
live markers after comments and blanks are stripped) classifies *every* input
``UNSURE`` (with a warning), rather than waving everything through as generic.

Rules, per input, in order:

1. **CLIENT** — any marker (from ``CLIENT_MARKERS.txt``) is a case-insensitive
   substring of the path OR the content. The matched markers are reported.
2. **UNSURE** — no marker matched, but the path/content carries a structural
   risk signal: an absolute ``/Users/<name>`` (or ``/home/<name>``) path, an
   email address, a ``user@host`` ssh target, or an IPv4 address.
3. **GENERIC** — neither of the above.

Markers load from ``$HOME/.claude/learning/CLIENT_MARKERS.txt`` (override with
``--markers``); one marker per line, ``#`` comments and blank lines ignored.

Output is one machine-readable line per input::

    <verdict>\t<path>\t<markers>

where ``<markers>`` is the comma-joined matched markers for CLIENT, a
``structural:<signals>`` tag for UNSURE, ``no-markers-file`` when the markers
file is missing or empty, or ``-`` for GENERIC.

Exit codes: **0** = every input GENERIC · **3** = any input CLIENT or UNSURE
(the default-deny signal) · **2** = a usage error (no inputs). Stdlib only.
"""
import argparse
import pathlib
import re
import sys

# --- Structural risk signals -------------------------------------------------
# These fire only when NO marker matched. Each says "this text is specific to a
# machine or a person," which is enough to withhold a GENERIC verdict.
_STRUCTURAL = [
    # Absolute per-user home paths bake a username into an artifact.
    ("userpath", re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+")),
    # Email addresses.
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    # ssh-style user@host targets (host need not be a full domain). Kept after
    # email so a real address is labelled "email"; a bare user@host still fires.
    ("ssh-host", re.compile(r"\b[A-Za-z0-9._-]+@[A-Za-z0-9][A-Za-z0-9.-]+\b")),
    # IPv4 addresses.
    ("ip", re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
]

TEXT_LABEL = "<text>"

# A GitHub-Actions style pin (`uses: actions/checkout@v4`, `@<40-hex sha>`)
# puts a version reference after the "@", not a machine — treating it as an
# ssh-host marked every workflow template UNSURE and tripped the autocommit
# gate on files with no host in them.
_PIN_HOST = re.compile(r"^(?:v\d+(?:\.\d+)*|[0-9a-fA-F]{7,40})$")


def _ssh_host_present(rx, text):
    """True when an ssh-style match has a real host, not a version pin."""
    return any(
        not _PIN_HOST.match(m.group(0).rsplit("@", 1)[1])
        for m in rx.finditer(text))


def load_markers(path):
    """Return the marker list at ``path``, or ``None`` if it yields no markers.

    ``None`` is the fail-closed signal: the caller must classify every input
    ``UNSURE``. It is returned for BOTH a missing file AND a present file that
    holds zero live markers after stripping ``#`` comments and blank lines — an
    empty (or all-comment) markers file must NOT wave every input through as
    GENERIC. One marker per line; blank lines and ``#`` comment lines are dropped
    (a ``#`` line that merely mentions a marker word never counts).
    """
    p = pathlib.Path(path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    markers = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        markers.append(line)
    if not markers:
        # Present but empty after stripping: fail CLOSED, exactly like a missing
        # file. Returning [] here would classify every input GENERIC (leak-open).
        return None
    return markers


def structural_signals(text):
    """Return the list of structural-signal names present in ``text``."""
    found = []
    for name, rx in _STRUCTURAL:
        if name == "ssh-host":
            if _ssh_host_present(rx, text):
                found.append(name)
        elif rx.search(text):
            found.append(name)
    return found


def classify(content, path_label, markers):
    """Classify one input. Returns ``(verdict, detail)``.

    ``markers`` is the list from :func:`load_markers`, or ``None`` when the
    markers file is missing — in which case the verdict is always ``UNSURE``
    (fail closed), never ``GENERIC``.
    """
    if markers is None:
        return ("UNSURE", "no-markers-file")
    haystack = ("%s\n%s" % (path_label, content)).lower()
    hits = [m for m in markers if m and m.lower() in haystack]
    if hits:
        return ("CLIENT", ",".join(hits))
    signals = structural_signals("%s\n%s" % (path_label, content))
    if signals:
        return ("UNSURE", "structural:" + ",".join(signals))
    return ("GENERIC", "-")


def _read_content(path):
    """File content for classification, or ``None`` if unreadable."""
    try:
        return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Default-deny visibility classifier (GENERIC/CLIENT/UNSURE).")
    ap.add_argument("paths", nargs="*", help="file path(s) to classify")
    ap.add_argument("--text", help="classify this literal string instead of a "
                                   "file (label '<text>')")
    ap.add_argument("--markers", default=None,
                    help="markers file (default: "
                         "$HOME/.claude/learning/CLIENT_MARKERS.txt)")
    args = ap.parse_args(argv)

    if not args.paths and args.text is None:
        print("classify_visibility: no input — pass file path(s) or --text",
              file=sys.stderr)
        return 2

    markers_path = (pathlib.Path(args.markers) if args.markers
                    else pathlib.Path.home() / ".claude" / "learning"
                    / "CLIENT_MARKERS.txt")
    markers = load_markers(markers_path)
    if markers is None:
        print("classify_visibility: WARNING markers file not found at %s — "
              "classifying every input UNSURE (fail closed)" % markers_path,
              file=sys.stderr)

    inputs = []
    if args.text is not None:
        inputs.append((TEXT_LABEL, args.text))
    for path in args.paths:
        content = _read_content(path)
        if content is None and markers is not None:
            # Cannot verify the content — do not assume GENERIC. Classify the
            # path alone; a clean path with unverifiable content stays UNSURE.
            verdict, detail = classify("", path, markers)
            if verdict == "GENERIC":
                verdict, detail = "UNSURE", "unreadable"
            inputs.append((path, None, verdict, detail))
            continue
        inputs.append((path, content if content is not None else "",))

    counts = {"GENERIC": 0, "CLIENT": 0, "UNSURE": 0}
    for item in inputs:
        if len(item) == 4:                      # pre-decided unreadable case
            label, _c, verdict, detail = item
        else:
            label, content = item
            verdict, detail = classify(content, label, markers)
        counts[verdict] += 1
        print("%s\t%s\t%s" % (verdict, label, detail))

    print("classify_visibility: %d GENERIC, %d CLIENT, %d UNSURE"
          % (counts["GENERIC"], counts["CLIENT"], counts["UNSURE"]),
          file=sys.stderr)
    return 0 if (counts["CLIENT"] == 0 and counts["UNSURE"] == 0) else 3


if __name__ == "__main__":
    sys.exit(main())
