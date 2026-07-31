# Guide — make-brief

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
`harvest_metrics.py` states the problem in its own source comment: *"Subagents
rarely announce."* Asking a dispatched agent to remember a reporting protocol
does not work — it complied on 21.7% of tasks. A brief that carries the
identifiers and the return schema does not rely on memory: the agent cannot
produce a valid result without also producing its own attribution.

## When to deploy (triggers)
- Before every subagent dispatch that belongs to a work order.
- Not for an inline step the main thread does itself — there is no part to
  brief.

## Interface (how to invoke)
```
make_brief.py <plan-id> <part-id> [--state-dir DIR]
```
Prints the full subagent prompt to stdout, ready to paste into an Agent
dispatch. Exits 2 with a stated reason when the plan or part is unknown, or
when the part has not been assigned yet.

## Composition (pairs with / hands off to)
- Consumes a work order that `plan-task --assign` has already routed.
- The rendered brief demands a JSON return whose fields feed
  `plan_task.py --log`, which in turn feeds `assess-task`.
- Carries two machine-global rules into every dispatch: the grammar rule from
  `~/.claude/CLAUDE.md` §1, and evidence-before-assertions.

## Build & maintenance notes
Lives at `payload/tools/make_brief.py`. Tests:
`payload/tools/tests/test_make_brief.py` (16 cases), including one that parses
the embedded schema block as real JSON so the template cannot drift into
something an agent would have to guess at. The brief is a single template
string — edit `BRIEF_TEMPLATE` and `RETURN_SCHEMA` together, and keep the
`ok` field's meaning intact: a return without an explicit `ok: true` is
recorded as a failure, never as a success.
