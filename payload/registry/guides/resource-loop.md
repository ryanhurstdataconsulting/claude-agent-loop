# Guide — resource-loop

**Category:** superpower
**Scope:** machine-global
**Status:** candidate

## Why this exists (evidence)
Anchors every session to a closed MATCH → ANNOUNCE → ROUTE → EXECUTE → SCORE →
LEARN discipline so the right registry resource gets deployed — and scored, so
the loop learns — instead of re-derived from scratch.

## When to deploy (triggers)
Start of every Claude Code session, before the first substantive task — match
the task shape against `REGISTRY.md`, announce the deployed resource, route any
subagents, execute, then score the result so the loop can learn. Filing a
candidate stub for a recurring unmet need (GAP) is a side behavior, not a
mainline step.

## Interface (how to invoke)
Runs via the `SessionStart` hook `~/.claude/hooks/inject-resource-loop.sh`,
which injects the registry index inside `<resource-loop>` tags; the
`Skill(resource-loop)` skill governs the MATCH → ANNOUNCE → ROUTE → EXECUTE →
SCORE → LEARN sequence (with GAP as a side behavior). Keyword and file-glob
shortcuts for MATCH live in
`~/.claude/registry/TRIGGERS.md`. If the injected block is absent (hook
failure or a subagent context), read `~/.claude/registry/REGISTRY.md`
directly at session start.

## Composition (pairs with / hands off to)
Feeds every other registry row — it is the dispatcher, not a peer. Pairs
with `lint-registry` (keeps the index it reads valid) and
`check-coverage` / `run-canaries` (verify the loop actually fires).

## Build & maintenance notes
Skill lives at `~/.claude/skills/resource-loop/SKILL.md`; the injection hook
lives at `~/.claude/hooks/inject-resource-loop.sh`.
