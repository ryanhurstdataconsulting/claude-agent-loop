#!/usr/bin/env python3
"""audit_store — the consolidated output store for the repo-security-audit scheduler.

A scheduling layer that runs the repo-security-audit agent across many
packages on a rotating cadence needs one durable, local place to land runs,
findings, and digests — otherwise each invocation's output lives only in that
session's transcript and the scheduler has nothing to diff against or reason
about run history with. This module owns that store: a small directory tree
under a git repo with its own history, so every run is versioned and
recoverable, but with no remote — the store holds per-client package names
and audit findings that must never leave this machine, so "no remote, ever"
is a hard invariant this module enforces, not just documents.

Layout created by :func:`ensure_store`::

    <root>/
      .git/                  (no remote — see assert_no_remote)
      .gitignore              (scoped: audit/ is tracked, the rest is not)
      audit/
        config.json           (tier schedule + workspace root; hand-written,
                               not by this tool)
        runs/
        findings/
        digests/
        quarantine/           (findings documents held back from a client repo)
        logs/                 (the nightly job's stdout/stderr; never tracked)

The ``.gitignore`` is deliberately narrow rather than empty. ``root`` is the
whole metrics tree — the resource loop's monthly JSONL shards, budget
checkpoints, and caches are siblings of ``audit/`` — so an empty ignore file
would leave every one of them untracked-but-not-ignored, and a single
``git add -A`` run in that directory by a human or an agent would sweep the
lot into a commit. Only ``audit/`` is tracked here; :func:`commit_paths` is
the only writer, and it stages explicit paths, never ``-A``.

Stdlib only — no third-party imports, so this tool has no install step and no
supply-chain surface of its own.
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys

SCHEMA = 1

SUBDIRS = ("audit/runs", "audit/findings", "audit/digests",
           "audit/quarantine", "audit/logs")

# Committed by an unattended job, so the identity is fixed rather than
# inherited: a machine with no `user.email` configured would otherwise fail
# every store commit, and a machine that has one would stamp the owner's
# personal identity onto an automated write.
COMMIT_NAME = "claude-agent-loop"
COMMIT_EMAIL = "claude-agent-loop@localhost"

# Only `audit/` is tracked. See the module docstring for why an empty ignore
# file was the wrong default: `root` is the whole metrics tree, and everything
# else under it is transient working data that must never be committable by
# accident. `audit/logs/` is excluded again underneath — the nightly job's raw
# stdout is a rotating byproduct, not an artifact worth versioning.
GITIGNORE = """\
# Managed by audit_store.ensure_store — do not hand-edit.
# The audit store is the only tracked family under this root. Everything else
# here (the resource loop's monthly JSONL shards, budget checkpoints, caches)
# is transient working data, kept ignored so a stray `git add -A` in this
# directory can never sweep the whole metrics tree into a commit.
/*
!/.gitignore
!/audit/
/audit/logs/
"""


class StoreUnsafe(Exception):
    """Raised when the store violates a safety invariant (e.g. has a remote)."""


class ConfigError(Exception):
    """Raised when ``audit/config.json`` is missing, malformed, or invalid."""


def store_root():
    """Return the real default store path, ``~/.claude/metrics``, as a string.

    Every other function in this module takes an explicit ``root`` argument
    instead of calling this itself, so tests can point at a tempdir and the
    real ``~/.claude`` tree is never touched except by a deliberate caller.
    """
    return str(pathlib.Path.home() / ".claude" / "metrics")


def ensure_store(root):
    """Create the store layout under ``root`` and git-init it if needed.

    Idempotent: safe to call on every scheduler invocation. Creates
    ``audit/{runs,findings,digests,quarantine,logs}``, writes the scoped
    ``.gitignore`` above, and runs ``git init -q`` only when ``root/.git``
    does not already exist. Returns a status dict describing what was done.

    The ``.gitignore`` is rewritten whenever its content differs from
    :data:`GITIGNORE`, not merely when the file is absent. Earlier versions of
    this function wrote an EMPTY ignore file, which left every sibling of
    ``audit/`` untracked-but-not-ignored; a store created by one of those
    still has that file on disk, and only an unconditional reconcile repairs
    it. The file carries a "managed, do not hand-edit" header for that reason.
    """
    root = pathlib.Path(root)
    for sub in SUBDIRS:
        os.makedirs(root / sub, exist_ok=True)

    gitignore = root / ".gitignore"
    try:
        current = gitignore.read_text()
    except OSError:
        current = None
    if current != GITIGNORE:
        gitignore.write_text(GITIGNORE)

    git_dir = root / ".git"
    initialised = False
    if not git_dir.exists():
        try:
            result = subprocess.run(
                ["git", "init", "-q", str(root)],
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise StoreUnsafe(f"git is unavailable — cannot initialise store at {root}: {exc}")
        if result.returncode != 0:
            raise StoreUnsafe(
                f"git init failed for store at {root}: {result.stderr.strip()}"
            )
        initialised = True

    # Commit the ignore file itself, so the repo carries its own scope rather
    # than leaving the one file that defines it sitting untracked forever, and
    # the tier schedule alongside it — `config.json` is hand-written and is
    # exactly the kind of file whose edit history is worth having. Both are
    # skipped when unchanged or absent, so this stays idempotent.
    commit_paths(root, [".gitignore", "audit/config.json"],
                 "audit(store): record the store's scope and tier schedule")

    return {
        "root": str(root),
        "created": True,
        "git_initialised": initialised,
    }


def commit_paths(root, paths, message):
    """Stage ``paths`` inside the store and commit them. Return the SHA or ``None``.

    This is what makes the store's git history real rather than decorative:
    ``ensure_store`` initialises the repo, and every tool that writes an
    artifact — ``audit_run.sh`` for a run log or a quarantined findings
    document, :func:`audit_digest.write_digest` for a digest — calls this
    immediately afterwards, so each night's output has a recoverable, versioned
    home instead of sitting untracked forever.

    Three properties, each deliberate:

    * **Explicit paths, never** ``git add -A``. Only what the caller just wrote
      is staged, so an unrelated file sitting in the tree can never ride along.
      A path outside ``root``, or one that does not exist, is dropped rather
      than staged.
    * **Never pushes.** The store has no remote and must never gain one — see
      :func:`assert_no_remote`. There is no push code path here to disable.
    * **Never fatal.** Any failure — no repo, nothing staged, a git error —
      returns ``None``. The artifact is already on disk; a missed commit is a
      far smaller problem than a nightly sweep that aborts over one.

    ``--no-verify`` and ``commit.gpgsign=false`` are set because this runs
    unattended: a hook or a GPG passphrase prompt would hang the job.
    """
    root = pathlib.Path(root)
    if not (root / ".git").exists():
        return None

    rel = []
    for raw in paths or ():
        candidate = pathlib.Path(raw)
        if candidate.is_absolute():
            try:
                candidate = candidate.relative_to(root)
            except ValueError:
                continue  # outside the store — never stage it
        if not (root / candidate).exists():
            continue
        rel.append(str(candidate))
    if not rel:
        return None

    base = ["git", "-C", str(root)]
    try:
        added = subprocess.run(base + ["add", "--"] + rel,
                               capture_output=True, text=True)
        if added.returncode != 0:
            return None
        pending = subprocess.run(base + ["diff", "--cached", "--quiet"],
                                 capture_output=True, text=True)
        if pending.returncode == 0:
            return None  # nothing staged differs from HEAD
        committed = subprocess.run(
            base + [
                "-c", "user.name=" + COMMIT_NAME,
                "-c", "user.email=" + COMMIT_EMAIL,
                "-c", "commit.gpgsign=false",
                "commit", "-q", "--no-verify", "-m", message,
            ],
            capture_output=True, text=True,
        )
        if committed.returncode != 0:
            return None
        head = subprocess.run(base + ["rev-parse", "HEAD"],
                              capture_output=True, text=True)
    except OSError:
        return None

    return head.stdout.strip() or None


def assert_no_remote(root):
    """Raise :class:`StoreUnsafe` if the store at ``root`` violates local-only isolation.

    The store holds client package names and audit findings that must never
    be pushed anywhere and must never be swallowed into an enclosing repo's
    history — this is the enforcement point for both halves of that
    invariant, meant to be called before anything writes to or reads from
    the store. Checks, in order: (1) the store's own repo has no configured
    remote; (2) no enclosing repository tracks the store path (which would
    let it be committed as a nested gitlink/submodule).
    """
    root = pathlib.Path(root)
    _assert_no_git_remote(root)
    _assert_not_nested_in_tracked_parent(root)


def _assert_no_git_remote(root):
    """Raise :class:`StoreUnsafe` if ``git remote`` reports a remote — or fails.

    Fails CLOSED: if ``git remote`` cannot be run to completion (non-zero
    exit — e.g. a corrupted or unreadable ``.git/config``), that is treated
    as a violation, not a pass. An unreadable answer is not evidence the
    invariant holds; only a confirmed-empty remote list is.
    """
    try:
        result = subprocess.run(
            ["git", "remote"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise StoreUnsafe(f"git is unavailable — cannot verify store at {root}: {exc}")

    if result.returncode != 0:
        raise StoreUnsafe(
            f"could not verify store at {root} has no remote — `git remote` "
            f"exited {result.returncode}: {result.stderr.strip()} — inability "
            "to verify the no-remote invariant is not evidence it holds"
        )

    remotes = result.stdout.strip()
    if remotes:
        named = ", ".join(remotes.splitlines())
        raise StoreUnsafe(
            f"store repo has a remote ({named}) — this store is local-only by design"
        )


def _assert_not_nested_in_tracked_parent(root):
    """Raise :class:`StoreUnsafe` if the store's parent directory is a git repo

    that does not gitignore the store path.

    The store must stand alone — never get pulled into a parent project as a
    nested gitlink/submodule. The parent repo is expected to gitignore the
    store path so no gitlink can ever form; this asks git, from the store's
    immediate parent directory, whether that expectation actually holds. A
    parent that is not itself a git repository, or a git binary that is
    unavailable, cannot violate this invariant — those cases pass rather
    than crash or block on an unrelated environment gap. Likewise, only a
    confirmed "not ignored" (``git check-ignore`` exit code 1) is treated as
    a violation; any other ambiguous git-check-ignore outcome passes.
    """
    root = pathlib.Path(root).resolve()
    parent = root.parent

    try:
        in_repo = subprocess.run(
            ["git", "-C", str(parent), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return  # git unavailable — nothing to verify
    if in_repo.returncode != 0 or in_repo.stdout.strip() != "true":
        return  # parent is not a git repository — nothing to verify

    try:
        ignored = subprocess.run(
            ["git", "-C", str(parent), "check-ignore", "-q", str(root)],
            capture_output=True,
            text=True,
        )
    except OSError:
        return  # git unavailable — nothing to verify

    if ignored.returncode == 1:
        raise StoreUnsafe(
            f"store at {root} sits inside a git-tracked parent repository at "
            f"{parent} that does not gitignore it — this would let the store "
            "be committed as a nested gitlink/submodule; add its path to the "
            "parent repository's .gitignore"
        )


def load_config(root):
    """Read and validate ``audit/config.json`` under ``root``. Return it as a dict.

    Raises :class:`ConfigError` for a missing file, malformed JSON, an
    unrecognised ``schema`` value, or a package that appears in more than one
    tier (each package is scheduled by exactly one cadence).
    """
    cfg_path = pathlib.Path(root) / "audit" / "config.json"
    if not cfg_path.is_file():
        raise ConfigError(f"missing config: {cfg_path}")

    try:
        cfg = json.loads(cfg_path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"malformed config at {cfg_path}: {exc}")

    if cfg.get("schema") != SCHEMA:
        raise ConfigError(
            f"unknown config schema {cfg.get('schema')!r} at {cfg_path} — expected {SCHEMA}"
        )

    seen = {}
    for tier_name, tier in (cfg.get("tiers") or {}).items():
        for package in tier.get("packages", []) or []:
            if package in seen:
                raise ConfigError(
                    f"package {package!r} appears in both {seen[package]!r} and "
                    f"{tier_name!r} tiers — each package must belong to exactly one tier"
                )
            seen[package] = tier_name

    return cfg


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        default=None,
        help="store root (default: %s)" % store_root(),
    )
    parser.add_argument(
        "--message",
        default="audit(store): record artifacts",
        help="commit message for the 'commit' action",
    )
    parser.add_argument(
        "action",
        choices=("ensure", "check", "commit"),
        help="'ensure' creates the layout and git repo; "
        "'check' verifies no-remote and prints the loaded config; "
        "'commit' stages the given paths and commits them to the store",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="for 'commit': the artifact paths to stage, inside the store",
    )
    args = parser.parse_args(argv)
    root = args.root or store_root()

    if args.action == "ensure":
        status = ensure_store(root)
        print(json.dumps(status, sort_keys=True))
        return 0

    if args.action == "commit":
        sha = commit_paths(root, args.paths, args.message)
        if sha:
            print(sha)
        return 0

    # action == "check"
    assert_no_remote(root)
    cfg = load_config(root)
    print(json.dumps(cfg, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
