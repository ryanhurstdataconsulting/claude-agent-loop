# Agent Observability Layer — Design Spec

**Source.** This spec implements §2 onward ("Proposed architecture") of the
"Agent Architecture — Current State and Observability Target" doc
(claude.ai artifact `8eaf1bae-ff13-485f-b385-6fdde7f77285`). That doc's §1
audited the current `claude-agent-loop` framework and found: no run
abstraction spanning surfaces, no tracing, batch-only post-hoc measurement,
invisible hook health, no dashboards/alerts, coarse attribution, and
unobserved programmatic loops. This spec is the buildout that closes those
gaps, scoped and decided against the source doc's own Phase 0–4 migration
checklist.

**Non-goals, carried over unchanged from the source doc:**
- The JSONL shards (`~/.claude/metrics/YYYY-MM.jsonl`) remain the learning
  system's source of truth. OTel is a read-side projection, never the join
  store. `heuristics_eval.py`, `assess_task.py`, and the digest pipeline keep
  reading the shards exactly as today.
- Hooks stay stdlib-only and fail-open. No hook does network I/O; OTLP
  export happens only in the out-of-tree `obs_ship.py` sidecar, which is
  allowed to die without consequence.
- Gated lanes stay gated. `settings.json` and `hooks/` edits in this spec are
  explicit owner-directed hand edits (this build), never routed through
  `loop_autocommit.sh`, which refuses those paths by design.
- Nothing leaves the machine. All OTLP export targets `localhost`.

## Decisions locked in for this build

These were open questions in the source doc; each is now settled and drives
scope below.

| Question | Decision |
|---|---|
| How much of Phase 0–4 to build now | All of it, in one coordinated build. |
| Backend (`grafana/otel-lgtm` container) | **Skip.** Everything wires to export to `localhost:4318`, but no container runs. Export failures are silent and non-blocking by design (see Phase 2), so this is safe to leave dark indefinitely. |
| Phase 3 dashboards/alerts, which need a backend to run against | **Ship as code, unwired.** Grafana dashboard JSON + alert-rule YAML live in the repo, ready for `docker compose up` to pick up later, but nothing is validated against a live backend in this build. |
| The two dormant launchd jobs (`repo-audit`, `usage-poll`) | **Bootstrap both for real**, via `INSTALL.md`'s existing `cp` + `launchctl bootstrap` recipe. `repo-audit` has zero prior production runs (~2,500 lines) — this is the one piece of real, unreversed operational risk in this build. Confirmed acceptable by the owner. |

## Components, by phase

### Phase 1 — structured event log

**`payload/tools/obs_emit.py`** (new, stdlib only). One function:

```python
def emit(event, session_id=None, agent_id=None, plan_id=None, part_id=None,
          project=None, **attrs) -> None
```

- Computes `trace_id = sha256("run:" + root_task_id)[:32 hex]` and
  `span_id = sha256(root_task_id + ":" + component_key)[:16 hex]` per the
  source doc's §2.2 deterministic-ID scheme (no `uuid4` anywhere, matching
  the framework's existing `plan_id` convention).
- Appends one `obs.v1`-schema JSON line to
  `~/.claude/metrics/events/YYYY-MM-DD.ndjson` via `O_APPEND` — the same
  atomic-append pattern `harvest_metrics.py` already uses.
- Wrapped in a bare `try/except: pass`. A broken emit must never raise into
  the caller. No return value; nothing downstream depends on this call
  succeeding.

Schema `obs.v1` fields: `schema`, `ts` (ISO-8601), `event` (enum:
`session.start`, `prompt.submit`, `gate.decision`, `tool.pre`, `tool.post`,
`skill.invoked`, `subagent.stop`, `compaction`, `turn.stop`, `session.end`,
`run.end`, `hook.error`, `heartbeat`), `session_id`, `agent_id`, `trace_id`,
`span_id`, `parent_span_id`, `plan_id`, `part_id`, `project`, `attrs` (object,
event-specific — see source doc §2.3 for the per-event attribute list, used
verbatim: `tool_name`/`tool_use_id`/`ok`/`error_class`/`duration_ms`/
`args_hash` for `tool.*`; `gate`/`action`/`score` for `gate.decision`;
`skill_name` for `skill.invoked`; `hook`/`stage`/`message` for `hook.error`).

**Tests** — `payload/tools/tests/test_obs_emit.py`:
- Emitted record matches `obs.v1` shape and required fields.
- `trace_id`/`span_id` are deterministic (same inputs → same hex) and stable
  across process restarts.
- Appending survives a pre-existing malformed last line in the day's NDJSON
  file (never raises, never corrupts prior lines).
- Failure is silent when the events directory is unwritable (e.g.
  permission-denied fixture) — call returns normally, no exception escapes.

**New hook script `payload/hooks/obs-events.sh`** — same shape as
`harvest-metrics.sh` (bash wrapper → python heredoc, 10s `SIGALRM` guard,
`OBS_EVENTS_DISABLE=1` kill switch, always exits 0). Bound in
`payload/fragments/settings.fragment.json`:
- `PreToolUse`, no matcher (all tools) → `tool.pre`.
- `PostToolUse`, no matcher (new entry alongside the existing
  `context-budget.sh`/`usage-budget.sh` bindings) → `tool.post`.
- `Stop` (new top-level hook event for this framework) → `turn.stop`.

`tool.pre`/`tool.post` pairing: prefer `tool_use_id` from hook stdin. If
absent **[assumed — verify against current hook payload shape at
implementation time]**, fall back to `(session_id, tool_name,
sequence-counter)`, where the counter is a small per-session tmp file
incremented on each `tool.pre` and read (not incremented) on the matching
`tool.post`. `duration_ms` is computed at `tool.post` from the stored
`tool.pre` timestamp for that key. `args_hash` is `sha256` of the
normalized (sorted-keys JSON) tool input — never raw arguments.

**`gate.decision` instrumentation** — one `obs_emit.py` call added inline to:
- `payload/hooks/workorder-gate.sh`
- `payload/hooks/prompt-clarity-gate.sh`
- `payload/hooks/read-guard.sh`
- `~/.claude/hooks/account-guard.sh` (local-only file, edited directly — not
  part of the `payload/` tree, per the framework's local-lane convention;
  this edit does not flow through `install.sh`)

Each call carries `gate` (`workorder|clarity|read-guard|account`), `action`
(`silent|inject|block|deny|warn`), and `score` where applicable.

**`skill.invoked`** — extends `payload/hooks/pipeline-relay.sh`, which
already owns the `PostToolUse(Skill)` binding, rather than adding a new
script. Carries `skill_name`. This is the highest-leverage record in the
whole build per the source doc: it is tool-written, per-resource attribution
independent of the ANNOUNCE-line prose contract (measured at 21.7%/~2%
compliance today), and directly raises the precise-evidence row count
`heuristics_eval.py` needs.

**`hook.error` trap wrapper** — a 3-line `trap` block added near the top of
all 13 hook scripts (11 under `payload/hooks/` + the 2 local-only files
`account-guard.sh` and `zoom-token-refresh.sh` in `~/.claude/hooks/`) that
calls `obs_emit.py` with `event=hook.error`, `hook=<script name>`,
`stage=<trap context>`, `message=<captured error>` immediately before the
script's existing `exit 0` / `os._exit(0)`. Exit behavior is unchanged in
every case — this only adds a breadcrumb when something already failed
silently.

### Phase 2 — runs and traces

**`kind:"run"` records**, emitted into the existing monthly shards (same
`(task_id, kind)` last-wins contract, no second store):

```json
{"kind": "run", "task_id": "session-b6c80e44-...", "schema": "run.v1",
 "run_kind": "session", "parent_task_id": null,
 "outcome": "success | failure | partial | interrupted",
 "stop_reason": "completed | error | timeout | user-interrupt | budget | max-turns",
 "trace_id": "8f3a...", "plan_id": null, "part_id": null,
 "ts_start": "...", "ts_end": "..."}
```

`outcome` is derived, never asserted: for work-order-linked runs, mapped
from the `assess_task.py` verdict (`clean`→`success`, `dirty`→
`partial`/`failure` by severity, `unknown`→`partial`); for others, from
process exit codes and interrupt flags already visible to the emitter.

- **`payload/tools/loop_close.py`** — extended to emit `kind:"run"` at
  session/subagent close, alongside its existing work-order close logic.
- **`payload/tools/audit_run.sh`** — extended to emit the audit-run
  equivalent from its existing success and `_fail_run` paths.

**`payload/observability/obs_ship.py`** (new) — the span-builder sidecar.

- Runs out-of-session, in its own venv at `~/.claude-agent-loop/obs-venv`
  (real `opentelemetry-sdk` dependency — acceptable here because this is an
  out-of-tree sidecar, following the same placement precedent as the
  existing Playwright usage-poll venv; hooks themselves stay stdlib-only).
- Reads `~/.claude/metrics/events/*.ndjson` with a cursor file
  (`obs_ship.cursor.json`, same pattern as the existing `harvest.cursor.json`).
- Folds events into the span hierarchy from the source doc's §2.4: one root
  span per run, child spans per turn, grandchild spans per gate/tool/skill
  call, subagent spans linked via `parent_span_id`.
- Exports via OTLP to `http://localhost:4318`. **If export fails** (expected
  right now, since no backend is running): catch the exception, do **not**
  advance the cursor past the failed batch, exit 0. Events remain in NDJSON
  and are retried on the next invocation once a backend exists. A live
  session never observes this either way — the sidecar runs entirely
  out-of-process.
- Scheduled via new plist `com.hdc.claude-agent-loop.obs-ship.plist`,
  `StartInterval 60`, added to `payload/launchd/` and symlinked through
  `install.sh`'s existing `link-file` mechanism into `~/.claude/launchd/`.
  Bootstrapped for real per the `INSTALL.md` recipe (`cp` to
  `~/Library/LaunchAgents/` + `launchctl bootstrap gui/$(id -u)` +
  `launchctl list` verification) — this is the 3rd launchd job, alongside
  `repo-audit` and `usage-poll`.

**`payload/tools/make_brief.py`** — dispatch briefs gain a W3C `traceparent`
header value and the run ID (both derived per §2.2, no lookup required).
`loop_close.find_agent_id()` tries an O(1) event-log lookup by that ID first,
falling back to the existing directory scan if the lookup misses — no
regression on the failure path, faster on the common one.

**Tests** — `payload/observability/tests/test_obs_ship.py`: span-folding
against a fixture NDJSON file, cursor advancement on successful export
(mocked OTLP client), and the "OTLP endpoint unreachable → cursor does not
advance, no exception escapes" path — verified without a live collector.

### Phase 0 — native telemetry + inert backend config

(Sequenced after Phase 1/2 in the rollout so there's something real to
export once this is turned on.)

- **`~/.claude/settings.json`** — hand-edited directly (gated lane, owner-
  authorized for this build) to add the `env` block from source-doc §2.4:
  `CLAUDE_CODE_ENABLE_TELEMETRY`, `OTEL_METRICS_EXPORTER`,
  `OTEL_LOGS_EXPORTER`, `OTEL_EXPORTER_OTLP_PROTOCOL`,
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`,
  `OTEL_RESOURCE_ATTRIBUTES=service.name=claude-code,deployment.environment=hdc-local`.
  **[assumed]** Exact variable/metric names — verify against current Claude
  Code monitoring docs at implementation time; the mechanism (OTLP metrics +
  logs via env config) is the stable part.
- **`payload/observability/docker-compose.yml`** (new) — single
  `grafana/otel-lgtm` service, OTLP receivers on 4317 (gRPC) / 4318 (HTTP),
  Grafana UI on 3000, dashboard-provisioning volume mount pointed at
  `payload/observability/dashboards/` (Phase 3). Not started as part of this
  build.

### Phase 3 — shard retrofit, dashboards/alerts-as-code, launchd bootstrap

**`payload/tools/metrics_to_otlp.py`** (new) — read-only retrofit exporter
over the existing shards. Reads `kind:"task"`, `kind:"score"`,
`kind:"learn"` records and emits corresponding OTel metrics: tests
passed/failed, `error_rate`, `cache_efficiency`, assess verdicts, heuristic
firings by rule, `resources_source` mix. Idempotent via the shards' own
`(task_id, kind)` last-wins keys — safe to re-run without double-counting.
Never mutates the shards.

**Dashboards-as-code**, `payload/observability/dashboards/*.json` — one per
row of the source doc's §2.5 metrics catalog: run timelines, tool-call
latency p50/p95 by `tool_name`, tool error rate live, gate decisions by
gate×action, skill invocations by skill, subagents-per-session/task-depth,
turns-per-run/compactions-per-session, the shard-derived KPIs above (with
the precise-vs-backfill attribution ratio called out specifically, per the
source doc), and scheduler liveness. Picked up automatically by the compose
file's provisioning mount whenever it's eventually started.

**Alert rules-as-code**, `payload/observability/alerts/*.yaml` — the six
from §2.5:
1. No `repo-audit` `run.end` in 26h.
2. Any wired hook silent for N sessions (via `hook.error`/heartbeat age).
3. ≥5 `tool.post` events with the same `(tool_name, args_hash)` within 1
   minute (repeated-call / thrash detection).
4. Subagent depth ≥3.
5. Fan-out ≥N subagents per turn.
6. Cost/day threshold exceeded.

Both directories are inert until a backend exists to import them into.

**Launchd bootstrap (live, not code-only):**
- `repo-audit`: `cp ~/.claude/launchd/com.hdc.claude-agent-loop.repo-audit.plist ~/Library/LaunchAgents/` → `launchctl bootstrap gui/$(id -u) ...` → confirm via `launchctl list | grep repo-audit`.
- `usage-poll`: same recipe, per the existing `INSTALL.md` section 2 steps.
- Both verified loaded before this phase is considered done.

### Phase 4 — outer surfaces and guardrails

- **`payload/tools/audit_run.sh`** — pass the `OTEL_*` env vars into the
  `claude` subprocess invocation (native export inside that subprocess,
  no new instrumentation code needed) plus
  `OTEL_RESOURCE_ATTRIBUTES=...,audit.package=<key>,parent.run=<dispatch-run-id>`
  for parent/child linkage back to the dispatcher. Add retry-once-on-
  infrastructural-failure: if the CLI exits non-zero with no findings
  written, retry once in a fresh worktree; a model-produced failure (CLI
  succeeded, findings are just bad) never retries — it alerts instead via
  the existing lost-run detector. Both outcomes emit `run.end` with distinct
  `stop_reason`s.
- **`HDC_Assistant/src/hdc_assistant/agent/core.py`** — add
  `opentelemetry-sdk` to `pyproject.toml`. Instrument
  `run_agent_turn_async()` (currently: retries once on any exception,
  `backoff_seconds` delay) with one span per turn and a child span per
  retry attempt, exporting to the same `localhost:4318` endpoint via
  `opentelemetry-sdk` directly (this is application code, not a hook — real
  dependencies are fine here). The existing "success but
  `message.subtype != 'success'`" edge case becomes a span status instead
  of the current silent branch.
- **SQL-preflight hook** — new `PreToolUse(Bash)` binding in
  `HDCx68Sports/68_Challenge_Report/.claude/settings.local.json`, matched
  against Bash commands touching `psql`/`sports68db`/the bastion SSH
  tunnel. Runs a static check mirroring what the `sql-safety-reviewer`
  agent checks for (read-only transaction wrapper present, statement
  timeout set, no DDL/DML keywords) and **warns via
  `hookSpecificOutput.additionalContext`, never blocks** — consistent with
  every other hook's fail-open, additive-only posture in this framework.
  Ships with one tracked example query file demonstrating the expected
  pattern.
- **Hook-health heuristic stub** —
  `~/.claude/registry/candidates/2026-08-05-hook-health-heuristic.md`,
  describing a future H9 rule over `hook.error` counts + per-hook heartbeat
  age. Filed as a candidate per the framework's own rule that heuristic IDs
  are owner-gated (`lint_heuristics.py`) — not implemented in this build.

## Rollout order

Each phase is independently useful and reversible, matching the source
doc's own phasing intent:

1. **Phase 1** (event log) — events accumulate in NDJSON immediately, useful
   standalone even with nothing downstream reading them yet.
2. **Phase 2** (run abstraction + tracing sidecar) — `kind:"run"` records
   land in the shards; the sidecar starts folding spans (export fails
   silently until Phase 0 is live and a backend exists — expected).
3. **Phase 0** (native telemetry env + compose file) — now there's
   something real for both native OTel and the sidecar to export.
4. **Phase 3** (shard retrofit + dashboards/alerts-as-code + launchd
   bootstrap) — the retrofit exporter and dashboard/alert authoring are
   code-only; the launchd bootstrap is the one live-infrastructure step.
5. **Phase 4** (outer surfaces + SQL-preflight guardrail + heuristic stub).

Each phase lands as its own commit(s) on `feat/agent-observability-layer` in
`claude-agent-loop` (branched off `main`; the prior checked-out branch,
`feat/vendor-claude-pentest`, is unrelated and was left alone). The
`HDC_Assistant` and `68_Challenge_Report` changes in Phase 4 are separate
commits in their own repos, referencing this spec.

## Testing summary

| Component | Test approach |
|---|---|
| `obs_emit.py` | Unit tests: schema shape, deterministic IDs, append-safety, silent-failure path. No live session needed. |
| `obs-events.sh` bindings | Exercised naturally the next time hooks fire in any session; verify by tailing `~/.claude/metrics/events/*.ndjson` after a real session. |
| `gate.decision`/`skill.invoked`/`hook.error` emits | Same — verified against real NDJSON output post-change, spot-checked against known trigger conditions (e.g. a low-score prompt for `gate.decision:silent`). |
| `loop_close.py` / `audit_run.sh` `run.end` | Unit tests against fixture transcripts/exit codes for outcome derivation; live-verified against the next real session/audit close. |
| `obs_ship.py` | Unit tests against fixture NDJSON: span folding, cursor advancement, and the unreachable-OTLP-endpoint non-crash path. |
| `metrics_to_otlp.py` | Unit tests against fixture shard lines; idempotency check (run twice, assert no duplicate emission). |
| Dashboards/alerts-as-code | Static JSON/YAML validity only — no live backend to validate against in this build. |
| Launchd bootstrap | `launchctl list | grep <label>` for all three jobs, plus tailing each job's log path after its first scheduled fire. |
| `HDC_Assistant` instrumentation | Existing test suite (`tests/test_agent_core.py`) extended to assert span creation/status on the success and retry paths, using the SDK's in-memory span exporter for test isolation (no real OTLP call in tests). |
| SQL-preflight hook | New hook fixture test asserting warn-not-block on a query missing the read-only wrapper, and silence on a compliant one. |

## Assumptions carried forward from the source doc

- **[assumed]** Native Claude Code OTel env-var and metric names as written
  in Phase 0 — verify against current docs before that step.
- **[assumed]** `PreToolUse`/`PostToolUse` hook payloads carry a
  `tool_use_id`. Fallback pairing by `(session_id, tool_name, sequence)` is
  specified above if not.
- Telemetry sensitivity: traces will contain client project slugs, same as
  the metrics store already does today. Everything stays localhost-only in
  this build; any future remote export would need to pass the same
  `classify_visibility.py` standard applied to committed files.
