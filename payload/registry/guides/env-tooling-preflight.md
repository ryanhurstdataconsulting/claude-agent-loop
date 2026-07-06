# Guide — env-tooling-preflight

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Toolchain health was rediscovered per session as mid-task failures rather than
checked up front. A `.venv/bin/python` had been clobbered to a broken symlink;
system Python 3.9 was silently used where 3.11+ was required; and required
binaries (ffmpeg, pandoc, weasyprint) plus fonts were missing when a task
reached for them. This pattern recurred across multiple projects. macOS ships
bash 3.2, so scripts using `declare -A` or `base32` broke in ways that read as
logic bugs. It is the toolchain companion to `git-safety-preflight`, which
owns repo state rather than the interpreter and binaries.

## When to deploy (triggers)
- Session start on any Python or build project.
- Before a task that needs a specific external binary (a render, an ffmpeg
  pipeline, a document build).
- Symptoms it explains: `ModuleNotFoundError` from the wrong interpreter,
  "command not found: ffmpeg/pandoc/weasyprint", a `declare: -A: invalid
  option` error, a font-missing render fallback.

## Interface (how to invoke)
Tool. Exact command line: `python3 ~/.claude/tools/env_tooling_preflight.py`
(or a `make env-check` target in a project that adopts it). It prints a
green/red capability line per checked item and a one-command fix hint for each
miss; exits non-zero when a required tool is absent.

## Composition (pairs with / hands off to)
Runs at session start next to `git-safety-preflight` (interpreter/binaries vs.
repo state). Hands off to `document-render` (which depends on
pandoc/weasyprint/LibreOffice being present) and to `tauri-desktop-dev` builds.
Surfaced by `resource-loop`.

## Build & maintenance notes
Build sketch: a small script (or Makefile target) that verifies
`.venv/bin/python` is a valid ≥ 3.11 interpreter, probes for each tool a
project declares it needs, and checks for bash-3.2 portability pitfalls. Keep
the required-tool list project-declarable so the check is not one fixed set.
Lives at `~/.claude/tools/env_tooling_preflight.py`; test by pointing it at a
venv with a deliberately broken symlink and a PATH missing one binary.
