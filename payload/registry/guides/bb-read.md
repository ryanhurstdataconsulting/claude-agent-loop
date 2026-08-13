# Guide — bb-read

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The read side of the blackboard (agent-loop-v2 design spec, Phase 3) — the
only sanctioned way to look up what another agent or an earlier phase left
behind, without every reader inventing its own SQLite query.

## When to deploy (triggers)
Any step that wants a prior step's shared_state hint, an artifact's path by
its id, the event trail for a task, or (once Phase 6 lands) a consensus
vote's current tally.

## Interface (how to invoke)
```
python3 ~/.claude/tools/bb_read.py --table {shared_state,events,consensus_state,workflow_state,artifacts} \
    [--task-id <id>] [--artifact-id <id>] [--json]
```
`--artifact-id` only applies to `--table artifacts`. Default output is one
JSON line per row; `--json` returns the whole result as one array.

## Composition (pairs with / hands off to)
The read counterpart to `bb-write`; `bb-gc` trims what this can see over
time.

## Build & maintenance notes
Lives at `~/.claude/tools/bb_read.py`; exposes a reusable `fetch()` function,
not just a CLI, for any future in-process caller.
