# Guide — role-agents

**Category:** agent
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The AGENT layer of the deterministic `HOOK → AGENT → SKILL → TOOL` stack. Each
file in `agents/roles/<role>.md` is a company role — data-scientist,
data-engineer, dba, cloud-architect, product-manager (more roles land over
time) — declaring, in frontmatter, the `routes:` phrases the router scores, the
`skills:` it operates from the skill library, and the `mcps:` best suited to its
job. The frontmatter also carries harness-compatible `name`/`description` keys,
so a role can be dispatched directly as a subagent.

## When to deploy (triggers)
- Automatically: the resource loop's MATCH step runs `route_role.py` over the
  task; a confident match activates the role (its skills become the MATCH
  shortlist, its MCPs are preferred where configured).
- Manually: dispatch the role by name as a subagent when a task clearly belongs
  to one role end to end.

## Interface (how to invoke)
Router: `python3 ~/.claude/tools/route_role.py "<task text>"` (add `--json` for
programmatic use). Files: `~/.claude/agents/roles/<role>.md`. Add a role by
creating a new file in the same schema; then lint:
`python3 ~/.claude/tools/lint_roles.py`.

## Composition (pairs with / hands off to)
- Sits inside `resource-loop` MATCH (the role hop) — see that guide.
- `lint-roles` guards the schema; `skill-library` supplies the SKILL layer the
  roles reference; each skill's References section names its TOOL layer.
- Roles never gate: every library skill stays directly invocable.

## Build & maintenance notes
Lives at `payload/agents/roles/` (symlinked via the MANIFEST `link-dir`).
Linted by `lint_roles.py` (tests: `payload/tools/tests/test_lint_roles.py`);
routed by `route_role.py` (tests: `payload/tools/tests/test_route_role.py`,
including golden routes per role). Keep `routes:` phrases natural — the router
is keyword arithmetic, so a phrasing users actually type is worth more than a
taxonomy term.
