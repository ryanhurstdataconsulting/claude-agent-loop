# Guide — audit-dispatch

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Running the repo-security-auditor against every package every night would
burn agent turns on packages nobody touched since their last audit; skipping
by calendar alone would silently miss a package whose interval elapsed weeks
ago, because nothing keeps prompting it. `audit_dispatch` owns the whole
night. It reads the consolidated store (`audit_store`) and each package's git
HEAD to answer "is this due, and why" — tier interval elapsed AND HEAD moved
since the last audit, never audited, or unverifiable — then drives that due
list through `audit_run.sh` one package at a time and closes with a single
`audit_digest` render.

The two halves stay strictly separable, which is what keeps them testable.
The policy half never shells out to anything. The execution half never
invokes `claude` directly: it invokes `audit_run.sh`, resolved through
`AUDIT_RUN_BIN` exactly as `audit_run.sh` resolves the CLI through
`AUDIT_CLAUDE_BIN`. That indirection is a safety control, not a convenience —
no test may ever start a real, billed agent session, and an injectable runner
is the only way to guarantee it.

## When to deploy (triggers)
- Nightly, by the `com.hdc.claude-agent-loop.repo-audit` launchd job. This is
  the job's only entry point and it runs the entire sweep.
- Manually, to preview tonight's selection and the exact command each package
  would get, spending nothing:
  `python3 audit_dispatch.py --dry-run` (add `--workspace DIR` to point it at
  a tree other than the configured one).

## Interface (how to invoke)
```
audit_dispatch.py [--workspace DIR] [--root DIR] [--json] [--dry-run]
                  [--audit-run-bin PATH]
```
The workspace is the directory holding one subdirectory per package named in
`config.json`. It is resolved in this order: `--workspace` on the command
line, then the `workspace` key in `<store>/audit/config.json`, then `~/dev`.
The config key is the intended home for a machine's real answer — it is
local-only, never committed, and sits beside the package list it belongs with,
whereas the launchd plist is a template shipped verbatim to every machine and
so must not name one machine's home directory. A `workspace` key that is
present but is not a non-empty string raises `ConfigError` rather than falling
back, because a malformed root resolves every package to a path that does not
exist and the sweep would report "never audited" forever with no clue why.

A plain invocation **runs the audits**: it prints the due list,
invokes `audit_run.sh <path> <root> --key <package>` per package in sequence,
renders one digest, and fires an alert per package. `--dry-run` prints the
same plan and invokes nothing — use it to exercise the launchd job safely.
`--json` emits the whole night as one object (`due`, `results`, `alerts`,
`digest`). `ensure_store()` and `assert_no_remote()` run before anything is
read or written.

Contracts callers rely on:
- `head_sha()` never raises — a missing path, a non-repository, or a failed
  `git` invocation all resolve to `None` ("unknown"), never an error.
- `is_due()` treats an unknown HEAD as due, never as skippable.
- `select_due()` never lets one broken package abort the rest of the night's
  selection: a per-package failure becomes a loud due-entry naming the
  error, sorted to the front.
- `run_due()` holds the same line at execution time: a package that crashes,
  hangs, or exits non-zero costs exactly itself, and the rest of the night
  still runs.
- Runs are sequential by design. Each one is a full agent session against a
  real repository; running several at once would multiply peak cost, contend
  for the same rate limit, and make the per-package timeout meaningless.
- A tier literally named `"excluded"` is skipped in full, regardless of its
  `interval_days`.

## Composition (pairs with / hands off to)
- Reads `audit_store.ensure_store()`, `store_root()`, `assert_no_remote()`,
  and `load_config()` directly.
- Invokes `audit_run.sh` once per due package, passing the config key with
  `--key` so that what the run WRITES and what `last_state()` READS are the
  same store path by construction.
- Calls `audit_digest.write_digest()` exactly once, after the last package,
  and `audit_digest.severity_alert()` per run log to decide what interrupts.
  It sets `AUDIT_NOTIFY=0` for its children so a single event never produces
  two OS notifications.
- `last_state()` reads the exact run-log JSON files `audit_run.sh` writes,
  so a change to one file's shape must be made in both.

**The launchd job's logs do not go to `/tmp`.**
`com.hdc.claude-agent-loop.repo-audit.plist` redirects stdout and stderr to
`~/.claude/metrics/audit/logs/repo-audit.{out,err}.log` and leaves launchd's
own `StandardOutPath`/`StandardErrorPath` at `/dev/null`. This is a
deliberate divergence from the `usage-poll` plist, which logs to
world-readable `/tmp`: that job emits anonymous quota numbers, while this one
prints one client package name per due line, which is exactly the data the
store is guarded as local-only for. The redirect is done inside the shell
command rather than through the plist keys because launchd performs no
variable or tilde expansion in path keys, and a template copied verbatim onto
any machine cannot hardcode a home directory.

## Build & maintenance notes
Lives at `payload/tools/audit_dispatch.py`. Tests:
`payload/tools/tests/test_audit_dispatch.py`. Stdlib only. `per_night_cap` in
`config.json` bounds how many packages one night's run touches even if more
are overdue — entries are sorted longest-overdue first, so the cap never
hides the worst case. An empty night writes no digest: doing so would advance
the render window and fire the SessionStart nudge for a file with nothing in
it.
