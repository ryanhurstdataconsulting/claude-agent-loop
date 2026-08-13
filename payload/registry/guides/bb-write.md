# Guide — bb-write

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The blackboard (agent-loop-v2 design spec, Phase 3) is cross-agent shared
state — hints, results, artifact IDs, phase-transition events, consensus
votes, resumable checkpoints — that no single JSON file (like a plan's own
`plans/<id>.json`) is the right shape for. `bb_write.py` is the only
sanctioned write path into it.

## When to deploy (triggers)
Any EXECUTE step that needs to leave a result, hint, or checkpoint another
step or a later session can read back; any phase transition worth an audit
trail; any gated action needing a Phase 6 consensus vote recorded (once
Phase 6 lands).

## Interface (how to invoke)
```
python3 ~/.claude/tools/bb_write.py --table {shared_state,events,consensus_state,workflow_state} \
    --task-id <id> --phase <MATCH|PLAN|ANNOUNCE|ROUTE|EXECUTE|SCORE|MERGE|LEARN> \
    [--agent-id <id>] (--payload '<json>' | --payload-file <path>)

python3 ~/.claude/tools/bb_write.py --table artifacts --artifact-id <id> \
    --task-id <id> --phase <phase> [--agent-id <id>] --path <path> [--sha256 <hex>]
```

## Composition (pairs with / hands off to)
Pairs with `bb-read` (the read side of the same store) and `bb-gc` (the
retention trim). Sits alongside, not instead of, `plan-task`'s own
`plans/<id>.json` — the plan file is a task's own record; the blackboard is
what tasks share with each other.

## Build & maintenance notes
Lives at `~/.claude/tools/bb_write.py`, backed by `~/.claude/tools/bb_common.py`
(schema + connection) and `~/.claude/state/blackboard.db` (WAL-mode SQLite,
single file, no daemon). Exit 0 success, 2 usage error.
