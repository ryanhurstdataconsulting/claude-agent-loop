# Agent Loop v2 — Design

**Date:** 2026-08-06
**Status:** Approved
**Supersedes:** `docs/superpowers/specs/2026-07-30-workorder-pipeline-design.md` — Phase 1
below replaces that spec's DECOMPOSE/ASSIGN/BRIEF/LOG/ASSESS pipeline entirely.
Extends the `MATCH → ANNOUNCE → ROUTE → EXECUTE → SCORE → LEARN` loop in
`ARCHITECTURE.md` with a new PLAN phase and four independent additions.

---

## Problem

An external proposal doc ("Proposed Agent Architecture — claude-agent-loop v2")
recommended four upgrades against 2025-2026 open-source agent-framework
patterns: a LangGraph-style supervisor/PLAN phase, a SQLite blackboard for
cross-agent shared state, parallel git worktrees as the standard EXECUTE
surface, and a 10-category skill taxonomy. A grounding pass against the actual
current state found the headline addition — the PLAN phase — substantially
duplicates the existing work-order pipeline (`plan_task.py` → `make_brief.py`
→ EXECUTE → `plan_task.py --log` → `assess_task.py` → `heuristics_eval.py`),
and that the taxonomy proposal's premise (routing cost from 173 flat skill
files) doesn't hold — REGISTRY.md has 63 rows, and the harness's native skill
listing (not REGISTRY.md) is what resolves most skill matches.

This spec reconciles the proposal with reality: it replaces the work-order
pipeline outright (decided collaboratively, full architectural collapse — see
"Phase 1" below for what that costs and why it was chosen anyway), rescopes
the taxonomy to the 63 REGISTRY rows only, and keeps the blackboard/worktree/
dispatcher additions close to the original proposal since those don't
conflict with anything that already exists.

## Goal

Land seven independently-revertable phases, ordered so nothing later depends
on something earlier being incomplete:

1. PLAN-phase replacement (schema + pipeline rewrite)
2. REGISTRY domain taxonomy
3. Blackboard
4. Worktree EXECUTE support (depends on Phase 1's step schema)
5. Dispatcher generalization
6. Consensus gate (depends on Phase 3's blackboard)
7. GNAP reserved filenames

Non-goals: physically reorganizing `payload/skills/` into category
directories (doesn't speed up native skill matching, which is what actually
resolves most lookups); MCP category-prefix naming (§5.3 of the original
proposal — deferred until the server count passes ~10); GNAP as a working
protocol (§7 below reserves filenames only). GAP behavior (candidate stub
creation for unmet needs, still owner-gated, still fires from MATCH) is
unchanged by any phase here.

## Architecture — phase flow

```
                    ┌──────────────────────────────────────────────┐
                    │  SessionStart hook (unchanged, additive-only) │
                    └──────────────────────┬─────────────────────────┘
                                            │
                                   ┌────────▼────────┐
                                   │  MATCH          │  route_role.py,
                                   │  (domain-first,  │  now domain-filtered
                                   │   Phase 2)       │  against REGISTRY
                                   └────────┬────────┘
                                            │
                                   ┌────────▼────────┐
                                   │  PLAN           │  plan_task.py
                                   │  (Phase 1,      │  writes plans/<id>.json
                                   │   directive,    │  (steps + briefs,
                                   │   not gated)     │  no separate BRIEF stage)
                                   └────────┬────────┘
                                            │
                                   ┌────────▼────────┐
                                   │  ANNOUNCE       │  unchanged
                                   └────────┬────────┘
                                            │
                                   ┌────────▼────────┐
                                   │  ROUTE          │  fan out per step
                                   └────────┬────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    │                       │                       │
              ┌─────▼─────┐           ┌─────▼─────┐           ┌─────▼─────┐
              │ EXECUTE S1│           │ EXECUTE S2│           │ EXECUTE S3│
              │ worktree  │           │ (no       │           │ worktree  │
              │ (Phase 4, │           │  worktree)│           │ (Phase 4) │
              │  opt-in)  │           │           │           │           │
              └─────┬─────┘           └─────┬─────┘           └─────┬─────┘
                    │                       │                       │
                    └───────────────────────┼───────────────────────┘
                                            │
                                   ┌────────▼────────┐
                                   │  SCORE          │  score_task.py --auto
                                   │  (absorbs        │  (Phase 1: ports
                                   │   assess_task)   │  assess_task's verdict
                                   └────────┬────────┘  algorithm)
                                            │
                                   ┌────────▼────────┐
                                   │  MERGE          │  loop_autocommit.sh,
                                   │  (gates 0-5)     │  gates fire once here
                                   └────────┬────────┘
                                            │
                                   ┌────────▼────────┐
                                   │  LEARN          │  unchanged
                                   └─────────────────┘
```

Blackboard (Phase 3) and consensus gate (Phase 6) are cross-cutting — read
from any phase, written from EXECUTE/MERGE.

---

## Phase 1 — PLAN-phase replacement

**Decision context.** Chosen after a collaborative comparison (see session
transcript / commit message for the tradeoff discussion): the existing
pipeline has 9+ direct callers, 7 test files, 3 REGISTRY rows, a dashboard
panel, and 18 live work-order files. Full replacement was chosen anyway,
deliberately accepting that cost, because the goal is a coherent PLAN-centric
architecture rather than a patched hybrid.

**New artifact.** `~/.claude/plans/YYYY-MM-DD/<task_id>.json`. `task_id` keeps
the existing collision-resistant format: `wo-<YYYYMMDD>-<slug>-<sha256:6>`.

```json
{
  "schema": 2,
  "task_id": "wo-20260806-agent-loop-v2-3f9a1c",
  "goal": "...",
  "supervisor_reasoning": "...",
  "steps": [
    {
      "id": "S1",
      "agent": "backend-engineer",
      "depends_on": [],
      "budget_tokens": 40000,
      "worktree": false,
      "brief": "<full ready-to-dispatch prompt, folded in from the old BRIEF stage>",
      "status": "pending",
      "return": null
    }
  ],
  "termination": {"success_when": "...", "max_steps": 8},
  "created": "...",
  "project": "...",
  "git_branch": "..."
}
```

**`plan_task.py`** (same file path, full rewrite). CLI collapses DECOMPOSE +
ASSIGN + BRIEF into one call:

- `--new "<task>"` / `--from-plan <doc> --task "<text>"` — writes the plan
  file with all steps pre-briefed (agent assignment via `route_role.route()`,
  model tier via the existing `model_for()` keyword arithmetic, and a fully
  rendered dispatch prompt per step — no separate `make_brief.py` call).
- `--record <task_id> --step <id> --json <file>` — replaces `--log`; writes
  the subagent's structured return onto `steps[i].return`.
- `--show <task_id>` — unchanged in spirit.
- `load()` / `save()` module functions are kept function-compatible in
  signature (still take a state dir + id, still read/write one JSON file) so
  `loop_close.py` / `loop-close.sh` need path/schema updates, not rewrites of
  their control flow.
- `creative_score()` / `MIN_CREATIVE` are deleted outright — grounding check
  confirmed zero other hooks depend on them (`prompt-clarity-gate.sh` scores
  independently).

**SCORE absorbs ASSESS.** `score_task.py` gains `--auto <task_id>`: ports
`assess_task.py`'s git-log + metrics-shard correlation algorithm to read the
new `steps[]` schema instead of the old `parts[]` schema, iterates every step
of that plan the same way `assess_task.py` iterated every part, and writes
the per-step verdict back into that step's own `return` field in
`plans/<task_id>.json` — preserving the original per-part granularity. It
then emits one rolled-up `kind:"score"` metrics record for the task_id (the
existing granularity `score_task.py` records at), mapping the *worst* verdict
found across steps onto the existing SCALES.md `evidence` scale
(`proven > partial > asserted` — a one-to-one fit for `clean`/(no strong
signal)/`unknown`) plus `rework` when a revert or follow-up-fix commit is
found on any step. The subjective `outcome` scale stays human/agent-declared,
unchanged. `assess_task.py` is deleted; its algorithm moves into
`score_task.py`.

**Gate removed.** `~/.claude/hooks/workorder-gate.sh` (and its
`payload/hooks/` source) is deleted, and its `UserPromptSubmit` entry is
removed from `settings.json`. PLAN becomes a directive step documented in
`payload/skills/resource-loop/SKILL.md` — exercised by agent judgment for
multi-step or multi-agent work, same trust level as MATCH/ANNOUNCE/ROUTE/
SCORE today. There is no keyword-scored backstop forcing it.

**Rewrite / retire list:**

| File | Change |
|---|---|
| `tools/plan_task.py` | full rewrite (above) |
| `tools/make_brief.py` | deleted — folded into `plan_task.py` |
| `tools/assess_task.py` | deleted — folded into `score_task.py` |
| `tools/score_task.py` | add `--auto` mode |
| `hooks/workorder-gate.sh` | deleted |
| `hooks/pipeline-relay.sh` | repoint directive text at new CLI |
| `tools/loop_close.py`, `hooks/loop-close.sh` | repoint at new schema/paths |
| `tools/heuristics_eval.py`, `tools/obs_emit.py` | update convention comments |
| `payload/skills/resource-loop/SKILL.md` | document new phase flow |
| `registry/REGISTRY.md` | collapse `plan-task`/`make-brief`/`assess-task` rows into one `plan-task` row |
| `registry/guides/plan-task.md`, `registry/guides/make-brief.md` | merge into one guide |
| `observability/dashboards/shard-kpis.json` | update panel to new schema |
| `MANIFEST` | update `plan_task.py` link entry, remove `make_brief.py`/`assess_task.py` entries |
| `tools/tests/test_plan_task.py`, `test_make_brief.py`, `test_assess_task.py`, `test_workorder_gate.sh`, `test_loop_close.py`, `test_pipeline_relay.sh`, `test_hooks_harvest.sh` | rewritten against new schema/CLI; `test_make_brief.py`/`test_assess_task.py`/`test_workorder_gate.sh` retired outright |

**Migration.** One-time script converts the 18 files under
`~/.claude/metrics/state/workorders/` to the new schema at
`~/.claude/plans/<created-date>/<task_id>.json`: `parts[]` → `steps[]`
(`part_id`→`id`, `role`→`agent`, `log`/`evidence`/`verdict`/`score` → `return`
+ score-scale values where present). No dependency graph is fabricated —
`depends_on` defaults to `[]` for every migrated step. Parts already
`status:"assigned"` but never logged carry forward as `status:"pending"`; if
still relevant, re-dispatch them fresh under the new pipeline. Old directory
renamed to `workorders_archive/` post-migration, read-only.

## Phase 2 — REGISTRY domain taxonomy

Verified: REGISTRY.md's existing second column is resource **type**
(`superpower`/`skill`/`agent`/`mcp`/`tool`), not a domain category — this adds
a genuinely new third column, `domain`, populated across all 63 rows with one
of the 10 VoltAgent-matching values (`core-dev`, `language`, `infra`,
`quality-security`, `data-ai`, `dev-experience`, `specialized-domains`,
`business-product`, `meta-orchestration`, `research-analysis`).
`route_role.py` gains a two-stage match: domain filter first, then
in-domain semantic match against the (now much smaller) candidate set.
`lint_registry.py` gains a check that `domain` is non-empty and one of the 10
values. No skill files move on disk.

## Phase 3 — Blackboard

New `~/.claude/state/blackboard.db` — SQLite, WAL mode, single file, no
daemon. Five tables:

| Table | Purpose |
|---|---|
| `shared_state` | subagent-written hints/results/artifact IDs, keyed by task_id |
| `events` | append-only phase-transition audit trail |
| `consensus_state` | vote records for Phase 6's gated actions |
| `workflow_state` | checkpoints for long-running plans, resumable across sessions |
| `artifacts` | id → path + sha256 for large payloads referenced elsewhere |

`tools/bb_write.py` / `tools/bb_read.py` are the only sanctioned access path;
every write is stamped `(task_id, phase, agent_id, ts, sha256(payload))`,
mirroring the metrics harvester's discipline. `tools/bb_gc.py`, run from the
existing cron surface: 30-day trim on `shared_state`/`artifacts`, 90-day on
`events`. The `metrics/*.jsonl` ledger is untouched — blackboard is working
state, metrics stays the permanent ledger.

## Phase 4 — Worktree EXECUTE support

`~/.claude/worktrees/<task_id>/<step_id>/`, created via
`git worktree add --detach` only when a plan step (Phase 1 schema) has
`"worktree": true` — opt-in per step, not a universal default. Parent branch
untouched until SCORE passes. Merge-back goes through the normal
`loop_autocommit.sh` path, so gates 0–5 fire once, on the merge commit, not on
any intermediate per-worktree commit.

## Phase 5 — Dispatcher generalization

`tools/audit_dispatch.py` / `audit_run.sh` / `audit_store.py` /
`audit_digest.py` → `tools/dispatch/{dispatch.py,run.sh,store.py,digest.py}`,
renamed in place (not duplicated) with a `--job-type` flag added.
`jobs/security-audit.yml` becomes job #1. The 3am
`com.hdc.claude-agent-loop.repo-audit.plist` launchd job is re-pointed at the
new path in the same commit that does the rename, so the nightly run is never
left pointing at a deleted file. `dep-refresh.yml` / `doc-drift.yml` /
`metric-summary.yml` are new job definitions, added after the rename is
proven on at least one real nightly run.

## Phase 6 — Consensus gate

`consensus_state` table (Phase 3) gets a 2-of-3 vote record for: `git push`,
publish/release commands, and any AWS mutation that would fire despite
`REQUIRE_MUTATION_CONSENT=true`. This is an audit-log addition — it does not
relax the existing never-auto-push rule or the AWS consent requirement; it
gives them a queryable vote history.

## Phase 7 — GNAP reserved filenames

Four empty stub files under `coordination/` in the framework repo
(`claims.json`, `handoffs.json`, `results.json`, `agents.json`), each
containing `{"_reserved": "not implemented — see agent-loop-v2-design.md §7"}`.
No protocol logic. Purely reserves the names for a future multi-machine
scenario, per the original proposal's rationale.

---

## Testing & rollback

Test → commit → push per standing protocol, one commit per phase — each
phase is independently revertable via `git revert` in the framework repo.
Phase 1's hook/settings changes (`workorder-gate.sh` deletion, `settings.json`
edit) go through a normal `git commit`, not `loop_autocommit.sh` — that
tool's Gate 0 restriction on `settings*.json`/`hooks/` exists to stop the
*autonomous* LEARN loop from self-editing those paths; it isn't a bar on
user-directed engineering work with normal review.

Each phase's existing test suite (or its replacement, for Phase 1) must pass
before that phase's commit. Phase 1's migration script gets its own test
against a fixture copy of the 18 real work-order files, asserting no data
loss on the fields the new schema still carries.

## Explicitly not doing

- Physically reorganizing `payload/skills/` into 10 category directories —
  doesn't speed up native skill matching, which resolves most lookups without
  ever consulting REGISTRY.md.
- MCP category-prefix naming (original proposal §5.3) — deferred until MCP
  server count exceeds ~10. The original proposal cited 3; the actual current
  count is 8 distinct configured servers. Still under the threshold, but
  closer than the proposal assumed — worth re-checking before Phase 2 lands.
- GNAP as a working protocol — filenames only (Phase 7).
- Hive-mind queens, Byzantine consensus, CrewAI-style role class hierarchy,
  auto-editing `.py` files from LEARN — all explicitly rejected in the
  original proposal's §7, carried forward unchanged here.
