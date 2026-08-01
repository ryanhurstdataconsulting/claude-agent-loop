#!/usr/bin/env python3
"""audit_digest — the surfacing layer for the repo-security-audit scheduler.

Audits run across many packages nightly. Almost every finding is routine —
zero counts, or a Low/Informational note nobody needs to see at 2am. If every
run produced a notification, the human would learn to ignore notifications,
and the one Critical that matters would get ignored right along with them. So
the split is severity-based, not volume-based: Critical and High interrupt
immediately (``audit_run.sh`` already does this with its own OS notification,
built from the same rule as :func:`severity_alert` below); everything else —
Medium, Low, Informational, and every clean run — waits here, batched into a
digest the human reviews on their own schedule. A run whose verdict is
``blocked`` or ``failed`` alerts too, even at 0/0 findings: a gate abort or a
crashed audit is exactly the silent failure this layer must not swallow by
lumping it in with routine "nothing to see" runs.

Layout, under ``<root>/audit/`` (``root`` is normally
:func:`audit_store.store_root`, ``~/.claude/metrics``)::

    runs/<pkg>/<date>.json     read-only input, written by audit_run.sh
    digests/<date>.md          one rendered digest per day this ran
    digests/.last-digest       ISO instant of the last render (the "since" window)
    digests/.last-read         the date-stamp of the last digest a human has seen

Public surface:

* :func:`severity_alert` — the immediate-notification text for one run, or
  ``None`` when it can wait for the digest.
* :func:`render` — the markdown digest for everything recorded since a given
  instant.
* :func:`write_digest` — render, persist under ``digests/``, and advance the
  window for next time.
* :func:`nudge` — the one-line SessionStart surface. Self-consuming, the same
  shape as the hook's loop-close section: an unread digest is reported once
  and then goes quiet, rather than nagging every session until a human acts.

Stdlib only — no third-party imports, so this tool has no install step and no
supply-chain surface of its own.
"""
import argparse
import datetime
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_store  # noqa: E402  (path set up above)

SEVERITIES = ("critical", "high", "medium", "low")
ALERT_VERDICTS = ("blocked", "failed")


def _now_dt():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def severity_alert(run):
    """Return the immediate-notification text for ``run``, or ``None``.

    Two independent triggers, either one enough to interrupt rather than wait
    for the digest:

    1. ``findings.critical`` or ``findings.high`` is non-zero. Medium, Low,
       and Informational NEVER escalate here, no matter how many pile up —
       that is the whole point of a severity-gated alert instead of a
       count-gated one.
    2. ``verdict`` is ``blocked`` or ``failed``. Those runs may carry no
       findings at all (a crashed CLI leaves ``findings: null``), but a gate
       abort or a crash is precisely the silent failure this layer exists to
       catch — it must not read as "clean" just because nothing was counted.
    """
    package = run.get("package") or "<unknown package>"
    verdict = run.get("verdict")
    findings = run.get("findings") or {}
    critical = findings.get("critical") or 0
    high = findings.get("high") or 0

    if verdict in ALERT_VERDICTS:
        note = run.get("note") or "no further detail recorded"
        return "audit %s: %s — %s" % (verdict, package, note)

    if critical or high:
        return "audit alert: %s — %d critical, %d high" % (package, critical, high)

    return None


def _iter_runs(root):
    """Yield ``(package, record)`` for every run-log JSON under ``root``.

    Tolerates a missing runs directory, an unreadable or malformed file, and
    a JSON payload that isn't an object — each is skipped rather than
    aborting the whole digest over one corrupt entry, the same tolerance
    ``audit_dispatch.last_state`` applies to these identical files.
    ``state.json`` is a per-package scheduler marker, not a run record, and
    is always excluded.
    """
    runs_dir = pathlib.Path(root) / "audit" / "runs"
    try:
        pkg_dirs = sorted(p for p in runs_dir.iterdir() if p.is_dir())
    except OSError:
        return
    for pkg_dir in pkg_dirs:
        try:
            files = sorted(
                p for p in pkg_dir.glob("*.json")
                if p.is_file() and p.name != "state.json"
            )
        except OSError:
            continue
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                yield pkg_dir.name, data


def _sort_key(item):
    _, record = item
    return (record.get("run_at") or "", record.get("package") or "")


def render(root, since):
    """Render the markdown digest for every run recorded since ``since``.

    ``since`` is an ISO ``...Z`` instant (as written to ``.last-digest``), or
    ``None`` for "everything on record". ``run_at`` timestamps are ISO-8601
    with a ``Z`` suffix, so a plain string comparison is a correct "after"
    test — the same trick ``loop_digest.undigested`` relies on for its ledger.

    Two sections, oldest-first within each:

    * **Alerts** — every run :func:`severity_alert` would already have
      interrupted for (Critical/High findings, or a blocked/failed verdict).
      Repeated here so the digest is a complete record of the window, not
      just whatever never got surfaced.
    * **Routine** — everything else: clean runs, and Medium/Low/Informational
      findings that never needed to interrupt anyone.
    """
    records = list(_iter_runs(root))
    if since:
        records = [(pkg, r) for pkg, r in records if (r.get("run_at") or "") > since]
    records.sort(key=_sort_key)

    lines = []
    lines.append(
        "<!-- Repo-audit digest — LOCAL-ONLY. May name real client packages; "
        "never publish this file, or copy an excerpt out of the store, "
        "without re-running classify_visibility and secret_pii_scrub_gate "
        "over it first. -->"
    )
    lines.append("# Repo-audit digest")
    lines.append("")
    window = since if since else "the beginning of the run log"
    lines.append("Window: runs recorded since %s." % window)
    lines.append("Total runs in window: %d." % len(records))
    lines.append("")

    alerts = []
    routine = []
    for pkg, record in records:
        text = severity_alert(record)
        if text:
            alerts.append((pkg, record, text))
        else:
            routine.append((pkg, record))

    lines.append("## Alerts (%d)" % len(alerts))
    lines.append("")
    if not alerts:
        lines.append("None — nothing in this window needed an immediate interrupt.")
    else:
        for pkg, record, text in alerts:
            lines.append("- `%s` %s: %s" % (record.get("date") or "?", pkg, text))
    lines.append("")

    lines.append("## Routine (%d)" % len(routine))
    lines.append("")
    if not routine:
        lines.append("None.")
    else:
        for pkg, record in routine:
            findings = record.get("findings") or {}
            counts = ", ".join(
                "%s %d" % (sev, findings.get(sev) or 0) for sev in SEVERITIES
            )
            lines.append(
                "- `%s` %s — verdict %s, %s"
                % (record.get("date") or "?", pkg, record.get("verdict") or "?", counts)
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def write_digest(root):
    """Render today's digest, persist it, and advance the ``since`` window.

    Reads ``digests/.last-digest`` for the previous window edge (``None`` on
    a first run — "everything on record"), renders with :func:`render`,
    writes to ``digests/<today>.md`` (UTC date; calling this twice the same
    day overwrites with the now-current window rather than accumulating
    duplicates), and advances ``.last-digest`` to this run's instant. Returns
    the path written, as a string.
    """
    digests_dir = pathlib.Path(root) / "audit" / "digests"
    digests_dir.mkdir(parents=True, exist_ok=True)

    marker = digests_dir / ".last-digest"
    try:
        since = marker.read_text(encoding="utf-8").strip() or None
    except OSError:
        since = None

    now = _now_dt()
    text = render(root, since)

    out_path = digests_dir / (now.strftime("%Y-%m-%d") + ".md")
    out_path.write_text(text, encoding="utf-8")
    marker.write_text(_iso(now) + "\n", encoding="utf-8")

    return str(out_path)


def nudge(root):
    """The one-line SessionStart surface, or ``""`` when nothing is unread.

    Self-consuming, like the hook's loop-close section this is modelled on:
    the newest digest is reported at most once. The first call after a fresh
    digest lands returns the line AND advances ``digests/.last-read`` to that
    digest's date-stamp; every call after that, until the next digest is
    written, returns ``""``. Silence is the correct steady-state output here
    — a routine digest must not re-nag every session until a human opens it.
    """
    digests_dir = pathlib.Path(root) / "audit" / "digests"
    try:
        candidates = sorted(p for p in digests_dir.glob("*.md") if p.is_file())
    except OSError:
        candidates = []
    if not candidates:
        return ""

    latest = candidates[-1]
    stamp = latest.stem  # "YYYY-MM-DD" — sorts as chronological order too.

    last_read_path = digests_dir / ".last-read"
    try:
        last_read = last_read_path.read_text(encoding="utf-8").strip()
    except OSError:
        last_read = ""

    if last_read and last_read >= stamp:
        return ""

    last_read_path.write_text(stamp + "\n", encoding="utf-8")
    return "Audit digest ready for review (%s) — read it at %s." % (stamp, latest)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Render and surface the repo-security-audit digest.")
    parser.add_argument(
        "--root",
        default=None,
        help="store root (default: %s)" % audit_store.store_root(),
    )
    parser.add_argument(
        "--nudge",
        action="store_true",
        help="print the SessionStart nudge line if a digest is unread, and nothing else",
    )
    args = parser.parse_args(argv)
    root = args.root or audit_store.store_root()

    if args.nudge:
        line = nudge(root)
        if line:
            print(line)
        return 0

    path = write_digest(root)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
