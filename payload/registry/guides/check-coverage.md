# Guide — check-coverage

**Category:** tool
**Scope:** machine-global
**Status:** candidate

## Why this exists (evidence)
Statically verifies that every one of your target projects has the
CLAUDE.md stub and SUBAGENTS.md roster the doc cascade requires.

## When to deploy (triggers)
After wiring the doc cascade into a project, or before running
`run-canaries` (which tests runtime behavior rather than file presence).

## Interface (how to invoke)
`bash ~/.claude/tools/check_coverage.sh` (expected: one `OK` line per
project and a `coverage: N/N` summary; set `PROJECTS_DIR` to point at
your projects directory).

## Composition (pairs with / hands off to)
Precedes `run-canaries` in the verification sequence.

## Build & maintenance notes
Part of the `resource-loop` rollout tooling; validates the doc cascade
across every project under `$PROJECTS_DIR` (default `~/projects`).
