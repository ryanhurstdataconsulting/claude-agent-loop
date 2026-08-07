# Guide — plan-task

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Attribution used to depend on the model emitting an exactly formatted ANNOUNCE
line that a harvester later scraped back out of the transcript. Measured over
two months, that line appeared on 21.7% of subagent tasks, and precise
attribution survived on 15.4% — so the heuristics engine spent most of its life
correctly refusing to act on coarse evidence. The plan replaces the prose
contract with a JSON artifact a tool writes, which makes attribution precise by
construction. The same tool adds the DECOMPOSE stage, which the loop never had:
`route_role.py` mapped one whole task to one role, so a four-part task got one
role and one score.

Briefing used to be a separate handoff to `make_brief.py`, which existed
because `harvest_metrics.py` states the problem in its own source comment:
*"Subagents rarely announce."* Asking a dispatched agent to remember a
reporting protocol does not work — it complied on 21.7% of tasks. A brief that
carries the identifiers and the return schema does not rely on memory: the
agent cannot produce a valid result without also producing its own
attribution. That generator is now `render_brief()` inside this tool — DECOMPOSE,
ASSIGN, and BRIEF happen synchronously in one `--new`/`--from-plan` call, so a
caller never waits through a separate "assigned" stage before dispatching.

Verdict computation used to be a separate handoff to `assess_task.py`, which
existed because the loop's assessment channel was a subjective self-score,
recorded on 74 of 1,596 subagent tasks — 4.6% — and written by the same agent
that did the work, while the metrics store already carried a git branch on
100% of tasks and test results on 64%, and nothing read either. That verdict
logic now lives in `score_task.py`'s `auto_assess()` (invoke as
`score_task.py --auto <task_id>`) — see that tool's own docs for the verdict
truth table.

## When to deploy (triggers)
- At the start of any task large enough to have parts.
- Whenever a subagent finishes, to record its structured return (`--record`).
- Never for a trivial single-step task — a plan for a one-line fix costs
  more than it measures.

## Interface (how to invoke)
```
plan_task.py --new "<task>"                    # one step, assigned + briefed
plan_task.py --from-plan <doc> --task "<task>" # one step per "### Task N:" heading
plan_task.py --assign <task_id>                # re-route every open step
plan_task.py --record <task_id> --step <id> --json <file-or-json>
plan_task.py --show <task_id>
```
`--json` accepts **either** a path to a file holding the subagent's return
JSON **or** the JSON text itself. Prefer the file: a real return's
`summary`/`evidence` prose carries quotes, newlines, and backticks, which is
exactly what a shell-quoted inline argument mangles.

Plans live at `~/.claude/plans/<YYYY-MM-DD>/<task_id>.json`. That directory is
**shared**, not this tool's alone: human-authored plan documents (the `.md`
files `superpowers:writing-plans` produces) sit at the top level, while this
tool's machine-generated plan artifacts live one level down, under a
`<YYYY-MM-DD>/` subdirectory. Anything that sweeps or cleans the directory has
to respect both — `loop_close.ready_plans()` globs `*/*.json` precisely so the
top-level documents are never picked up as plans.

There is no creativity gate — every task decomposes, nothing is refused. Exit 0
on success, 2 on failure (bad args, unknown plan/step, a `--json` argument that
is neither a readable file nor valid JSON). Unlike the loop's hooks, this tool
does **not** fail open.

## Composition (pairs with / hands off to)
- Creative work is still worth designing before it's decomposed — run
  `Skill(superpowers:brainstorming)` then `Skill(superpowers:writing-plans)`
  first for ambiguous or multi-agent work, then feed the resulting plan
  document to `--from-plan`. This is guidance now, not a refusal the tool
  enforces.
- Imports `route_role.route()` directly and calls it per step, and renders
  each step's dispatch prompt itself (folded in from the former
  `make_brief.py`) — no separate BRIEF call.
- Hands each recorded step to `score_task.py --auto`, which folds in what
  `assess_task.py` used to do.

## Build & maintenance notes
Lives at `payload/tools/plan_task.py`. Tests:
`payload/tools/tests/test_plan_task.py` (45 cases, hermetic — role fixtures and
state directories are built per-test in tempdirs, never the live `~/.claude`
tree). Model-tier selection (`model_for()`) is keyword arithmetic against
`MODEL_BUCKETS`, in the style of `route_role.py`: if a real task misclassifies,
edit `MODEL_BUCKETS` and re-run the tests. That is a data edit, not a code
edit.
