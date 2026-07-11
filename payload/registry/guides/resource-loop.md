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

## Subagent brief footer (H4 fix, 2026-07-10)
Metrics show subagents overwhelmingly "proceeding bare" because dispatch
briefs omit the loop contract. Append this footer verbatim to every subagent
and workflow-agent brief (it costs three lines and makes the task visible to
the loop):

> Resource Loop: before starting, print one line — either
> `Resource Loop — deploying: <registry id> (<category>) — <reason>` or
> `Resource Loop — no registry match; proceeding bare.` At task close, score
> yourself: `python3 ~/.claude/tools/score_task.py --task-id agent-<your id>
> --scale outcome=<great|good|bad|horrible> --scale evidence=<proven|partial|asserted>`.

## Build & maintenance notes
Skill lives at `~/.claude/skills/resource-loop/SKILL.md`; the injection hook
lives at `~/.claude/hooks/inject-resource-loop.sh`.
