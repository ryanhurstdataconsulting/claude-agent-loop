# Guide — explain-code

**Category:** skill
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Produces visual, analogy-driven explanations of how existing code works,
for onboarding or teaching.

## When to deploy (triggers)
A user asks "how does this work?", or an agent needs to teach a codebase
section with diagrams rather than a dry read-through.

## Interface (how to invoke)
`Skill(explain-code)`.

## Composition (pairs with / hands off to)
Pairs with `excalidraw-diagram` when the explanation benefits from an
architecture or data-flow diagram rather than prose alone.

## Build & maintenance notes
Lives at `~/.claude/skills/explain-code/`.
