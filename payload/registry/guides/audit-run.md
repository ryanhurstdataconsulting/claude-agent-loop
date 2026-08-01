# Guide — audit-run

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The scheduling layer runs the repo-security-auditor unattended, nightly,
against repositories the developer may have open with uncommitted work — so
the whole design turns on one property: the live checkout is never touched.
`audit_run.sh` is that guarantee made concrete. The audit happens inside a
throwaway `git worktree` checked out detached at HEAD, with a cleanup trap
registered before the worktree is created, so a run interrupted mid-flight
can never orphan one. Two safety gates run on the findings document before
any branch or commit exists, so an aborted run leaves the package repository
exactly as it was.

## When to deploy (triggers)
- Nightly, once per due package, dispatched after `audit_dispatch.py` names
  it.
- Manually, to preview or test a single package:
  `audit_run.sh <package-path> <store-root> --dry-run`.

## Interface (how to invoke)
```
audit_run.sh <package-path> <store-root> [--dry-run]
```
Exit codes the scheduler distinguishes: `0` success (committed to
`audit/security-<date>`, never pushed), `1` run failure (the CLI failed, or
produced no findings file), `2` usage error, `3` gate abort (a safety gate
refused the output; nothing was created), `4` the `claude` CLI is absent or
not executable. Environment overrides — `AUDIT_CLAUDE_BIN`, `AUDIT_GATE_DIR`,
`AUDIT_MAX_TURNS`, `AUDIT_TIMEOUT` — exist for testing and calibration, never
for routine use.

**A decision recorded here, not re-litigated:** the agent's tool allowlist
names read-only git subcommands one at a time (`git log`, `git diff`, `git
ls-files`, `git status`, `git rev-parse`) instead of the blanket
`Bash(git:*)` the original design spec called for. `--add-dir` scopes the
file tools to the worktree but has no effect on `Bash`, and the live package
repository is one `git rev-parse --git-common-dir` away from inside that
worktree — a blanket git allowlist would let an unattended agent, reading
potentially adversarial repository content, run `checkout`/`reset`/`push`
against the developer's real checkout with nothing but prompt text
discouraging it. The design spec (local-only, in the controlling repo) has
been amended to match this narrower allowlist; the shipped script is
authoritative.

## Composition (pairs with / hands off to)
- Dispatched for each package `audit_dispatch.py` names as due.
- Invokes the pre-existing `repo-security-auditor` agent headlessly
  (`--agent repo-security-auditor`), scoped to the worktree only.
- Runs `secret_pii_scrub_gate.py` on every changed path and
  `prose_grammar_gate.py` on `SECURITY_AUDIT.md` before any commit — two of
  the same safety gates the autonomy pipeline (`loop_autocommit.sh`) uses,
  reused here rather than reinvented.
- Writes its run log into the layout `audit_store.py` owns;
  `audit_digest.py` reads it back.
- Fires an OS notification directly for a Critical/High finding — it does
  not wait for the digest.

## Build & maintenance notes
Lives at `payload/tools/audit_run.sh`. Tests:
`payload/tools/tests/test_audit_run.sh`. macOS bash-3.2 portable: no
`mapfile`, no associative arrays, no `set -e` (gate handling reads exit
codes, which `set -e` would turn into an abort before the blocked-run log
could be written). Cleanup is belt-and-braces — `worktree remove`, then `rm
-rf`, then a name-matched drop of the script's own worktree registration —
deliberately never `git worktree prune`, which is repo-global and would
remove an unrelated worktree living on a volume that happens to be
unmounted tonight.
