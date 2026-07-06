---
name: resource-loop
description: Run at the start of EVERY session and before every new task — match the task against your resource registry, announce deployments, file gaps as candidates, and route subagents by model tier. Triggers - any new user task, any subagent dispatch decision, any "should I build this inline" moment.
---

# Resource Loop

The registry index is injected at session start inside `<resource-loop>` tags. If
it is absent (hook failure, subagent context), read
`~/.claude/registry/REGISTRY.md` directly.

## The four steps

1. **MATCH** — semantically match the task against the index. Think in task
   shapes, not keywords: "make the chart pop" matches
   visual-hierarchy-layered-charts. Consult `~/.claude/registry/TRIGGERS.md` as a
   keyword and file-glob shortcut alongside the semantic match — it is an
   accelerator, not a replacement for reading the task. Read the full guide
   (`~/.claude/registry/guides/<name>.md`) for anything you will deploy.
2. **ANNOUNCE** — before work starts, output exactly one line:
   `Resource Loop — deploying: <name> (<category>) — <reason>[; …]`
   or, when nothing matches:
   `Resource Loop — no registry match; proceeding bare.`
3. **GAP** — if the task exposes a recurring need (seen in ≥ 2 sessions, or ≥ 3
   times this session) with no matching resource: write
   `~/.claude/registry/candidates/YYYY-MM-DD-<slug>.md` and tell the user. NEVER
   auto-create the resource — creation is gated on your approval.
4. **ROUTE** — when dispatching subagents:
   | Work type | Model |
   |---|---|
   | Planning, architecture, synthesis review | session model |
   | Creation-heavy (code, guides, skills, prose) | `model: opus` |
   | Mechanical (extraction, sweeps, lint fixes, probes) | `model: sonnet` (haiku for trivial probes) |
   Opus creators sub-delegate mechanical subtasks to Sonnet.

## Subagent rule

Carry this loop into every subagent brief: paste the ANNOUNCE format, the
relevant guide pointers, and the ROUTE table into the dispatch prompt.

## First run

Run `Skill(environment-bootstrap)` once to tailor this registry — and the
directives in `~/.claude/CLAUDE.md` — to your machine, stack, and databases.

## Maintenance

After ANY registry edit: `python3 ~/.claude/tools/lint_registry.py`.
Registry drift checks are manual (there is no scheduled ritual): re-run the lint
after edits, and `bash ~/.claude/tools/check_coverage.sh` when project wiring
changes.
