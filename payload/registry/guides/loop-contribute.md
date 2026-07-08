# Guide — loop-contribute

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The package's feedback loop: fleet installs build local resources and record
local metrics; when a machine "plugs in," improvements that clear every
publication gate are packaged upstream so the whole fleet benefits. This tool
is that pipeline: detect local (non-symlink) skills/tools/agents → gate each
(classify_visibility must say GENERIC; secret/PII scrub must pass; grammar gate
on markdown) → measure impact from the metrics store → write a summary (what
changed · how it improved the local environment · agent-performance delta ·
how to implement it into the main project) → commit in a temporary worktree →
**auto-push to a `contrib/<date>-<slug>` branch** and print the branch link.

## When to deploy (triggers)
- SessionStart surfaces a one-line nudge when gate-cleared contributions are
  pending (the nudge itself never pushes).
- At digest review, or on demand any time.

## Interface (how to invoke)
Push: `python3 ~/.claude/tools/loop_contribute.py`
Nudge only: `python3 ~/.claude/tools/loop_contribute.py --nudge`
Kill switch: `AGENT_LOOP_CONTRIBUTE=0`. Flags for non-default layouts:
`--claude-dir --repo --markers-file --metrics-dir --state-file`.

## Composition (pairs with / hands off to)
- Consumes the gates: `secret-pii-scrub-gate`, `machine-prose-grammar-gate`,
  and `classify_visibility` (default-deny — CLIENT/UNSURE never leave the
  machine).
- Reads the metrics store the harvest hooks write; joins self-scores by
  task_id.
- Pairs with `loop-digest` (review altitude) and the auto-update hook (the
  fleet pulls merged contributions on its next session).

## Build & maintenance notes
Lives at `payload/tools/loop_contribute.py`. Pushes `contrib/*` branches only —
never `main`; merge is a human PR decision. Packaging happens in a temporary
`git worktree`, so the framework checkout is never disturbed;
`learning/contributed.json` dedups re-contribution. Tests:
`payload/tools/tests/test_loop_contribute.py` (GENERIC pushes with MANIFEST
line + four-section summary; CLIENT withheld; idempotent rerun; nudge never
pushes; symlinked framework content ignored; `main` untouched).
