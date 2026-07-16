# H5 route-cost-outlier Evaluator — Design Spec

**Date:** 2026-07-16
**Status:** Approved (Ryan picked "Approach b" after the three-approach proposal)
**Branch:** `feat/h5-route-cost-evaluator`

## Problem

H5 (route-cost-outlier) is the last unevaluable rule in the rulebook: "a task
classified as mechanical work is routed to the Opus model tier" → theme-note.
The repo seed `payload/learning/HEURISTICS.md` parks it under
`## Planned (not yet computable)` because the metrics schema carries neither a
task-shape nor a route-tier field. Meanwhile the LIVE rulebook on this machine
(`~/.claude/learning/HEURISTICS.md`) is an older revision with H5 ACTIVE in the
main body, so `lint_heuristics.py` currently FAILS against it: H5 is ACTIVE but
absent from `heuristics_eval.EVALUABLE_RULES`. The Resource Loop's LEARN step
therefore has a standing blind spot for routing waste (mechanical tasks burning
Opus tokens).

## Chosen approach (Approach B)

Derive the **route tier objectively** from data the harvester already records —
each task record's `models` field (model id → token usage) — and add only one
new, optional input: a `--task-shape {planning,creation,mechanical}` flag on
`score_task.py`. No `--route-tier` flag (this consciously revises the earlier
"route-tier field at ANNOUNCE time" note; Ryan approved the revision by
picking B).

Rejected alternatives:
- **A — both flags on score_task.py:** `--route-tier` duplicates information
  already in the task record and can contradict it; a self-reported tier is
  strictly worse evidence than the recorded model usage.
- **C — infer shape too (no new flags):** shape inference from prompts or
  resource names is guesswork; a wrong "mechanical" label produces false
  theme-notes. Shape is a human judgment; it stays a scoring-time input.

## Data model

### `score_task.py --task-shape` (new optional flag)

- `choices=["planning", "creation", "mechanical"]` (argparse enforces).
- When passed, the score record gains `"task_shape": "<value>"`.
- When omitted, the key is **absent** (no junk `"unknown"` values in shards);
  the evaluator treats a missing or unrecognized value as unknown, and unknown
  never counts toward — or against — H5.

### Route-tier derivation (evaluator-side, per task record)

`_route_tier(task_record) -> str` in `heuristics_eval.py`:

1. Read `task_record.get("models") or {}` — a dict of model id → usage dict.
2. Pick the **dominant** model id: the one with the largest `out` token count
   (missing/non-numeric `out` → 0); ties break lexicographically by model id
   so the result is deterministic. Empty dict → `"unknown"`.
3. Map the dominant id by substring, first match wins in this order:
   `"opus"` → `"opus"`, `"sonnet"` → `"sonnet"`, `"haiku"` → `"haiku"`,
   `"fable"` or `"mythos"` → `"session"`, else `"unknown"`.
4. Only `"opus"` counts as an H5 hit. `"session"` (a subagent inheriting the
   session model) is deliberately NOT an outlier: the Resource Loop's ROUTE
   table sends planning work to the session model, and the session model is
   not a per-dispatch routing decision.

## Evaluator

`_eval_route_cost(rule, tasks, scores)` — global scope, mirroring
`_eval_rework_signal` (the H7 score-joined-window pattern):

1. `window, explicit_min = parse_window(rule)`; `op, count = parse_threshold(rule)`
   — for the live text: window 10, `(">=", 2.0)`.
2. Population: kind-`task` records (already sorted by `ts_end` in `ctx.tasks`)
   whose joined score record exists **and** carries a known `task_shape`
   (`scores.get(task_id, {}).get("task_shape") in {"planning", "creation",
   "mechanical"}`). Unlabeled or unscored tasks never enter the window —
   the rule reads over tasks the owner actually classified.
3. `win = labeled[-window:]`; `need = _min_samples(window, explicit_min, int(count))`
   (→ 2 for the live text). If `len(win) < need`: no firing.
4. Hits: rows in `win` where the score's `task_shape == "mechanical"` AND
   `_route_tier(task_record) == "opus"`.
5. If `_cmp(op, len(hits), count)`: return the standard firing dict
   (rule/action/scope="global"/metric="mechanical_tasks_routed_to_opus"/
   computed/comparator/threshold/samples/window/min_samples/
   coarse_samples/precise_samples/evidence). Evidence rows come from
   `_ev_row(task_record, "mechanical -> <dominant-model-id>")` for each hit.
6. Dispatch wiring in `evaluate_rule`: `elif hid == "H5": f =
   _eval_route_cost(rule, ctx.tasks, ctx.scores)` — alongside the other
   global rules (H2/H3/H6). Confidence and `_apply_downgrade` then apply
   via the existing post-chain code; H5's THEN is theme-note, so
   `effective_action` stays theme-note.

## Set and comment updates in `heuristics_eval.py`

- `EVALUABLE_RULES` += `"H5"` (lint_heuristics imports this set; adding H5 is
  what makes the live rulebook lint-clean).
- `GLOBAL_TASK` += `"H5"`.
- `DOWNGRADE_RULES` stays `{"H1", "H7"}` — H5 must NOT join it (locked
  decision). Add a one-line comment at the set so it never drifts in:
  downgrade exists for improve-now rules; H5 is theme-note by design.
- Rewrite the scope-sets comment block (currently the lines explaining that H5
  is parked in Planned) to describe H5 as an evaluable global rule whose tier
  is derived from task-record `models`.

## Rulebook seed update (`payload/learning/HEURISTICS.md`)

Move the H5 block out of `## Planned (not yet computable)` into the active
body (after H4, keeping numeric order), with:

- WHEN/WINDOW/THRESHOLD/THEN/CONFIDENCE unchanged (the parsers already handle
  "last 10 tasks" and "2 or more").
- `LAST-REVIEWED: 2026-07-16`.
- NOTE rewritten: route tier is derived from the task record's `models` field
  (dominant model by `out` tokens); task shape comes from
  `score_task.py --task-shape`; tasks without a shape label are ignored.
- If moving H5 leaves the Planned section empty, delete the section header.

The LIVE `~/.claude/learning/HEURISTICS.md` needs **no edit**: its H5 block is
already active, and once `EVALUABLE_RULES` contains "H5" the live lint goes
green. (The tools are symlinks into this repo, so the fix is live on branch
checkout and durable on merge to main.)

## Testing plan

All tests extend the existing suites under `payload/tools/tests/` and run via
`run_all.sh`.

`test_heuristics_eval.py` (new cases):
1. `_route_tier`: dominant-by-`out` selection across two models; opus/sonnet/
   haiku substring mapping; fable → `"session"`; unrecognized id → `"unknown"`;
   empty/missing `models` → `"unknown"`.
2. H5 fires: 10 labeled+scored tasks, 2 mechanical tasks with opus-dominant
   `models` → firing with `computed == 2`, action theme-note, scope global,
   evidence naming both task ids.
3. H5 does not fire: only 1 mechanical+opus hit in the window.
4. Unknown shapes excluded: unscored tasks and scores without `task_shape`
   never enter the window (a shard where only 1 labeled task exists →
   insufficient samples → no firing even if it is mechanical+opus).
5. Mechanical on the session model (fable-dominant) is not a hit.
6. `effective_action` stays theme-note (no downgrade path).

`test_score_task.py` (new cases):
1. `--task-shape mechanical` → record contains `"task_shape": "mechanical"`.
2. Flag omitted → the key is absent from the record.
3. Invalid value (e.g. `--task-shape huge`) → argparse exits non-zero.

`test_lint_heuristics.py` (new/updated case):
- An ACTIVE H5 block lints clean now that "H5" ∈ `EVALUABLE_RULES` (this is
  the regression that pins the live-rulebook fix).

Acceptance evidence:
- `python3 payload/tools/lint_heuristics.py` passes against BOTH the repo seed
  and `~/.claude/learning/HEURISTICS.md`.
- Full `run_all.sh` green (no regressions across all suites).

## Out of scope

- Editing the live `~/.claude/learning/HEURISTICS.md` (not needed).
- Any change to `harvest_metrics.py` (the `models` field already exists).
- Backfilling `task_shape` onto historical score records.
- An H5 improve-now/downgrade path.
