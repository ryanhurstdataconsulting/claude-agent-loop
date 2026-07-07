# Guide — skill-library

**Category:** skill
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
A single index row for the role-based skill library: 157 generic, publication-safe
`SKILL.md` files spanning every role in a tech company — product management,
program/project management, UX research, product/UI design and design systems,
frontend/backend/full-stack/mobile/embedded/API engineering, architecture, DevOps,
SRE, platform, cloud, security, QA/SDET, release/build, data engineering, analytics
engineering, DBA, data science, ML engineering, MLOps, AI/GenAI, engineering
management and leadership, DevRel, solutions engineering, technical writing, and
technical support. Rather than 157 registry rows (which would overrun the index
budget and drown MATCH), the library is indexed once here and browsed through
`skills/CATALOG.md`.

## When to deploy (triggers)
- A task falls inside one of the 33 role families and no more specific registry
  resource already matches. Grep `skills/CATALOG.md` for the closest skill, then
  invoke it by name.
- You need to see what generic role-based skills exist before building a new one —
  check the catalog first to avoid duplicating an existing skill.

## Interface (how to invoke)
Browse: read `payload/skills/CATALOG.md` (grouped by family; `★` marks cross-cutting
skills). Invoke a specific skill: `Skill(<skill-name>)` once installed. Each skill
lives at `payload/skills/<name>/SKILL.md` and installs via its MANIFEST `link-dir`
entry.

## Composition (pairs with / hands off to)
- Layers under `resource-loop`: the loop MATCHes a task, and where the match is a
  role-family capability, this library supplies the skill.
- Cross-cutting skills (e.g. `ci-pipeline-authoring`, `adr-authoring`,
  `eval-harness`) are consumed by several families — prefer the shared skill over a
  role-specific near-duplicate.
- Generic counterparts to machine-specific skills: the library's
  `read-only-diagnostic-query-pack` and `explain-analyze-query-tuning` generalize
  the patterns behind a project's own database skill; `well-architected-review`
  formalizes the cloud-architecture assessment pattern.

## Build & maintenance notes
Skills were authored one family at a time, each passing a grammar gate, a
client-marker scan, and a visibility classifier before landing. To add a skill:
create `payload/skills/<name>/SKILL.md`, add a `link-dir skills/<name>` line to the
MANIFEST, and regenerate `CATALOG.md`. Keep every skill generic — no company,
client, machine, or personal reference. Lint the registry after any edit here:
`python3 payload/tools/lint_registry.py payload/registry`.
