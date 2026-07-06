#!/usr/bin/env python3
"""Env/tooling preflight — advisory scan for interpreter and toolchain health.

Toolchain health was, until now, rediscovered per session as mid-task
failures instead of being checked up front: a clobbered ``.venv/bin/python``
symlink, a system Python silently used where 3.11+ was required, and missing
external binaries (ffmpeg, pandoc, weasyprint) reached for mid-pipeline.
macOS also ships bash 3.2 by default, so scripts using bash-4-only features
(``declare -A``, GNU-only flags) fail in ways that read as logic bugs.

Prints one green/red capability line per checked item, with a one-command
fix hint on every miss. This tool is advisory only: it always exits 0.

Checks:
  - ``.venv/bin/python`` presence + version >= 3.11 (only if a venv exists —
    a project need not have one);
  - presence of external tools on PATH (default: pandoc, weasyprint, ffmpeg;
    the list is caller-configurable via ``check_tools(names, ...)``);
  - a standing informational note about macOS's bash 3.2 default, since that
    is not a pass/fail condition, just a portability trap to keep in mind.

Stdlib only.
"""
import collections
import pathlib
import platform
import re
import shutil
import subprocess
import sys

Status = collections.namedtuple("Status", ["name", "ok", "detail", "fix"])

DEFAULT_TOOLS = ["pandoc", "weasyprint", "ffmpeg"]
MIN_PYTHON = (3, 11)

FIX_HINTS = {
    "pandoc": "brew install pandoc",
    "weasyprint": "pip install weasyprint  # inside the project's .venv",
    "ffmpeg": "brew install ffmpeg",
}

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _version_str(v):
    return ".".join(str(part) for part in v)


def check_tool(name, which=shutil.which, fix_hints=FIX_HINTS):
    """Return a Status for whether ``name`` resolves on PATH.

    ``which`` is injectable (defaults to ``shutil.which``) so tests can
    supply a fake resolver without touching the real PATH.
    """
    resolved = which(name)
    if resolved:
        return Status(name, True, resolved, None)
    fix = fix_hints.get(name, f"install {name} and ensure it is on PATH")
    return Status(name, False, "not found on PATH", fix)


def check_tools(names, which=shutil.which, fix_hints=FIX_HINTS):
    """Return one Status per name in ``names``, in order."""
    return [check_tool(n, which=which, fix_hints=fix_hints) for n in names]


def parse_version_output(output):
    """Parse a ``python --version``-style string (e.g. ``Python 3.11.4``) to a tuple."""
    m = _VERSION_RE.search(output or "")
    if not m:
        return None
    return tuple(int(g) for g in m.groups())


def _default_version_resolver(python_bin):
    try:
        res = subprocess.run(
            [str(python_bin), "--version"], capture_output=True, text=True
        )
    except OSError as exc:
        return str(exc)
    return (res.stdout + res.stderr).strip()


def check_venv_python(project_path, version_resolver=None):
    """Check ``<project_path>/.venv/bin/python`` presence + version floor.

    Returns ``None`` if no venv is present at all — the spec only requires
    this check "if a venv exists". ``version_resolver`` is injectable
    (defaults to actually invoking ``<python> --version``) so tests can
    supply a fake version string without needing a real interpreter.
    """
    python_bin = pathlib.Path(project_path) / ".venv" / "bin" / "python"
    if not python_bin.exists():
        return None

    resolver = version_resolver or _default_version_resolver
    raw = resolver(python_bin)
    version = parse_version_output(raw)

    floor_str = _version_str(MIN_PYTHON)
    if version is None:
        return Status(
            ".venv/bin/python",
            False,
            f"could not parse a version from {raw!r}",
            f"recreate the venv: `python3.11 -m venv .venv --clear` (need >= {floor_str})",
        )
    if version[:2] < MIN_PYTHON:
        return Status(
            ".venv/bin/python",
            False,
            f"{_version_str(version)} < {floor_str}",
            f"recreate with a >= {floor_str} interpreter: "
            f"`python3.11 -m venv .venv --clear`",
        )
    return Status(".venv/bin/python", True, _version_str(version), None)


def bash_portability_note():
    """A standing informational note about macOS's default bash 3.2.

    Not a pass/fail check — bash 3.2 is simply the platform default and
    scripts need to be written for it (no ``declare -A``, no GNU-only flags).
    """
    if platform.system() != "Darwin":
        return None
    return (
        "macOS ships bash 3.2 by default: avoid `declare -A` (associative "
        "arrays), `mapfile`, and GNU-only flags (e.g. base64/base32 options) "
        "in shell scripts meant to run here — either write bash-3.2-portable "
        "code, or install a newer bash with `brew install bash`."
    )


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    project_path = pathlib.Path(argv[0]) if argv else pathlib.Path.cwd()

    statuses = []
    venv_status = check_venv_python(project_path)
    if venv_status is not None:
        statuses.append(venv_status)
    statuses.extend(check_tools(DEFAULT_TOOLS))

    for s in statuses:
        light = "green" if s.ok else "red"
        line = f"[{light}] {s.name}: {s.detail}"
        if not s.ok and s.fix:
            line += f"  fix: {s.fix}"
        print(line)

    note = bash_portability_note()
    if note:
        print(f"[note] {note}")

    fails = sum(1 for s in statuses if not s.ok)
    print(
        f"env_tooling_preflight: {'OK' if fails == 0 else 'ISSUES'} "
        f"— {fails} of {_plural(len(statuses), 'check')} failed",
        file=sys.stderr,
    )
    return 0  # advisory: warns, never blocks


if __name__ == "__main__":
    sys.exit(main())
