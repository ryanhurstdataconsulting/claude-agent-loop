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
      .gitignore              (empty: the store tracks everything it holds)
      audit/
        config.json           (tier schedule; hand-written, not by this tool)
        runs/
        findings/
        digests/

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
    ``audit/{runs,findings,digests}``, writes an empty ``.gitignore`` (the
    store tracks everything it holds — there is nothing to ignore), and runs
    ``git init -q`` only when ``root/.git`` does not already exist. Returns a
    status dict describing what was done.
    """
    root = pathlib.Path(root)
    for sub in ("audit/runs", "audit/findings", "audit/digests"):
        os.makedirs(root / sub, exist_ok=True)

    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("")

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

    return {
        "root": str(root),
        "created": True,
        "git_initialised": initialised,
    }


def assert_no_remote(root):
    """Raise :class:`StoreUnsafe` if the store repo at ``root`` has any remote.

    The store holds client package names and audit findings that must never
    be pushed anywhere — this is the enforcement point for that invariant,
    meant to be called before anything writes to or reads from the store.
    """
    root = pathlib.Path(root)
    try:
        result = subprocess.run(
            ["git", "remote"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise StoreUnsafe(f"git is unavailable — cannot verify store at {root}: {exc}")

    remotes = result.stdout.strip()
    if remotes:
        named = ", ".join(remotes.splitlines())
        raise StoreUnsafe(
            f"store repo has a remote ({named}) — this store is local-only by design"
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
        "action",
        choices=("ensure", "check"),
        help="'ensure' creates the layout and git repo; "
        "'check' verifies no-remote and prints the loaded config",
    )
    args = parser.parse_args(argv)
    root = args.root or store_root()

    if args.action == "ensure":
        status = ensure_store(root)
        print(json.dumps(status, sort_keys=True))
        return 0

    # action == "check"
    assert_no_remote(root)
    cfg = load_config(root)
    print(json.dumps(cfg, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
