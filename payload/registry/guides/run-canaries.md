# Guide — run-canaries

**Category:** tool
**Scope:** machine-global
**Status:** candidate

## Why this exists (evidence)
Probes whether each of your wired projects actually announces the
Resource Loop at session start, once the loop is live.

## When to deploy (triggers)
Post-rollout verification — confirming the loop fires in practice, not
just that the docs claim it does.

## Interface (how to invoke)
`bash ~/.claude/tools/run_canaries.sh` (expected: one `PASS` line per
project and a `canaries: N/N passed` summary; set `CANARY_MODEL=<model>`
to retry with a different probe model, and `PROJECTS_DIR` to point at
your projects directory).

## Composition (pairs with / hands off to)
Runs after `check-coverage` confirms the static doc cascade is in place;
both gate the rollout's exit state.

## Build & maintenance notes
Part of the `resource-loop` rollout tooling; probes each project under
`$PROJECTS_DIR` (default `~/projects`) with a headless Claude Code session.
