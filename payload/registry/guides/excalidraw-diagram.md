# Guide — excalidraw-diagram

**Category:** skill
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Generates Excalidraw JSON diagrams for architecture, data-flow, and
onboarding visualizations.

## When to deploy (triggers)
A request to "diagram this project," visualize a data pipeline, or
produce a client-facing architecture overview.

## Interface (how to invoke)
`Skill(excalidraw-diagram)`.

## Composition (pairs with / hands off to)
Pairs with `explain-code` (narrative context for the diagram) and
`technical-pm` (architecture diagrams for sprint/ticket briefs).

## Build & maintenance notes
Lives at `~/.claude/skills/excalidraw-diagram/`; a superseded
`excalidraw-diagram.bak/` variant also exists — prefer the non-`.bak`
skill.
