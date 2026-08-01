#!/usr/bin/env python3
"""audit_dispatch — pure policy: decide which packages are due for a
repo-security audit tonight.

The scheduling layer runs the existing repo-security-audit agent across many
packages on a rotating cadence. Something has to decide, every night, which
of those packages actually need a run — a package on a weekly cadence that
was audited yesterday should not burn agent turns again, but a package
nobody has ever gotten to, or one whose HEAD moved after the interval
elapsed, must not be silently skipped either. This module is that decision
in isolation: it reads the consolidated store (Task 1's ``audit_store``) and
each package's git HEAD, and answers "is this due, and why" — nothing more.

It deliberately stops there. It does not invoke ``claude``, does not create
worktrees, and does not run any audit itself; that is
:mod:`audit_run` (a later task). Keeping the decision pure and the execution
separate means the policy can be unit-tested without ever shelling out to a
real agent session, and a bug in one never masks a bug in the other.

Contracts worth stating explicitly, because callers rely on them:

* :func:`head_sha` never raises. A path that is not a git repository, does
  not exist, or a ``git`` invocation that fails all resolve to ``None`` —
  "unknown", not an error.
* :func:`is_due` treats an unknown head as due, not skippable: a package we
  cannot verify must be surfaced, never silently dropped from the rotation
  just because it looks recently audited on paper.
* :func:`select_due` never lets one broken package abort the rest of the
  night's selection — a per-package failure becomes a loud due-entry naming
  the error, sorted to the front, rather than a crash or a silent drop.
* A tier named exactly ``"excluded"`` is skipped entirely, regardless of its
  ``interval_days`` value.

Stdlib only — no third-party imports, so this tool has no install step and
no supply-chain surface of its own.
"""
import argparse
import datetime
import json
import math
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_store

DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
EXCLUDED_TIER = "excluded"


def head_sha(pkg_path):
    """Return the git HEAD SHA at ``pkg_path``, or ``None`` — never raises.

    ``None`` means "unknown": ``pkg_path`` does not exist, is not a git
    repository, or ``git`` failed for any other reason. This is not an
    error condition for callers — a package listed in config but absent
    from disk (not yet cloned into the workspace, a typo, mid-decommission)
    must still be reasoned about, not crash the scheduler.
    """
    if not pkg_path or not os.path.isdir(pkg_path):
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(pkg_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def last_state(root, pkg):
    """Return the most recently recorded audit state for ``pkg``, or ``{}``.

    Never raises. Reads ``<root>/audit/runs/<pkg>/*.json`` — one file per
    run, written by ``audit_run.sh`` with a date-stamped filename (e.g.
    ``2026-07-31.json``) — and returns the parsed contents of the
    lexicographically greatest filename, which is also the chronologically
    latest run since date-stamped names sort as dates. A missing directory,
    no runs yet, unreadable JSON, or a non-object payload all fall back to
    ``{}`` — the same "nothing known yet" state :func:`is_due` already
    treats as never-audited, rather than raising and taking the whole
    night's selection down over one corrupt file.
    """
    run_dir = pathlib.Path(root) / "audit" / "runs" / pkg
    try:
        files = sorted(p for p in run_dir.glob("*.json") if p.is_file())
    except OSError:
        return {}
    if not files:
        return {}
    try:
        data = json.loads(files[-1].read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _parse_last_audit_date(date_str, now):
    """Parse a ``last_audit_date`` string, or return ``None`` if it can't be.

    An empty/missing value and an unparseable value are both treated the
    same way by the caller (never audited), so this function collapses
    both to ``None`` rather than distinguishing them.
    """
    if not date_str:
        return None
    try:
        dt = datetime.datetime.strptime(date_str, DATE_FORMAT)
    except (TypeError, ValueError):
        return None
    if now is not None and now.tzinfo is not None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _staleness_days(state, now):
    """Days since the recorded last audit, or ``None`` if that is unknown."""
    dt = _parse_last_audit_date((state or {}).get("last_audit_date"), now)
    if dt is None:
        return None
    return (now - dt).days


def is_due(pkg, tier_days, state, head, now):
    """Decide whether ``pkg`` is due for an audit. Return ``(bool, reason)``.

    Order of checks, each returning as soon as it applies:

    1. No usable ``last_audit_date`` on record (state is empty, or its date
       is missing/unparseable) -> due, "never audited".
    2. ``head`` is ``None`` (unknown) -> due, regardless of how recently the
       package was last audited — we cannot verify anything about its
       current state, so silence would hide that fact.
    3. The interval has not elapsed -> not due.
    4. The interval has elapsed but HEAD matches the recorded
       ``last_audited_sha`` -> not due (nothing changed to re-audit).
    5. Otherwise -> due: interval elapsed and HEAD moved.
    """
    dt = _parse_last_audit_date((state or {}).get("last_audit_date"), now)
    if dt is None:
        return True, "never audited"

    if head is None:
        return True, "head unknown — auditing rather than skipping"

    days_since = (now - dt).days
    if days_since < tier_days:
        return False, "interval not elapsed (%d of %d days)" % (days_since, tier_days)

    if head == (state or {}).get("last_audited_sha"):
        return False, "head unchanged since last audit"

    return True, "due: %d days since last audit, head moved" % days_since


def select_due(root, cfg, workspace, now):
    """Return the list of due packages for tonight, capped by ``per_night_cap``.

    Walks every tier in ``cfg["tiers"]`` except one literally named
    ``"excluded"`` (skipped in full, regardless of its ``interval_days``),
    resolves each package to ``<workspace>/<package>``, and asks
    :func:`is_due`. Entries are sorted longest-overdue first — unknown
    staleness (never audited, or a package that errored while being
    evaluated) sorts as maximally overdue, since those are exactly the
    cases that most need a human or the next run to see them — then
    truncated to ``cfg["per_night_cap"]``.

    A single package raising during evaluation never aborts the rest of
    the selection: the failure is caught per-package and turned into a due
    entry whose reason names the error, so a broken package is loud in the
    output rather than silently missing from it.
    """
    entries = []
    for tier_name, tier in (cfg.get("tiers") or {}).items():
        if tier_name == EXCLUDED_TIER:
            continue
        interval_days = tier.get("interval_days", 0)
        for package in tier.get("packages", []) or []:
            pkg_path = os.path.join(workspace, package)
            try:
                head = head_sha(pkg_path)
                state = last_state(root, package)
                due, reason = is_due(package, interval_days, state, head, now)
                staleness = _staleness_days(state, now)
            except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
                entries.append({
                    "package": package,
                    "tier": tier_name,
                    "interval_days": interval_days,
                    "path": pkg_path,
                    "head": None,
                    "due": True,
                    "reason": "error evaluating package %r: %s: %s"
                              % (package, type(exc).__name__, exc),
                    "staleness_days": None,
                })
                continue

            if not due:
                continue
            entries.append({
                "package": package,
                "tier": tier_name,
                "interval_days": interval_days,
                "path": pkg_path,
                "head": head,
                "due": True,
                "reason": reason,
                "staleness_days": staleness,
            })

    def sort_key(entry):
        staleness = entry["staleness_days"]
        return -(staleness if staleness is not None else math.inf)

    entries.sort(key=sort_key)

    cap = cfg.get("per_night_cap")
    if cap is not None:
        entries = entries[:cap]
    return entries


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        default=None,
        help="store root (default: %s)" % audit_store.store_root(),
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="directory holding one subdirectory per package named in config.json",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print the full due-list as JSON instead of one line per package",
    )
    args = parser.parse_args(argv)
    root = args.root or audit_store.store_root()

    audit_store.assert_no_remote(root)
    cfg = audit_store.load_config(root)
    now = datetime.datetime.now(datetime.timezone.utc)
    due = select_due(root, cfg, args.workspace, now)

    if args.as_json:
        print(json.dumps(due, sort_keys=True))
    elif not due:
        print("nothing due")
    else:
        for entry in due:
            print("%s — %s" % (entry["package"], entry["reason"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
