# Guide — environment-bootstrap

**Category:** skill
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The starter ships a generic resource set; this skill turns it into a
configuration fitted to the user's actual machine, stack, and databases — the
step that makes a one-size bundle useful to any individual. It is the first thing
a new user runs after install, and it is re-runnable as the setup evolves.

## When to deploy (triggers)
First run after install; a new machine; a new database, cloud account, or
language entering the user's workflow; or an explicit "set me up" / "reconfigure
my environment".

## Interface (how to invoke)
Skill: `Skill(environment-bootstrap)`. Runs EXPLORE → INTERVIEW → TAILOR →
VERIFY. Re-runnable; updates the config in place.

## Composition (pairs with / hands off to)
Uses `env-tooling-preflight` and `git-safety-preflight` (Phase 4 verification),
`lint-registry` (after registry edits), and `secret-pii-scrub-gate` (before any
handoff). Feeds the `resource-loop` — it tailors the registry the loop reads and
personalizes the directives in `~/.claude/CLAUDE.md`.

## Build & maintenance notes
Skill at `~/.claude/skills/environment-bootstrap/SKILL.md`. No executable test;
validated by `lint_registry.py` (index ↔ guide bijection) and the grammar gate.
Keep the EXPLORE probes portable (macOS bash 3.2) and degrade gracefully when a
CLI is absent — a missing `gcloud` is a "not installed" finding, not an error.
