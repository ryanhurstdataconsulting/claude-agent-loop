# Guide — audit-run

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The scheduling layer runs the repo-security-auditor unattended, nightly,
against repositories the developer may have open with uncommitted work — so
the whole design turns on one property: the live checkout is never touched.
`run.sh` is that guarantee made concrete. The audit happens inside a
throwaway `git worktree` checked out detached at HEAD, with a cleanup trap
registered before the worktree is created, so a run interrupted mid-flight
can never orphan one. Two safety gates run on the findings document before
any branch or commit exists, so an aborted run leaves the package repository
exactly as it was.

## When to deploy (triggers)
- Nightly, once per due package. `dispatch.py` iterates its own due
  list and invokes this script per package, sequentially — that chain is
  wired, not manual.
- Manually, to preview or test a single package:
  `run.sh <package-path> <store-root> --dry-run`.

## Interface (how to invoke)
```
run.sh <package-path> <store-root> [--key KEY] [--dry-run]
```
`--key` is the package's key in `config.json`, and it is the store path this
run writes under. It defaults to `basename <package-path>` for a hand-run
invocation, but the dispatcher always passes it explicitly: real keys are
workspace-relative paths, so a re-derived basename would write state to a
path `dispatch.last_state()` never reads back, and every nested package
would report "never audited" every night at full agent cost.

Exit codes the scheduler distinguishes: `0` success (committed to
`audit/security-<date>`, never pushed), `1` run failure (the CLI failed,
produced no findings file, or the run log could not be written), `2` usage
error, `3` gate abort (a safety gate refused the output; nothing was
created), `4` the `claude` CLI is absent or not executable, `5` quarantined
(see below). Environment overrides — `AUDIT_CLAUDE_BIN`, `AUDIT_GATE_DIR`,
`AUDIT_MAX_TURNS`, `AUDIT_TIMEOUT`, `AUDIT_GIT_TIMEOUT`, `AUDIT_NOTIFY` —
exist for testing, calibration, and the dispatcher's own use, never for
routine hand-running.

**A decision recorded here, not re-litigated: the secret gate is split in
two, because a hit in each half means something different.** Over the
auditor's own *code fixes*, a hit aborts the commit outright — an unattended
agent must never introduce a credential into a client's source. Over
`SECURITY_AUDIT.md` itself, a hit **quarantines** instead: quoting the
credential it found is a findings document's job, so the most valuable audits
this layer can produce are exactly the ones guaranteed to trip the gate. The
document is copied to `audit/quarantine/<key>/<date>-SECURITY_AUDIT.md` in
the local-only store, the run log records `verdict: "quarantined"`, an alert
fires, and the package repository receives nothing. The human keeps the
finding; the client repo never receives unredacted content.

**And a second: git calls run with the audited repository's hooks disarmed.**
A worktree shares `.git/hooks` with the checkout it came from, so `commit`
carries `--no-verify` and every hook-triggering git call is backgrounded,
waited on so the cleanup trap can still fire, and bounded by
`AUDIT_GIT_TIMEOUT`. Without that, one hanging `pre-commit` in an audited
repository would leave a worktree registered in the developer's checkout
indefinitely — the exact damage this script exists to prevent — and a
`pre-commit` that stages files of its own would put unscanned content into
the index the gates had just cleared.

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
- Invoked by `dispatch.py` once per due package, sequentially, with
  `--key <package>` taken straight from `config.json`.
- Invokes the pre-existing `repo-security-auditor` agent headlessly
  (`--agent repo-security-auditor`), scoped to the worktree only.
- Runs `secret_pii_scrub_gate.py` twice — once over every changed code path,
  once over `SECURITY_AUDIT.md` — and `prose_grammar_gate.py` on
  `SECURITY_AUDIT.md`, all before any commit exists. These are the same
  safety gates the autonomy pipeline (`loop_autocommit.sh`) uses, reused here
  rather than reinvented.
- Writes its run log into the layout `store.py` owns and commits it to
  the store's own local git history through `store.commit_paths()` —
  explicit paths, no remote, no push. `digest.py` reads it back.
- Fires an OS notification directly for a Critical/High finding — it does
  not wait for the digest. During a dispatched sweep this is suppressed
  (`AUDIT_NOTIFY=0`) because the dispatcher notifies from the run logs
  instead, so one event never produces two notifications.

## Build & maintenance notes
Lives at `payload/tools/dispatch/run.sh`. Tests:
`payload/tools/tests/test_audit_run.sh`. macOS bash-3.2 portable: no
`mapfile`, no associative arrays, no `set -e` (gate handling reads exit
codes, which `set -e` would turn into an abort before the blocked-run log
could be written). Cleanup is belt-and-braces — `worktree remove`, then `rm
-rf`, then a name-matched drop of the script's own worktree registration —
deliberately never `git worktree prune`, which is repo-global and would
remove an unrelated worktree living on a volume that happens to be
unmounted tonight.
