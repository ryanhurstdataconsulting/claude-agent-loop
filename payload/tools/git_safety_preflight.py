#!/usr/bin/env python3
"""Git safety preflight — advisory scan for file-sync and repo-health hazards.

A common and costly class of failure is environmental, not logical: iCloud "Desktop & Documents" sync evicting parts
of a ``.git`` directory mid-session, a clobbered ``.venv/bin/python`` symlink,
and repositories carrying stranded, unpushed work with no remote at all. This
scanner surfaces those hazards up front instead of letting an agent re-diagnose
"lost work" that was never actually lost.

Checks (each returns zero or more ``Finding`` objects):
  (a) the target path resolves under iCloud-synced storage
      (``~/Library/Mobile Documents/com~apple~CloudDocs``);
  (b) the path is a working git repository (``git rev-parse``);
  (c) ``.git`` object-graph integrity (``git fsck --connectivity-only``);
  (d) a remote is configured;
  (e) the working tree is dirty, or the current branch has no upstream, or the
      current branch is ahead of its upstream (unpushed commits);
  (f) a ``.venv/bin/python`` symlink, if present, resolves to a real file.

This tool WARNS — it never blocks. It always exits 0 (advisory only) and
prints one remediation line per detected hazard. If the target is not a git
repository, checks (c)-(e) are skipped as meaningless (there is no repo state
to report on beyond "this isn't one").

Stdlib only.
"""
import collections
import os
import pathlib
import subprocess
import sys

Finding = collections.namedtuple("Finding", ["check", "message"])

ICLOUD_PARTS = ("Library", "Mobile Documents", "com~apple~CloudDocs")


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _run_git(args, cwd):
    """Run a git subcommand in ``cwd``; never raises (missing git is reported, not fatal)."""
    try:
        return subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True
        )
    except OSError as exc:
        return subprocess.CompletedProcess(args, 127, stdout="", stderr=str(exc))


def _desktop_documents_sync_active(component, home):
    """Return True if ``component`` ("Desktop" or "Documents") is iCloud-backed.

    macOS's "Desktop & Documents" sync backs ``~/Desktop`` and ``~/Documents``
    with a firmlink to the CloudDocs tree — and critically, resolving a path
    that explicitly names the CloudDocs alias collapses it right back down to
    the friendly ``~/Desktop`` form, hiding the very fact we want to detect.
    So this checks the other direction: does the CloudDocs-side twin of the
    folder exist at all? If so, sync is on for that folder account-wide.
    """
    marker = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / component
    return marker.is_dir()


def check_icloud_sync(path):
    """Return a Finding if ``path`` is exposed to iCloud file-sync eviction risk.

    Deliberately avoids ``.resolve()`` on the input path: on a machine with
    Desktop & Documents sync active, resolving an explicit CloudDocs alias
    silently collapses it to the plain ``~/Desktop`` form, which would make
    the hazard undetectable. Two cases are checked instead:
      1. the path literally names the CloudDocs alias
         (``~/Library/Mobile Documents/com~apple~CloudDocs/...``) — this is
         what makes the check testable with a synthetic, non-existent path;
      2. the path is under the friendly ``~/Desktop`` or ``~/Documents`` and
         that folder is, in fact, iCloud-synced on this machine.
    """
    home = pathlib.Path.home()
    literal = pathlib.Path(path).expanduser()
    try:
        rel = literal.relative_to(home)
    except ValueError:
        return None  # outside the home directory entirely; not our concern

    parts = rel.parts
    if parts[: len(ICLOUD_PARTS)] == ICLOUD_PARTS:
        return Finding(
            "icloud-sync",
            f"{literal} is under the iCloud CloudDocs alias "
            "(Library/Mobile Documents/com~apple~CloudDocs) — iCloud can evict "
            ".git internals mid-session; move the repo outside the synced tree "
            "or turn off Desktop & Documents sync in "
            "System Settings > Apple ID > iCloud.",
        )

    if parts and parts[0] in ("Desktop", "Documents"):
        if _desktop_documents_sync_active(parts[0], home):
            return Finding(
                "icloud-sync",
                f"{literal} is under ~/{parts[0]}, and Desktop & Documents "
                "iCloud sync is active on this machine (it silently backs "
                f"~/{parts[0]} with a CloudDocs firmlink) — iCloud can evict "
                ".git internals mid-session; move the repo outside "
                f"~/{parts[0]} or turn off Desktop & Documents sync in "
                "System Settings > Apple ID > iCloud.",
            )
    return None


def check_is_repo(path):
    """Return a Finding if ``path`` is not a working git repository."""
    res = _run_git(["rev-parse", "--is-inside-work-tree"], path)
    if res.returncode != 0 or res.stdout.strip() != "true":
        return Finding(
            "not-a-repo",
            f"{path} is not a git repository (`git rev-parse` failed) "
            "— run `git init` if this should be tracked, or check that you are "
            "in the intended repo root.",
        )
    return None


def check_fsck(path):
    """Return a Finding if ``git fsck --connectivity-only`` reports a problem."""
    res = _run_git(["fsck", "--connectivity-only"], path)
    if res.returncode != 0:
        detail_lines = (res.stdout + res.stderr).strip().splitlines()
        first = detail_lines[0] if detail_lines else "git fsck reported a problem"
        return Finding(
            "fsck-failed",
            f"`git fsck --connectivity-only` failed in {path}: {first} "
            "— .git objects may be corrupted or evicted by file sync; consider "
            "`git fsck --full` and re-cloning from the remote if objects are missing.",
        )
    return None


def check_remote(path):
    """Return a Finding if no git remote is configured."""
    res = _run_git(["remote"], path)
    if res.returncode == 0 and res.stdout.strip():
        return None
    return Finding(
        "no-remote",
        f"{path} has no git remote configured — local-only commits are one disk "
        "failure from being lost; add one with `git remote add origin <url>` and push.",
    )


def check_unpushed_or_dirty(path):
    """Return a list of Findings for a dirty working tree / unpushed commits."""
    findings = []
    status = _run_git(["status", "--porcelain"], path)
    if status.returncode == 0 and status.stdout.strip():
        findings.append(
            Finding(
                "dirty-tree",
                f"{path} has uncommitted changes — commit (or stash) before "
                "switching tasks; see the test -> commit -> push protocol.",
            )
        )

    upstream = _run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], path
    )
    if upstream.returncode != 0:
        findings.append(
            Finding(
                "no-upstream",
                f"{path}'s current branch has no upstream tracking branch "
                "— push with `-u` (e.g. `git push -u origin <branch>`) so future "
                "pushes are one command.",
            )
        )
    else:
        branch = upstream.stdout.strip()
        ahead = _run_git(["rev-list", "--count", f"{branch}..HEAD"], path)
        count = ahead.stdout.strip() if ahead.returncode == 0 else ""
        if count.isdigit() and int(count) > 0:
            findings.append(
                Finding(
                    "unpushed-commits",
                    f"{path} has {_plural(int(count), 'commit')} not pushed "
                    f"to {branch} — push before ending the session.",
                )
            )
    return findings


def check_venv_symlink(path):
    """Return a Finding if ``.venv/bin/python`` is a broken symlink.

    If ``.venv/bin/python`` does not exist at all (no venv, or not a symlink),
    there is nothing to report — the spec only asks us to check it "if present".
    """
    venv_python = pathlib.Path(path) / ".venv" / "bin" / "python"
    if not venv_python.is_symlink():
        return None
    if venv_python.exists():
        return None
    target = os.readlink(venv_python)
    return Finding(
        "broken-venv-symlink",
        f"{venv_python} is a symlink to {target} which does not resolve "
        "— the venv interpreter is broken (often from iCloud evicting the "
        "target); recreate it with `python3 -m venv .venv`.",
    )


def run_checks(path):
    """Run every check against ``path`` and return the accumulated Findings.

    If the path is not a git repository, checks (c)-(e) — which only make
    sense inside a repo — are skipped rather than emitting cascading noise.
    """
    path = pathlib.Path(path)
    findings = []

    icloud = check_icloud_sync(path)
    if icloud is not None:
        findings.append(icloud)

    repo_finding = check_is_repo(path)
    if repo_finding is not None:
        findings.append(repo_finding)
        venv_finding = check_venv_symlink(path)
        if venv_finding is not None:
            findings.append(venv_finding)
        return findings

    for check in (check_fsck, check_remote):
        f = check(path)
        if f is not None:
            findings.append(f)

    findings.extend(check_unpushed_or_dirty(path))

    venv_finding = check_venv_symlink(path)
    if venv_finding is not None:
        findings.append(venv_finding)

    return findings


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    path = pathlib.Path(argv[0]) if argv else pathlib.Path.cwd()

    findings = run_checks(path)
    for f in findings:
        print(f"[{f.check}] {f.message}")

    status = "WARN" if findings else "OK"
    print(
        f"git_safety_preflight: {status} — {_plural(len(findings), 'warning')}",
        file=sys.stderr,
    )
    return 0  # advisory: warns, never blocks


if __name__ == "__main__":
    sys.exit(main())
