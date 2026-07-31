# Work-Order Pipeline — Design

**Date:** 2026-07-30
**Status:** Approved
**Supersedes:** nothing. Extends the `MATCH → ANNOUNCE → ROUTE → EXECUTE → SCORE → LEARN`
loop documented in `ARCHITECTURE.md`.

---

## Problem

The loop measures *process compliance* and collects it by regex-scraping prose
out of session transcripts. Two months of `~/.claude/metrics/` (3,847 records)
show what that costs:

| Signal | Coverage | Consumed by |
|---|---|---|
| `announce_found` true | 346 / 1,596 tasks (21.7%) | every heuristic |
| Precise attribution (`resources_source == "task"` **and** non-empty `resources_deployed`) | 246 / 1,596 (15.4%) | H1, H7 |
| `kind:"score"` records | 74 against 1,596 subagent tasks (4.6%) | LEARN |
| `kind:"learn"` records | 38 total; 29 are H4 "bare-match-streak" | — |
| `git_branch` | **1,596 / 1,596 (100%)** | **nothing** |
| `tests: {passed, failed}` | **1,026 / 1,596 (64%)** | **nothing** |
| `tool_errors` | **586 tasks non-zero** | H1 only |

`harvest_metrics.py:542` states the root cause in its own comment: *"Subagents
rarely announce."* When they do not, the harvester falls back to
`resources_source: "session-backfill"`, and `heuristics_eval.py` correctly
downgrades `improve-now` to `theme-note` on coarse evidence. The learning layer
is not broken — it is starved, and it is refusing to act on blind data. The
16 unprocessed themes at session start are the visible symptom.

Two structural gaps compound it:

1. **No decomposition step exists.** `route_role.py` maps one task string to one
   role. A task with four distinct parts gets one role and one score.
2. **Improvements target the wrong artifact.** `improve-now` patches a
   machine-global skill. The highest-value learning artifact on the machine —
   the per-project `.claude/SUBAGENTS.md`, whose every row cites the specific
   past failure that justifies it — is written only by hand.

## Goal

Make each stage of the task lifecycle leave a **machine-readable artifact**, so
attribution is precise by construction rather than by the model remembering a
prose protocol. Then repoint LEARN at objective evidence that already exists.

Non-goal: replacing the existing loop. `route_role.py`, `heuristics_eval.py`,
`harvest_metrics.py`, `loop_autocommit.sh`, and `score_task.py` are all reused.

## Architecture

One JSON **work order** per task carries the loop state. Every stage reads it
and writes back to it.

```
TASK
 │
 ├─ 1 DECOMPOSE  plan_task.py --new / --from-plan  ──► workorders/<plan-id>.json
 │                (creative task ⇒ brainstorming + writing-plans first)
 ├─ 2 ASSIGN     plan_task.py --assign             ──► part.role, part.skills, part.model
 ├─ 3 BRIEF      make_brief.py                     ──► the dispatched prompt
 ├─ 4 EXECUTE    subagent returns structured log   ──► part.log
 ├─ 5 ASSESS     assess_task.py                    ──► part.evidence (objective)
 │                                                     part.score    (subjective, tiebreak)
 └─ 6 LEARN      heuristics_eval.py on the objective channel
                  ├─ global fix  → skill / role doc via loop_autocommit.sh
                  └─ local fix   → project .claude/SUBAGENTS.md row
```

### Storage

`~/.claude/metrics/state/workorders/<plan-id>.json`. The `metrics/state/`
directory already exists and is already outside the monthly shard rotation.

Plan id: `wo-<YYYYMMDD>-<task-slug>-<6-hex>`, where the hex is a SHA-256 prefix
of the task text plus creation timestamp. Deterministic within a run, unique
across runs, and sortable by date.

### Work-order schema (schema 1)

```json
{
  "schema": 1,
  "plan_id": "wo-20260730-rearchitect-the-loop-a1b2c3",
  "task": "<the original task text>",
  "source": "direct" | "brainstorm" | "plan",
  "plan_doc": "<path to the writing-plans doc>" | null,
  "created": "2026-07-30T18:00:00Z",
  "project": "<slugified cwd>",
  "git_branch": "<branch at creation>",
  "parts": [
    {
      "part_id": "p1",
      "goal": "<one-line statement of this part>",
      "status": "pending" | "assigned" | "done" | "failed",
      "role": "data-engineer" | null,
      "role_score": 7,
      "skills": ["..."],
      "model": "opus" | "sonnet" | "haiku" | "session",
      "agent_task_id": "agent-..." | null,
      "log": {...} | null,
      "evidence": {...} | null,
      "score": {...} | null
    }
  ]
}
```

### Stage 1 — DECOMPOSE, and the superpowers gate

`plan_task.py --new "<task>"` refuses to create a work order for a task that
looks creative unless the caller states where the decomposition came from.
Creativity is detected the same way roles are routed: keyword arithmetic over a
fixed phrase list (`build`, `design`, `add a feature`, `redesign`, `new skill`,
`architecture`, …), with no model judgment. Behaviour:

| Task shape | `--source direct` | Required path |
|---|---|---|
| Mechanical (lint fix, extraction, sweep) | allowed | — |
| Creative | **refused, exit 3** | `Skill(superpowers:brainstorming)` → `Skill(superpowers:writing-plans)` → `plan_task.py --from-plan <doc>` |

The refusal prints the exact two skill invocations to run. `--force` overrides
it and records `"source": "direct", "forced": true` on the work order, so an
override is visible in the data rather than silent.

`--from-plan <path>` parses a writing-plans document, taking every
`### Task <n>: <title>` heading as one part. That heading shape is the existing
convention in `docs/superpowers/plans/` (verified against
`2026-07-17-usage-budget-hook.md`, which uses `### Task 1:` through
`### Task 10:`). A plan with no such headings is an error, not an empty work
order.

### Stage 2 — ASSIGN

`plan_task.py --assign <plan-id>` runs the existing `route_role.route()` against
**each part's goal**, not the whole task, and writes `role`, `role_score`, and
the role's declared `skills` onto the part. A part below the confidence floor
gets `role: "generalist"` with empty skills — stated, never guessed.

Model tier is assigned by the same keyword-arithmetic method against the ROUTE
table already in the resource-loop skill:

| Bucket | Phrases | Model |
|---|---|---|
| Planning / synthesis | plan, architecture, review, synthesize, evaluate | `session` |
| Creation | write, build, implement, author, design, draft, create | `opus` |
| Mechanical | extract, sweep, lint, rename, probe, list, count, verify | `sonnet` |

Ties break toward the more capable tier. No match defaults to `session`.

### Stage 3 — BRIEF

`make_brief.py <plan-id> <part-id>` renders the subagent prompt to stdout. The
brief embeds, non-optionally:

- the `plan_id` and `part_id` the agent must echo back;
- the part goal;
- the role's declared skill shortlist;
- the machine-global grammar rule (per `~/.claude/CLAUDE.md` §1);
- the required return schema, so the agent's final text is a JSON object rather
  than prose.

This is what replaces the ANNOUNCE string contract. The agent does not have to
remember to announce; it cannot return a valid result without the identifiers.

### Stage 4 — EXECUTE

`plan_task.py --log <plan-id> <part-id> --json <file>` records the returned
object on the part and flips `status` to `done` or `failed`. Attribution is now
a write, not a scrape.

### Stage 5 — ASSESS, two channels

`assess_task.py <plan-id>` builds `part.evidence` with **no model involvement**:

| Field | Source |
|---|---|
| `tests_passed`, `tests_failed`, `tests_detected` | the part's `agent-<id>` task record in the metrics shard |
| `tool_errors`, `error_rate`, `turns`, `duration_s` | same record |
| `commits` | `git log` on the work order's branch between part start and end |
| `reverts` | commits whose subject starts `Revert ` in that window |
| `followup_fixes` | commits touching the same paths within `--followup-hours` (default 24) whose subject starts `fix` |

It then computes a per-part `verdict` — `clean`, `dirty`, or `unknown` — from
those numbers alone. `clean` requires: no failed tests, no reverts, and
`error_rate` at or below 0.25 (the threshold H1 already uses). `unknown` is
returned when no objective signal was found, and is never treated as success.

The subjective `score_task.py` value is retained but demoted: it appears on the
part as `score` and is used only to break a `dirty`/`unknown` tie.

### Stage 6 — LEARN

`heuristics_eval.py` gains a `--from-workorder <plan-id>` mode that feeds it the
objective channel. Because every part carries a precise `role` + `skills` list
written by a tool, `resources_source` is `"workorder"` — a third precise source
alongside `"task"` — so H1 and H7 stop being downgraded for lack of precise
rows.

Improvement targets split:

- **global** — the implicated skill or role doc, committed through
  `loop_autocommit.sh` exactly as today. Gates unchanged.
- **local** — a row appended to the current project's `.claude/SUBAGENTS.md`,
  citing the plan id and the objective verdict that triggered it. This path
  writes inside a client project, so it is **proposal-only**: `assess_task.py`
  emits the row to stdout and the agent asks before writing. Client-project
  content never goes near `loop_contribute.py`.

## Testing

Each tool gets a `test_<tool>.py` under `payload/tools/tests/`, runnable by the
existing `run_all.sh`. Coverage required per tool:

- `plan_task.py` — creative-task refusal (exit 3), `--force` override recorded,
  `--from-plan` heading parse, plan with no task headings errors, plan-id
  determinism, `--assign` per-part routing, `--log` status transitions,
  malformed work order fails closed.
- `make_brief.py` — identifiers present in output, skills rendered, unknown
  part id errors, generalist role renders without a skill list.
- `assess_task.py` — verdict truth table (`clean` / `dirty` / `unknown`), a
  failed test forces `dirty`, missing metrics record yields `unknown` and not
  `clean`, `SUBAGENTS.md` row is emitted to stdout and never written to disk.

## Constraints

- Python 3 stdlib only, matching every existing tool.
- macOS bash 3.2 portable for any shell surface.
- No `hooks/` or `settings*.json` changes in this slice — `loop_autocommit.sh`
  refuses that lane by design, and nothing here needs it.
- Every tool exits 0 on success, non-zero with a stated reason on failure. These
  are called deliberately, not from a hook, so they do **not** fail open.

## Out of scope

- Hook-level enforcement (a `SubagentStop` hook rejecting an unlogged part).
  Deferred until the log format has run against real traffic.
- The compaction problem: 1,860 compactions against 1,596 tasks, at a mean of
  22.2 turns per task. Real, but a separate concern.
- A `framework` role. `route_role.py` returns `generalist` for tasks about the
  loop itself, because no role's `routes:` phrases cover it.
