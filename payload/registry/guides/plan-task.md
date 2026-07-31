# Guide — plan-task

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Attribution used to depend on the model emitting an exactly formatted ANNOUNCE
line that a harvester later scraped back out of the transcript. Measured over
two months, that line appeared on 21.7% of subagent tasks, and precise
attribution survived on 15.4% — so the heuristics engine spent most of its life
correctly refusing to act on coarse evidence. The work order replaces the prose
contract with a JSON artifact a tool writes, which makes attribution precise by
construction. The same tool adds the DECOMPOSE stage, which the loop never had:
`route_role.py` mapped one whole task to one role, so a four-part task got one
role and one score.

## When to deploy (triggers)
- At the start of any task large enough to have parts.
- Whenever a subagent finishes, to record its structured return
  (`--log`).
- Never for a trivial single-step task — a work order for a one-line fix costs
  more than it measures.

## Interface (how to invoke)
```
plan_task.py --new "<task>"                    # one part; refuses creative tasks
plan_task.py --from-plan <doc> --task "<task>" # one part per "### Task N:" heading
plan_task.py --assign <plan-id>                # route every open part
plan_task.py --log <plan-id> --part <id> --json <file>
plan_task.py --show <plan-id>
```
Work orders live at `~/.claude/metrics/state/workorders/<plan-id>.json`.
Exit 0 on success, 3 on a refused creative task, 2 on any other failure. Unlike
the loop's hooks, this tool does **not** fail open.

## Composition (pairs with / hands off to)
- **The superpowers gate is the point of `--new`.** A task scoring at or above
  the creativity threshold is refused and told to run
  `Skill(superpowers:brainstorming)` then `Skill(superpowers:writing-plans)`
  first; the resulting plan document feeds `--from-plan`. `--force` overrides
  and records `"forced": true`, so the override is visible in the data.
- Imports `route_role.route()` directly and calls it per part.
- Hands each assigned part to `make-brief`, and the finished work order to
  `assess-task`.

## Build & maintenance notes
Lives at `payload/tools/plan_task.py`. Tests:
`payload/tools/tests/test_plan_task.py` (41 cases, hermetic — role fixtures and
state directories are built per-test in tempdirs, never the live `~/.claude`
tree). Creativity detection and model-tier selection are keyword arithmetic in
the style of `route_role.py`: if a real task misclassifies, edit
`CREATIVE_STRONG`/`CREATIVE_WEAK` or `MODEL_BUCKETS` and re-run the tests. That
is a data edit, not a code edit.
