# Guide — distill-transcripts

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Extracts redacted user/assistant text from session JSONLs, so
mining/audit work doesn't have to hand-parse raw transcripts.

## When to deploy (triggers)
Any resource-mining pass over prior session history, or a request to
review what an agent said or did across sessions without exposing
secrets.

## Interface (how to invoke)
`python3 ~/.claude/tools/distill_transcripts.py --out-dir <dir>
[--projects-root <dir>] [--prefix <name-prefix>]`.

## Composition (pairs with / hands off to)
Feeds the resource-mining reports that justify new registry candidates.

## Build & maintenance notes
Lives at `~/.claude/tools/distill_transcripts.py`; built in Phase 1 of
this build. Redaction rules cover PEM blocks and similar secret shapes —
verify output before sharing.
