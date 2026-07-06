# Guide — lint-registry

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Validates the registry index against its guide files — row format,
categories, name↔guide bijection, and the 150-row budget.

## When to deploy (triggers)
After any edit to `REGISTRY.md` or `registry/guides/` — before
committing a registry change.

## Interface (how to invoke)
`python3 ~/.claude/tools/lint_registry.py [<registry-root>]` (defaults
to `~/.claude/registry`).

## Composition (pairs with / hands off to)
Gates every `resource-loop` registry edit; pairs with
`check-coverage` (verifies the loop's doc cascade, a separate concern
from index/guide integrity).

## Build & maintenance notes
Lives at `~/.claude/tools/lint_registry.py`; enforces one row per
resource, a guide file per row, and no orphan guides.
