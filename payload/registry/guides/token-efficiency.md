# Guide — token-efficiency

**Category:** superpower
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Requested 2026-07-06 alongside a token-optimization proposal that asked the agent
to browse four third-party repos and rewrite its own execution loop from their
contents — including rules that would have broken standing protocol (truncating
test output to an exit code, refusing to read files). This resource captures the
*safe* kernel of that request: the genuine token levers, grounded in the
first-party Claude Platform features, with the correctness floor made explicit so
efficiency never overrides the commit protocol's evidence requirement. It also
codifies what was already implicit and being re-derived per session (targeted
reads, subagent file-handoff, model/effort routing). Extended 2026-07-08 after a
plan-authoring session thrashed through five compactions: the verbatim recon for a
large implementation plan was front-loaded into the main window, so each compaction
summarized the reads away before any plan bytes reached disk. Lever 6 ("author
large artifacts disk-first") captures the fix — delegate the verbatim reads into
throwaway subagent/Workflow contexts that write fragments to disk, then assemble
from those files.

## When to deploy (triggers)
Starting a long-horizon, high-volume, or multi-file task; before dispatching a
fleet of subagents; any session expected to run past compaction; or an explicit
"keep this cheap" / token-budget instruction. Keyword shortcuts in `TRIGGERS.md`.

## Interface (how to invoke)
Skill: `Skill(token-efficiency)`. The always-on baseline (targeted reads, delegate
bulk, file-handoff, reference-don't-repaste, and the never-trade floor) is also
written into `~/.claude/CLAUDE.md` § "Token & Context Discipline" so it applies
every session without an explicit invocation; invoke the skill for the full
playbook and the platform-mechanism reference table.

## Composition (pairs with / hands off to)
Layers under `resource-loop` — its ROUTE step is this skill's model/effort
lever. Pairs with `subagent-driven-development` (file-handoff), `background-build-watch`
(poll a log once), and the machine-global commit protocol, which sets the
verbatim-evidence floor this skill must never cross.

## Build & maintenance notes
Skill lives at `~/.claude/skills/token-efficiency/SKILL.md`; this guide is its
bijective index entry (category `superpower`, under "Superpowers (process)").
The "Already engaged" list names live mechanisms (compaction 150k, Tool Search,
ROUTE tiering) — refresh it if those change. No executable test; validated by
`lint_registry.py` (index ↔ guide bijection) and the grammar gate over its prose.
