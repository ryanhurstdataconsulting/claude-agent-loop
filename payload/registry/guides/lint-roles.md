# Guide — lint-roles

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The AGENT layer's schema guard. Role files bind the deterministic stack
together — a typo'd skill name or an unknown MCP would be a dead edge the
router happily follows. This linter enforces the bijection the same way
`lint-registry` does for the index: every declared skill must exist in the
library, every declared MCP must have a registry row, and the frontmatter shape
(name == role == filename, non-empty description and routes) must hold.

## When to deploy (triggers)
- After ANY edit under `agents/roles/` — add, rename, or reroute a role.
- In CI / test runs: `test_lint_roles.py` lints the shipped payload roles.

## Interface (how to invoke)
Live install: `python3 ~/.claude/tools/lint_roles.py`
Repo/CI: `python3 payload/tools/lint_roles.py payload/agents/roles
--skills-dir payload/skills --registry payload/registry/REGISTRY.md`
Exit 0 clean; 1 with `LINT:` lines and a FAIL summary.

## Composition (pairs with / hands off to)
- Guards `role-agents`; `route-role` consumes what this validates.
- Run alongside `lint-registry` whenever a registry edit accompanies a role
  edit.

## Build & maintenance notes
Lives at `payload/tools/lint_roles.py`; its frontmatter parser is also imported
by `route_role.py` (one parser, two consumers). Tests:
`payload/tools/tests/test_lint_roles.py`.
