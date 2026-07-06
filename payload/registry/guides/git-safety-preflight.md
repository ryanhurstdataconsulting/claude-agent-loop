# Guide — git-safety-preflight

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The single most expensive class of failure observed was environmental, not
logical. iCloud "Desktop & Documents" evicted parts of a `.git` directory
mid-session and cost a full worktree; file-sync clobbered the `.venv`
interpreter symlink; and several repositories were carrying stranded, unpushed
work with no remote at all — one project had never been pushed off-machine
and another had no remote configured. This pattern recurred across multiple
projects. No existing resource covers file-sync git hazards, so this is a new
tool. Its job is to stop agents from re-diagnosing "lost work" that was never
actually lost, and to catch local-only commits before a disk failure can turn
them into real loss.

## When to deploy (triggers)
- Session start on any project that is a git repository.
- Before any non-trivial git operation: `git worktree add`, `git rev-parse`,
  `git push`, a branch cutover, or a rebase.
- After a machine restart or a long-paused session, when the working tree
  state is uncertain.
- Symptoms it explains: "fatal: not a git repository", a missing
  `.git/objects` entry, `git status` reporting phantom changes, a `.venv`
  whose `bin/python` symlink resolves to nothing.

## Interface (how to invoke)
Tool. Exact command line: `python3 ~/.claude/tools/git_safety_preflight.py`
(optionally with a path argument; defaults to the current working directory).
It warns — it does not block — and prints one remediation line per detected
hazard, then exits non-zero only when a repo is unrecoverable.

## Composition (pairs with / hands off to)
Runs alongside `env-tooling-preflight` at session start (this one owns repo
state; that one owns interpreter and toolchain health). Surfaced by the
`resource-loop` MATCH step. When it flags an unpushed tree it hands off to
the standing commit protocol (`test → commit → push`).

## Build & maintenance notes
Build sketch: resolve `pwd` against
`~/Library/Mobile Documents/com~apple~CloudDocs` to detect a file-synced
location; run `git fsck --connectivity-only` plus a `git rev-parse` smoke
test; assert each active repo has a remote and a clean-or-pushed tree; verify
`.venv/bin/python` resolves. Warn (never block) with a specific fix per miss.
Lives at `~/.claude/tools/git_safety_preflight.py`; testable with a fixture
repo pointed at a synthetic iCloud path and a remote-less clone.
