# Guide — bb-gc

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The blackboard (agent-loop-v2 design spec, Phase 3) has no daemon and no
automatic expiry — without a trim job, `shared_state`/`events`/`artifacts`
grow forever. `bb_gc.py` applies the spec's stated retention windows.

## When to deploy (triggers)
Runs unattended, nightly, via
`payload/launchd/com.hdc.claude-agent-loop.blackboard-gc.plist` — not
something a session invokes directly, though `--dry-run` is safe to run by
hand to preview what a real run would delete.

## Interface (how to invoke)
`python3 ~/.claude/tools/bb_gc.py [--db <path>] [--dry-run]` — 30-day trim on
`shared_state`/`artifacts`, 90-day on `events`. `consensus_state` and
`workflow_state` are never trimmed by this tool (deliberate — see the
module's own docstring before changing that).

## Composition (pairs with / hands off to)
Operates on the same `blackboard.db` that `bb-write`/`bb-read` do; shares no
code with `audit-dispatch`'s nightly sweep (different launchd job, different
concern).

## Build & maintenance notes
Lives at `~/.claude/tools/bb_gc.py`. Installed the same manual way the other
3 launchd plists in this repo are — copy to `~/Library/LaunchAgents/`,
`launchctl load` — there is no installer script.
