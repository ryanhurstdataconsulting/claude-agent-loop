# Guide — route-role

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The deterministic `HOOK → AGENT` edge. The loop's MATCH step needs to pick a
role without model judgment, so the same task always lands on the same role:
plain keyword arithmetic over each role's `routes:` phrases (a found multi-word
phrase scores 2, a single word on a boundary scores 1; below the confidence
floor the answer is `generalist`, stated, never guessed).

## When to deploy (triggers)
- Automatically at MATCH, on every new task (the SessionStart directive says
  so).
- Manually, to check where a task would land:
  `python3 ~/.claude/tools/route_role.py "tune this slow query"`.

## Interface (how to invoke)
`python3 ~/.claude/tools/route_role.py [--roles-dir DIR] [--json] "<task>"`
Human output is the `Role — <role> (score N: matched…) · skills: … · mcps: …`
announce line; `--json` returns `{role, score, matched, skills, mcps, reason}`.
Always exits 0.

## Composition (pairs with / hands off to)
- Inside `resource-loop` MATCH; announces alongside the deploying line.
- Reads `role-agents` files; `lint-roles` keeps them valid.
- A `generalist` result hands MATCH back to the semantic pass unchanged.

## Build & maintenance notes
Lives at `payload/tools/route_role.py` (imports the frontmatter parser from
`lint_roles.py`). Tests: `payload/tools/tests/test_route_role.py`, including a
golden-route case per shipped role. If a real task misroutes, enrich that
role's `routes:` with the natural phrasing and re-run the tests — routing
quality is a data edit, not a code edit.
