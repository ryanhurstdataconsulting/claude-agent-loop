#!/usr/bin/env python3
"""audit_dispatch — the nightly repo-security-audit sweep: decide, then run.

The scheduling layer runs the existing repo-security-audit agent across many
packages on a rotating cadence. Something has to decide, every night, which
of those packages actually need a run — a package on a weekly cadence that
was audited yesterday should not burn agent turns again, but a package
nobody has ever gotten to, or one whose HEAD moved after the interval
elapsed, must not be silently skipped either. This module owns the whole
night: it reads the consolidated store (``audit_store``) and each package's
git HEAD to answer "is this due, and why", then drives the due list through
``audit_run.sh`` one package at a time and closes with a single
``audit_digest`` render.

The two halves stay strictly separable, which is what keeps them testable.
The policy half (:func:`is_due`, :func:`select_due`) never shells out to
anything. The execution half (:func:`run_package`, :func:`run_due`) never
invokes ``claude`` directly — it invokes ``audit_run.sh``, resolved through
the ``AUDIT_RUN_BIN`` environment variable exactly as ``audit_run.sh``
resolves the CLI through ``AUDIT_CLAUDE_BIN``. That indirection is a safety
control, not a convenience: no test may ever launch a real, billed agent
session, and an injectable runner is the only way to guarantee it.

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
* :func:`run_due` holds the same line at execution time: one package that
  crashes, hangs, or exits non-zero never aborts the rest of the sweep.
* A tier named exactly ``"excluded"`` is skipped entirely, regardless of its
  ``interval_days`` value.
* The workspace root — the directory each package name is resolved against —
  comes from ``--workspace``, else the store config's ``workspace`` key, else
  ``~/dev``. See :func:`resolve_workspace` for why the config, and not the
  launchd plist, is the right place for a machine's real answer.
* ``--dry-run`` prints exactly what would happen and invokes nothing, so the
  launchd job can be exercised end to end without spending a cent.

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
import audit_digest
import audit_store

DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
EXCLUDED_TIER = "excluded"
AUDIT_RUN_BIN_ENV = "AUDIT_RUN_BIN"
NOTIFY_ENV = "AUDIT_NOTIFY"

#: Where packages are looked for when neither ``--workspace`` nor the store
#: config says otherwise. ``~/dev`` is a convention, not this machine's real
#: answer, and that is the point: the launchd template is copied verbatim onto
#: any machine, so the real root belongs in the local-only store config, which
#: is never committed, rather than baked into a shipped file.
DEFAULT_WORKSPACE = "~/dev"


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


def _read_latest_json(run_dir, include):
    """Parse the lexicographically greatest matching JSON file in ``run_dir``.

    Never raises: a missing directory, no matching file, unreadable JSON, or
    a payload that is not an object all return ``{}`` — the same "nothing
    known yet" answer :func:`is_due` already treats as never-audited, rather
    than taking the whole night's selection down over one corrupt file.
    """
    try:
        files = sorted(p for p in run_dir.glob("*.json")
                       if p.is_file() and include(p.name))
    except OSError:
        return {}
    if not files:
        return {}
    try:
        data = json.loads(files[-1].read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def last_state(root, pkg):
    """Return the most recently recorded audit state for ``pkg``, or ``{}``.

    ``pkg`` is the package's key in ``config.json``, which is also the store
    path it is recorded under — and which may be a nested, workspace-relative
    path such as ``<client-dir>/<package>``. ``audit_run.sh`` is handed the
    same string with ``--key`` rather than re-deriving one from the package
    directory's basename, so what is written and what is read here are the
    same path by construction. They were not always: while the runner derived
    the key itself, a nested package's state was written one level shallower
    than this function looked for it, and every such package reported "never
    audited" every single night.

    Reads ``<root>/audit/runs/<pkg>/*.json``, which holds one date-stamped
    file per run (``2026-07-31.json``) plus a ``state.json`` marker written
    on success only. The greatest filename wins. That is ``state.json``
    whenever one exists — ``s`` sorts above any digit — and that is the
    intended answer, not an accident of ordering: ``state.json`` is by
    definition the last SUCCESSFUL run, and a later blocked or failed run
    must not overwrite the due-check keys with its own. When no successful
    run has ever happened, the greatest name is the newest date-stamped log,
    which carries no ``last_audit_date`` and so reads as never audited.
    """
    return _read_latest_json(pathlib.Path(root) / "audit" / "runs" / pkg,
                             lambda name: True)


def last_run_record(root, pkg):
    """Return ``pkg``'s newest dated run log, or ``{}`` — ``state.json`` excluded.

    :func:`last_state` deliberately prefers the ``state.json`` marker because
    it answers a scheduling question ("when was this last successfully
    audited"). This answers a reporting one ("what happened on the most
    recent run, whatever its verdict"), so the marker — which records only
    successes — would be the wrong file to read. The digest reader applies
    the same exclusion for the same reason.
    """
    return _read_latest_json(pathlib.Path(root) / "audit" / "runs" / pkg,
                             lambda name: name != "state.json")


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
    output rather than silently missing from it. The same holds one level
    up: ``audit_store.load_config`` does not validate tier shape or
    package-entry types, so a hand-edited ``config.json`` can hand this
    function a tier that isn't a dict, or a ``packages`` entry that isn't a
    string. Both are read inside a guarded region for exactly that reason —
    a malformed tier becomes one loud entry naming the error and the other
    tiers still run; a malformed package entry becomes one loud entry for
    itself and its sibling packages still run.
    """
    entries = []
    for tier_name, tier in (cfg.get("tiers") or {}).items():
        if tier_name == EXCLUDED_TIER:
            continue

        try:
            interval_days = tier.get("interval_days", 0)
            packages = list(tier.get("packages", []) or [])
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
            entries.append({
                "package": None,
                "tier": tier_name,
                "interval_days": None,
                "path": None,
                "head": None,
                "due": True,
                "reason": "error reading tier %r: %s: %s"
                          % (tier_name, type(exc).__name__, exc),
                "staleness_days": None,
            })
            continue

        for package in packages:
            try:
                pkg_path = os.path.join(workspace, package)
                head = head_sha(pkg_path)
                state = last_state(root, package)
                due, reason = is_due(package, interval_days, state, head, now)
                staleness = _staleness_days(state, now)
            except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
                entries.append({
                    "package": package,
                    "tier": tier_name,
                    "interval_days": interval_days,
                    "path": None,
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


def resolve_workspace(cli_value, cfg):
    """Return the workspace root packages are resolved against.

    Precedence, highest first:

    1. ``--workspace`` on the command line — an operator running the sweep by
       hand against some other tree always wins.
    2. ``cfg["workspace"]`` from ``<store>/audit/config.json``.
    3. :data:`DEFAULT_WORKSPACE`.

    The config is the intended home for the real answer. It is local-only,
    lives beside the package list it belongs with, and is never committed,
    whereas the launchd plist is a template shipped verbatim to any machine —
    a `$HOME`-relative workspace baked into that template is wrong on every
    machine but the one it was written on, and silently audits the wrong tree
    rather than failing.

    ``~`` is expanded, because the config is hand-written and ``~/dev/...`` is
    how a human writes a home-relative path. A ``workspace`` key that is
    present but is not a non-empty string raises :class:`ConfigError` rather
    than falling back: a malformed root would resolve every package to a path
    that does not exist, and the whole sweep would report "never audited"
    forever with no indication why.
    """
    if cli_value:
        return os.path.expanduser(cli_value)

    configured = (cfg or {}).get("workspace")
    if configured is not None:
        if not isinstance(configured, str) or not configured.strip():
            raise audit_store.ConfigError(
                "the 'workspace' key in audit/config.json must be a non-empty "
                "string naming the directory that holds the packages; got %r"
                % (configured,)
            )
        return os.path.expanduser(configured.strip())

    return os.path.expanduser(DEFAULT_WORKSPACE)


def audit_run_bin():
    """Resolve the ``audit_run.sh`` this sweep will invoke.

    ``AUDIT_RUN_BIN`` overrides the sibling lookup, and the override is read
    with ``os.environ.get`` and NO default so that a variable which is set
    but EMPTY resolves to the empty string and fails loudly. That is the same
    rule ``audit_run.sh`` applies to ``AUDIT_CLAUDE_BIN``, and for the same
    reason: a harness that computes an empty path must not fall through to
    the real thing and start a live, billed agent session. A prior agent did
    exactly that; the indirection exists so no test can repeat it.
    """
    override = os.environ.get(AUDIT_RUN_BIN_ENV)
    if override is not None:
        return override
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "audit_run.sh")


def _notify(text):
    """Fire one macOS notification. Never raises, never fails the sweep.

    Honours ``AUDIT_NOTIFY=0`` the same way ``audit_run.sh`` does, so a test
    suite or a headless run stays silent.
    """
    if os.environ.get(NOTIFY_ENV) == "0":
        return False
    if sys.platform != "darwin":
        return False
    message = str(text).replace('"', "")
    try:
        subprocess.run(
            ["osascript", "-e",
             'display notification "%s" with title "claude-agent-loop"' % message],
            capture_output=True,
        )
    except OSError:
        return False
    return True


def run_package(entry, root, binary=None):
    """Run one due package's audit. Returns a result dict; never raises.

    Invokes ``audit_run.sh <path> <root> --key <package> --dispatch-run-id
    <run-id>``. Passing the key explicitly is what keeps the store path this
    run WRITES identical to the one :func:`last_state` READS on the next
    night — see that function. The run id is this sweep's own OTel linkage
    only (``OTEL_RESOURCE_ATTRIBUTES``' ``parent.run``) — it plays no part in
    the store path or in ``last_state``'s lookup.

    ``AUDIT_NOTIFY=0`` is set in the child's environment on purpose. The
    runner fires its own OS notification for a Critical/High finding, which
    is right when a human invokes it by hand, but during a sweep the
    dispatcher does the notifying from the run logs, and one owner per event
    beats two notifications for it.
    """
    package = entry.get("package")
    result = {
        "package": package,
        "path": entry.get("path"),
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "error": None,
    }

    try:
        if not isinstance(package, str) or not package:
            result["error"] = "package entry is not a usable name: %r" % (package,)
            return result
        if not result["path"]:
            result["error"] = "no resolved package path for %r" % (package,)
            return result

        runner = binary if binary is not None else audit_run_bin()
        if not runner:
            result["error"] = (
                "%s is set but empty — refusing to guess the runner rather "
                "than risk starting a real agent session" % AUDIT_RUN_BIN_ENV
            )
            return result

        env = dict(os.environ)
        env[NOTIFY_ENV] = "0"
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        run_id = "night-%s-%s" % (today, package)
        proc = subprocess.run(
            ["bash", runner, result["path"], str(root), "--key", package,
             "--dispatch-run-id", run_id],
            capture_output=True,
            text=True,
            env=env,
        )
        result["returncode"] = proc.returncode
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
    return result


def run_due(root, due, binary=None):
    """Run every due package, SEQUENTIALLY, and return one result per entry.

    Sequential rather than parallel by design: each audit is a full agent
    session against a real repository, and running several at once would
    multiply peak cost, contend for the same rate limit, and make the
    per-package timeout meaningless. Nothing here aborts the batch —
    :func:`run_package` converts every failure into a result entry, so one
    package that crashes or hangs costs exactly itself and the rest of the
    night still runs.
    """
    return [run_package(entry, root, binary) for entry in due]


def collect_alerts(root, due, since):
    """Return the alert lines for runs recorded after ``since``, one per package.

    Reads what each run actually WROTE rather than trusting its exit status:
    a run log is the record the digest and the next night's due check both
    use, so an alert derived from anything else could disagree with them. A
    package whose newest run log predates this sweep produced no record at
    all tonight, which is itself alert-worthy — that is a lost run, not a
    quiet one.
    """
    alerts = []
    for entry in due:
        package = entry.get("package")
        if not isinstance(package, str) or not package:
            continue
        record = last_run_record(root, package)
        if not record or (record.get("run_at") or "") < since:
            alerts.append(
                "audit: %s — the run left no log for tonight; its outcome is "
                "unknown and its scheduler state was not recorded" % package)
            continue
        text = audit_digest.severity_alert(record)
        if text:
            alerts.append(text)
    return alerts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        default=None,
        help="store root (default: %s)" % audit_store.store_root(),
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="directory holding one subdirectory per package named in "
             "config.json (default: the 'workspace' key in audit/config.json, "
             "else %s)" % DEFAULT_WORKSPACE,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print the whole night as one JSON object instead of plain lines",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print tonight's due list and the exact command each package "
             "would get, then stop — nothing is invoked and nothing is spent",
    )
    parser.add_argument(
        "--audit-run-bin",
        default=None,
        help="path to audit_run.sh (default: the AUDIT_RUN_BIN environment "
             "variable, else the copy beside this script)",
    )
    args = parser.parse_args(argv)
    root = args.root or audit_store.store_root()

    # Reconcile the layout before anything reads or writes it. This is what
    # repairs a store created by an earlier version, whose `.gitignore` was
    # empty and therefore left every sibling of `audit/` merely untracked.
    audit_store.ensure_store(root)
    audit_store.assert_no_remote(root)
    cfg = audit_store.load_config(root)
    workspace = resolve_workspace(args.workspace, cfg)
    now = datetime.datetime.now(datetime.timezone.utc)
    since = now.strftime(DATE_FORMAT)
    due = select_due(root, cfg, workspace, now)
    runner = args.audit_run_bin if args.audit_run_bin is not None else audit_run_bin()

    if args.dry_run:
        if args.as_json:
            print(json.dumps({"dry_run": True, "due": due, "runner": runner},
                             sort_keys=True))
            return 0
        print("audit_dispatch: dry run — nothing was invoked")
        if not due:
            print("nothing due")
        for entry in due:
            print("%s — %s" % (entry["package"], entry["reason"]))
            print("  would run: bash %s %s %s --key %s"
                  % (runner, entry["path"], root, entry["package"]))
        return 0

    if not due:
        # No digest on an empty night: writing one would advance the render
        # window and fire the SessionStart nudge for a file with nothing in it.
        if args.as_json:
            print(json.dumps({"dry_run": False, "due": [], "results": [],
                              "alerts": [], "digest": None}, sort_keys=True))
        else:
            print("nothing due")
        return 0

    results = run_due(root, due, runner)
    digest_path = audit_digest.write_digest(root)
    alerts = collect_alerts(root, due, since)
    for line in alerts:
        _notify(line)

    if args.as_json:
        print(json.dumps({"dry_run": False, "due": due, "results": results,
                          "alerts": alerts, "digest": digest_path},
                         sort_keys=True))
        return 0

    for entry in due:
        print("%s — %s" % (entry["package"], entry["reason"]))
    for result in results:
        outcome = result["error"] or ("exit %s" % result["returncode"])
        print("ran %s — %s" % (result["package"], outcome))
    for line in alerts:
        print(line)
    print("digest: %s" % digest_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
