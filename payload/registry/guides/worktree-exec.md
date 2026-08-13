# Guide — worktree-exec

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
A plan step (agent-loop-v2 design spec, Phase 1 schema) can be marked
`"worktree": true` to run in isolation from the parent branch — Phase 4 of
that same spec. `worktree_exec.py` is the create/merge lifecycle for that
isolation; it is NOT `loop_autocommit.sh` (that tool refuses any repo other
than this framework repo and `~/.claude` — see its own routing logic).

## When to deploy (triggers)
Before dispatching an EXECUTE step whose plan JSON has `"worktree": true`
for that step — run `--create` first, dispatch the step's brief inside the
printed worktree path, then run `--merge` only after that step's return
records `ok: true` (or pass `--force` to override deliberately).

## Interface (how to invoke)
```
python3 ~/.claude/tools/worktree_exec.py --create --task-id <id> --step <id> --repo <path>
python3 ~/.claude/tools/worktree_exec.py --merge --task-id <id> --step <id> [--force]
```

## Composition (pairs with / hands off to)
Reads/writes `plan-task`'s own plan file (`load()`/`save()`) and the
`bb-write`/`bb-read` blackboard's `workflow_state` table — the parent
branch a worktree came from is a blackboard checkpoint, not a new plan
schema field.

## Build & maintenance notes
Lives at `~/.claude/tools/worktree_exec.py`. A real merge conflict always
aborts and preserves the worktree for manual resolution, regardless of
`--force` — `--force` only overrides the `return.ok` check, never a
conflict.
