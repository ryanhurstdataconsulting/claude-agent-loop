# Guide — audit-dispatch

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Running the repo-security-auditor against every package every night would
burn agent turns on packages nobody touched since their last audit; skipping
by calendar alone would silently miss a package whose interval elapsed weeks
ago, because nothing keeps prompting it. `audit_dispatch` is the decision,
made in isolation from execution: it reads the consolidated store
(`audit_store`) and each package's git HEAD, and answers "is this due, and
why" — tier interval elapsed AND HEAD moved since the last audit, never
audited, or unverifiable. Keeping the decision pure, and separate from
`audit_run.sh`'s execution, means the policy can be unit-tested without ever
shelling out to a real agent session, and a bug in one never masks a bug in
the other.

## When to deploy (triggers)
- Nightly, by the `com.hdc.claude-agent-loop.repo-audit` launchd job, ahead
  of any `audit_run.sh` invocation.
- Manually, to preview tonight's selection without running anything:
  `python3 audit_dispatch.py --workspace ~/dev`.

## Interface (how to invoke)
```
audit_dispatch.py --workspace DIR [--root DIR] [--json]
```
`--workspace` is the directory holding one subdirectory per package named in
`config.json`. Prints one `package — reason` line per due package (or
`nothing due`), or the full list as JSON with `--json`. Always calls
`assert_no_remote()` before reading anything.

Contracts callers rely on:
- `head_sha()` never raises — a missing path, a non-repository, or a failed
  `git` invocation all resolve to `None` ("unknown"), never an error.
- `is_due()` treats an unknown HEAD as due, never as skippable.
- `select_due()` never lets one broken package abort the rest of the night's
  selection: a per-package failure becomes a loud due-entry naming the
  error, sorted to the front.
- A tier literally named `"excluded"` is skipped in full, regardless of its
  `interval_days`.

## Composition (pairs with / hands off to)
- Reads `audit_store.store_root()`, `assert_no_remote()`, and
  `load_config()` directly.
- Its output — the due list — is what the launchd job's dispatch step
  names; running `audit_run.sh` against each entry is the next, currently
  manual, link in the chain.
- `last_state()` reads the exact run-log JSON files `audit_run.sh` writes,
  so a change to one file's shape must be made in both.

## Build & maintenance notes
Lives at `payload/tools/audit_dispatch.py`. Tests:
`payload/tools/tests/test_audit_dispatch.py`. Stdlib only. `per_night_cap` in
`config.json` bounds how many packages one night's run touches even if more
are overdue — entries are sorted longest-overdue first, so the cap never
hides the worst case.
