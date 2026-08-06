# Agent Observability Layer — Phase 3: Shard Retrofit, Dashboards/Alerts-as-Code, Launchd Bootstrap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retrofit-export the existing metrics shards' historical `kind:"task"`/`kind:"score"`/`kind:"learn"` data as OTel metrics; ship dashboards-as-code and alerts-as-code (both inert, no live backend to validate against); and — the one live-infrastructure step in this whole build — actually bootstrap the three dormant launchd jobs (`repo-audit`, `usage-poll`, `obs-ship`).

**Architecture:** `metrics_to_otlp.py` is a new, stdlib-plus-OTel-SDK tool (same venv as `obs_ship.py`) that scans every monthly shard, applies the shards' own `(task_id, kind)` last-wins dedup (the same pattern `heuristics_eval.load_metrics()` already implements), and emits OTel metrics — read-only, idempotent, never mutates a shard. Dashboards/alerts are static JSON/YAML with nowhere live to validate against yet. The launchd bootstrap is 3 `cp` + `launchctl bootstrap` invocations, one of which (`repo-audit`) this plan's own research found will safely no-op every night (a caught, logged `ConfigError`, not a crash) until a human authors `~/.claude/metrics/audit/config.json` — a real spend-policy decision (which repos, how often, real billed CLI invocations) explicitly OUT of this plan's scope to fabricate.

**Tech Stack:** Python 3, `opentelemetry-sdk`'s **metrics** submodule (a new API surface for this codebase — Phase 2's `obs_ship.py` only exercised the tracing submodule) via the same `~/.claude-agent-loop/obs-venv`. Static JSON (Grafana dashboard model) and YAML (Grafana unified-alerting-style rules) for the -as-code deliverables.

## Global Constraints

- **`metrics_to_otlp.py` never mutates a shard.** Read-only, always. Idempotent means "safe to re-run without double-counting," not "writes anything back to the shard."
- **Dashboards/alerts are unvalidated against a live backend in this build** — same posture as Phase 0's compose file. Static-validity checks only (JSON schema plausibility, YAML syntax).
- **The launchd bootstrap is real and live.** This is the one step in the whole 5-phase build with genuine, hard-to-fully-reverse effect (a scheduled job starts running on this machine going forward). Per the source design spec's own explicit framing: *"repo-audit has zero prior production runs (~2,500 lines) — this is the one piece of real, unreversed operational risk in this build. Confirmed acceptable by the owner."* This plan proceeds with the bootstrap as specified, but does **not** additionally fabricate `~/.claude/metrics/audit/config.json` (a real, separate policy decision — which repos get audited, how often, spending real billed `claude` CLI invocations — nowhere specified in the source spec or this plan). Confirmed via this plan's own research: `audit_dispatch.py` fails safely (a caught `ConfigError`, logged, no crash cascade, nothing destructive) when that config is absent, so bootstrapping without it leaves the job genuinely dormant in practice, not silently dangerous.
- **No fabricated dashboard content.** Every dashboard panel must correspond to a real, already-emitting field in the shard/event-log schema this build actually produces — no placeholder metrics for data that doesn't exist yet.

## Design decisions locked in for this plan

1. **`metrics_to_otlp.py`'s idempotency mechanism**: this plan's own research found no existing tool that does exactly what's needed (a full-shard-glob scan with per-(task_id,kind) last-wins dedup AND a persisted cursor to skip re-exporting unchanged records across runs). The closest precedents are `heuristics_eval.load_metrics()`'s in-memory last-wins dedup loop (shape to copy) and `obs_ship.py`'s atomic cursor-file save pattern (mechanism to copy) — this plan combines both: a cursor file mapping `(task_id, kind) -> sha256(json.dumps(record, sort_keys=True))`, so a record that hasn't changed since the last run is skipped, and a record whose content changed (a later last-wins line for the same key) re-exports with its new value.
2. **`verdict` is not a universal `kind:"task"` field** — confirmed via live-data grep: only `loop_close.py`'s workorder-emitted task records carry it (a small subset of all `kind:"task"` records; `harvest_metrics.build_record()`'s transcript-parsed path never sets it). The exporter must treat a missing `verdict` key as "not recorded," never coerce it to `"unknown"` (that coercion is `loop_close.py`'s own business logic, not a shard-wide invariant).
3. **`H0` and other rule ids outside `heuristics_eval.EVALUABLE_RULES` (H1–H8) appear in real historical `kind:"learn"` data.** The exporter counts firings by whatever rule id string literally appears in the data — never a hardcoded H1–H8 enum — so it doesn't silently drop real historical signal from a retired or renumbered rule.
4. **Alerts-as-code needs a docker-compose.yml volume mount that doesn't exist yet.** Phase 0's compose file only wires a dashboard-provisioning mount (`./dashboards:/otel-lgtm/grafana/dashboards`); there is no equivalent alerting-provisioning mount. This plan adds one (`./alerts:/otel-lgtm/grafana/provisioning/alerting`) so the alert YAMLs are genuinely "picked up automatically... whenever it's eventually started," matching the dashboards' own already-correct framing — not a new claim, a fix to make an existing claim (in the source spec, "Both directories are inert until a backend exists to import them into") actually true for alerts too.
5. **INSTALL.md needs a new `## Repo-security-audit scheduler (one-time)` section.** This plan's own research found the source spec's Phase 3 assumes `repo-audit` already has a documented bootstrap recipe in `INSTALL.md` the same way `usage-poll` does — it doesn't. This plan adds one, mirroring the existing two sections' style, including the config-authoring caveat from design decision 3 above.
6. **OTel metrics API is unverified — empirically verify before finalizing**, same posture Phase 2 Task 4 took toward the tracing API (which found and worked around 3 real SDK constraints no one anticipated). Do not assume `opentelemetry.sdk.metrics` behaves like `opentelemetry.sdk.trace` structurally.

---

### Task 1: `payload/tools/metrics_to_otlp.py` — read-only retrofit exporter

**Files:**
- Create: `payload/tools/metrics_to_otlp.py`
- Create: `payload/tools/tests/test_metrics_to_otlp.py`
- Modify: `payload/MANIFEST` (add `link-file tools/metrics_to_otlp.py`)

**Interfaces:**
- Consumes: `opentelemetry.sdk.metrics` (new API surface — verify empirically), the same `~/.claude-agent-loop/obs-venv` Phase 2 set up.
- Produces: nothing other tasks call — terminal consumer of the shards.

- [ ] **Step 1: Verify the OTel metrics API empirically before writing real code**

In a throwaway venv (or the persistent `~/.claude-agent-loop/obs-venv` if it exists on this machine by now — check first, don't assume), confirm: does `opentelemetry-sdk` (already a dependency per Phase 2) include the `opentelemetry.sdk.metrics` submodule, or is a SEPARATE package needed (check `pip show opentelemetry-sdk` and try `python3 -c "import opentelemetry.sdk.metrics"`)? Confirm whether `opentelemetry-exporter-otlp-proto-http` (already installed for tracing) ALSO covers metrics export, or whether a distinct import path (`opentelemetry.exporter.otlp.proto.http.metric_exporter`) is needed. Read enough of the installed package's own source/docs to understand the MeterProvider/Meter/Counter-or-Histogram API shape well enough to build synchronous counters (test pass/fail counts) and histograms (error_rate distribution) correctly — don't guess at the API shape the way an earlier phase's brief guessed at the tracing API and was wrong.

- [ ] **Step 2: Write the failing tests**

Create `payload/tools/tests/test_metrics_to_otlp.py`, following `test_harvest_metrics.py`'s fixture-dict-and-`unittest.TestCase` convention (NOT the tempfile-per-test style `test_obs_emit.py` uses — match whichever convention this specific kind of "fixture shard file" test already established in this repo; read `test_harvest_metrics.py`'s fixture-construction helpers first). Cover:
- Reading a fixture shard with `kind:"task"` records (some with `verdict`, some without), `kind:"score"` records, `kind:"learn"` records (including a rule id outside H1-H8) → confirm the right counts/aggregates are computed for each metric category (tests passed/failed sums, error_rate distribution, verdict counts treating missing-verdict as its own bucket not "unknown", heuristic firings grouped by the LITERAL rule string in the data, resources_source mix).
- Idempotency: run the exporter twice against the same fixture shard with a mocked/no-op exporter — confirm the SECOND run either skips already-exported unchanged records (per design decision 1's cursor mechanism) or, if using an OTel metrics API that's inherently additive/re-computable rather than "export once," confirm the chosen approach doesn't double-count when re-run (this depends on Step 1's findings — write the test to match whatever mechanism Step 1 confirms the real API actually supports, not a mechanism assumed in advance).
- A shard containing a superseding record for the same `(task_id, kind)` (last-wins) → confirm only the LATEST value is exported, not both.
- Never mutates the shard file — read its bytes before and after running the exporter, assert byte-identical.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd payload/tools/tests && python3 -m unittest test_metrics_to_otlp -v` (using whichever `python3` Step 1 confirmed has the metrics API — likely the obs-venv's interpreter, not bare system python3, since this needs the same real dependency `obs_ship.py` does)
Expected: `ModuleNotFoundError: No module named 'metrics_to_otlp'`

- [ ] **Step 4: Implement `metrics_to_otlp.py`**

Structure (adapt exactly per Step 1's empirical findings — this is a skeleton, not literal code to copy verbatim, unlike earlier phases' fully-specified tasks, because the metrics API shape is unverified going in):
- A shard-scanning function modeled on `heuristics_eval.load_metrics()`'s last-wins dedup loop: glob `~/.claude/metrics/*.jsonl`, parse each line, keep the LAST record per `(task_id, kind)` across the whole scan.
- Per-metric-category aggregation functions: tests passed/failed (from `kind:"task"` records' `tests` sub-object), error_rate distribution, verdict counts (bucketing missing-verdict separately, per design decision 2), heuristic firings by literal rule string (per design decision 3), resources_source mix (`workorder`/`task`/`session`/`session-backfill`).
- A cursor file at `~/.claude/metrics/state/metrics_to_otlp.cursor.json` mapping `"%s:%s" % (task_id, kind)` to a content hash, using the same atomic tmp-file-then-`os.replace` save pattern `obs_ship.py`'s `_save_cursor` already established.
- OTel metrics emission via whatever MeterProvider/Meter API Step 1 confirmed, exporting to the same `http://localhost:4318` endpoint every other phase uses.
- A `main()` with argparse (`--metrics-dir`, `--cursor`, `--endpoint`), matching this repo's existing tool conventions (see `loop_close.py`'s `main()` for the pattern).
- Never write to a shard file anywhere in this module.

- [ ] **Step 5: Run tests to verify they pass**

Run the same command as Step 3.
Expected: all tests `OK`.

- [ ] **Step 6: Wire into MANIFEST**

Add `link-file tools/metrics_to_otlp.py` to `payload/MANIFEST`, placed alphabetically near the other `tools/*.py` entries (after `make_brief.py`, before `plan_task.py`, matching this repo's established near-alphabetical convention).

- [ ] **Step 7: Run the full existing test suite**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -30` and `bash payload/observability/tests/run.sh` (the venv-aware runner Phase 2 added) — confirm no regressions in either.

- [ ] **Step 8: Commit**

```bash
git add payload/tools/metrics_to_otlp.py payload/tools/tests/test_metrics_to_otlp.py payload/MANIFEST
git commit -m "$(cat <<'EOF'
feat(observability): add metrics_to_otlp.py — read-only shard retrofit exporter

(1) Task & Change
New tool scanning every monthly ~/.claude/metrics/*.jsonl shard, applying
the shards' own (task_id, kind) last-wins dedup, and emitting OTel metrics
for tests passed/failed, error_rate, verdict distribution (treating
missing-verdict as its own bucket, since verdict is only ever set on
workorder-emitted kind:"task" records, not universally), heuristic firings
by literal rule id (including ids outside the H1-H8 enum, e.g. H0, found
in real historical data), and resources_source mix. Never mutates a shard;
idempotent via a cursor file keyed by (task_id, kind) -> content hash, so
an unchanged last-wins record is skipped on re-run.

(2) Tests created / modified
- payload/tools/tests/test_metrics_to_otlp.py: [describe exact coverage
  once written, matching Step 2's list]

(3) Test results — evidence
[paste full real output]
EOF
)"
```

---

### Task 2: Dashboards-as-code

**Files:**
- Create: `payload/observability/dashboards/run-timelines.json`
- Create: `payload/observability/dashboards/tool-call-latency.json`
- Create: `payload/observability/dashboards/tool-error-rate.json`
- Create: `payload/observability/dashboards/gate-decisions.json`
- Create: `payload/observability/dashboards/skill-invocations.json`
- Create: `payload/observability/dashboards/subagent-fanout-depth.json`
- Create: `payload/observability/dashboards/shard-kpis.json`
- Create: `payload/observability/dashboards/scheduler-liveness.json`

**Interfaces:** None — static config, picked up by `docker-compose.yml`'s existing dashboard volume mount, never validated against a live backend in this build.

- [ ] **Step 1: Confirm the real, already-emitting fields each dashboard will chart**

Before writing any dashboard JSON, list the exact obs.v1/shard fields each one charts, confirming every single one is a real field this build actually emits (no placeholder metrics):
- **run-timelines**: `kind:"run"` records' `ts_start`/`ts_end`/`outcome`/`run_kind` (Phase 2).
- **tool-call-latency**: `obs.v1` `tool.post` events' `attrs.duration_ms` grouped by `attrs.tool_name`, p50/p95 (Phase 1).
- **tool-error-rate**: `obs.v1` `tool.post` events' `attrs.ok`/`attrs.error_class` (Phase 1).
- **gate-decisions**: `obs.v1` `gate.decision` events' `attrs.gate`×`attrs.action` (Phase 1).
- **skill-invocations**: `obs.v1` `skill.invoked` events' `attrs.skill_name` (Phase 1).
- **subagent-fanout-depth**: `obs.v1` events grouped by `agent_id`/`parent_span_id` depth (Phase 1/2) — note per this plan's own Task 6 caveat, `agent_id` is never actually populated by any current hook, so this panel's query will be structurally valid but return no data until a future phase threads `agent_id` through — state this explicitly in the dashboard's own JSON description field, not just this plan, so nobody mistakes an empty panel for a bug.
- **shard-kpis**: `metrics_to_otlp.py`'s exported metrics (Task 1) — tests passed/failed, error_rate, verdict mix, resources_source mix (with the precise-vs-backfill attribution ratio as its own explicit panel, per the source spec's specific callout).
- **scheduler-liveness**: `kind:"run"` `run_kind:"audit"` records' recency (feeds Alert 1 in Task 3) plus `obs_ship.py`'s own health (the `"reason"` field Phase 2's final review added).

- [ ] **Step 2: Write each dashboard as a minimal, valid Grafana dashboard-model JSON**

Each file follows the same skeleton (Grafana's dashboard JSON model — `title`, `panels` array, each panel a `type`/`title`/`targets` referencing the metric/field it charts, `description` noting the exact source per Step 1). Keep panels minimal (1-3 per dashboard) — this is about shipping structurally correct, honestly-scoped code, not a polished dashboard design (no live backend exists to iterate against visually in this build). Example shape for one file (`run-timelines.json`):
```json
{
  "title": "Run Timelines",
  "description": "kind:\"run\" records (Phase 2) — one row per subagent/session/audit run, grouped by outcome.",
  "panels": [
    {
      "type": "table",
      "title": "Recent runs by outcome",
      "description": "Source: kind:\"run\" records in ~/.claude/metrics/*.jsonl, run_kind in (subagent, session, audit).",
      "targets": [
        {"query": "SELECT ts_start, ts_end, run_kind, outcome, stop_reason FROM runs ORDER BY ts_start DESC LIMIT 100"}
      ]
    },
    {
      "type": "piechart",
      "title": "Outcome distribution",
      "description": "Count of kind:\"run\" records grouped by outcome (success/failure/partial/interrupted).",
      "targets": [
        {"query": "SELECT outcome, count(*) FROM runs GROUP BY outcome"}
      ]
    }
  ]
}
```
(The exact `query` syntax is illustrative/placeholder-for-a-real-datasource — since no backend exists to wire a real Grafana datasource against in this build, use a plain-English-adjacent pseudo-SQL `query` string in each target rather than inventing a fake, precise-looking query language that would mislead a future implementer into thinking it's copy-paste-ready for a specific datasource plugin. State this explicitly in each dashboard's top-level `description`.)

Repeat this shape for all 8 files, each with 1-3 panels covering exactly the fields listed in Step 1 for that dashboard, each `description` citing its real source fields and phase.

- [ ] **Step 3: Validate JSON syntax for all 8 files**

Run: `for f in payload/observability/dashboards/*.json; do python3 -c "import json,sys; json.load(open('$f'))" && echo "OK: $f" || echo "FAIL: $f"; done`
Expected: `OK:` for all 8.

- [ ] **Step 4: Confirm no MANIFEST change needed**

`payload/MANIFEST` already has `link-dir observability` (Phase 2) — confirm this covers the new `dashboards/` subdirectory automatically (it does, since `link-dir` symlinks the whole tree recursively). No new MANIFEST line needed.

- [ ] **Step 5: Run the full existing test suite**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -20` — sanity check only, this task touches no code.

- [ ] **Step 6: Commit**

```bash
git add payload/observability/dashboards/
git commit -m "$(cat <<'EOF'
feat(observability): add dashboards-as-code for the metrics catalog

(1) Task & Change
8 minimal Grafana dashboard-model JSON files, one per row of the source
spec's metrics catalog, each charting real fields this build already
emits (obs.v1 events from Phase 1, kind:"run" records from Phase 2,
metrics_to_otlp.py's exports from this phase's Task 1) — no placeholder
metrics for data that doesn't exist. The subagent-fanout-depth dashboard
explicitly notes in its own description that its query will return no
data yet, since no current hook populates agent_id — an honest, visible
caveat rather than a silently-empty panel. Picked up automatically by
docker-compose.yml's existing dashboard volume mount whenever a backend
is eventually started; not validated against a live backend in this
build, per the source spec's own Phase 0/3 framing.

(2) Tests created / modified
None — static config. Evidence is JSON validity.

(3) Test results — evidence
[paste the per-file OK/FAIL loop output — all 8 must show OK]
EOF
)"
```

---

### Task 3: Alerts-as-code + the missing compose.yml volume mount

**Files:**
- Create: `payload/observability/alerts/repo-audit-silent.yaml`
- Create: `payload/observability/alerts/hook-silent.yaml`
- Create: `payload/observability/alerts/tool-call-thrash.yaml`
- Create: `payload/observability/alerts/subagent-depth.yaml`
- Create: `payload/observability/alerts/subagent-fanout.yaml`
- Create: `payload/observability/alerts/cost-per-day.yaml`
- Modify: `payload/observability/docker-compose.yml` (add the alerting-provisioning volume mount — design decision 4)

**Interfaces:** None — static config.

- [ ] **Step 1: Add the missing volume mount to `docker-compose.yml`**

Read the current file (Phase 0 created it) and add, alongside the existing `dashboards` mount:
```yaml
    volumes:
      - ./dashboards:/otel-lgtm/grafana/dashboards
      - ./alerts:/otel-lgtm/grafana/provisioning/alerting
```
Validate YAML syntax after the edit (same method Phase 0 used — `python3 -c "import yaml; yaml.safe_load(...)"` or `docker compose config`, whichever is actually available on this machine).

- [ ] **Step 2: Write each alert rule as a minimal Grafana unified-alerting-style YAML**

Grafana's alerting provisioning format is a real, specific schema (`apiVersion`, `groups`, each group a `name`/`folder`/`interval`/`rules` list, each rule a `uid`/`title`/`condition`/`data` query array). Since no live Grafana instance exists to validate the exact schema against in this build, write each file honestly as a best-effort approximation of that shape with a top-level comment stating this explicitly (matching the pattern the source spec itself uses for "inert until a backend exists"). Example (`repo-audit-silent.yaml`):
```yaml
# repo-audit-silent.yaml — Grafana unified-alerting provisioning format
# (best-effort shape; unvalidated against a live Grafana instance in this
# build — see payload/observability/README.md).
#
# Condition: no kind:"run" record with run_kind:"audit" and a fresh
# ts_end has landed in the last 26 hours (repo-audit fires nightly at
# 03:17; 26h gives one missed-and-retried cycle of slack before alerting).
apiVersion: 1
groups:
  - name: claude-agent-loop
    folder: claude-agent-loop
    interval: 1h
    rules:
      - uid: repo-audit-silent
        title: "repo-audit has not completed a run in 26 hours"
        condition: B
        data:
          - refId: A
            model:
              query: "SELECT max(ts_end) FROM runs WHERE run_kind = 'audit'"
          - refId: B
            model:
              expression: "now() - A > 26h"
        for: 1h
        labels:
          severity: warning
```
Repeat this shape for the other 5 (tool-call-thrash: "≥5 tool.post events with same (tool_name, args_hash) within 1 minute"; hook-silent: "any wired hook silent for N sessions" — note in the YAML comment that "N" needs a concrete default, e.g. 20, stated explicitly rather than left as a free variable; subagent-depth: "≥3"; subagent-fanout: "≥N subagents per turn" — same N-needs-a-default note; cost-per-day: "exceeds threshold" — same note, and flag in the comment that this alert has no data source yet since no cost-per-day metric is emitted by any phase of this build, making this the one alert that's aspirational rather than wired to a real emitted field — say so plainly).

- [ ] **Step 3: Validate YAML syntax for all 6 files**

Run: `for f in payload/observability/alerts/*.yaml; do python3 -c "import yaml; yaml.safe_load(open('$f'))" && echo "OK: $f" || echo "FAIL: $f"; done`
Expected: `OK:` for all 6.

- [ ] **Step 4: Run the full existing test suite**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -20`

- [ ] **Step 5: Commit**

```bash
git add payload/observability/alerts/ payload/observability/docker-compose.yml
git commit -m "$(cat <<'EOF'
feat(observability): add alerts-as-code and the missing alerting volume mount

(1) Task & Change
6 Grafana unified-alerting-style YAML rules for the source spec's six
named conditions, plus the docker-compose.yml alerting-provisioning
volume mount that didn't exist before this commit (only the dashboards
mount did) — without it, these files would never actually be "picked up
automatically... whenever it's eventually started" as claimed. Two
conditions (hook-silent's N, subagent-fanout's N) get an explicit stated
default rather than an undefined free variable. cost-per-day is flagged
honestly as aspirational — no phase of this build emits a cost-per-day
metric yet, so this rule has no data source until one does.

(2) Tests created / modified
None — static config. Evidence is YAML validity.

(3) Test results — evidence
[paste the per-file OK/FAIL loop output — all 6 must show OK]
EOF
)"
```

---

### Task 4: `INSTALL.md` — add the missing repo-audit scheduler section

**Files:**
- Modify: `INSTALL.md`

**Interfaces:** None.

- [ ] **Step 1: Add the new section**

Add, mirroring the existing "Usage-budget poller (one-time)" and "Observability sidecar (one-time)" sections' style, placed after the observability-sidecar section:

```markdown
## Repo-security-audit scheduler (one-time)

`payload/tools/audit_dispatch.py` (invoked nightly at 03:17 by
`com.hdc.claude-agent-loop.repo-audit.plist`) needs a config file this
framework deliberately never ships or auto-generates — `audit/config.json`
in the audit store encodes a real policy decision (which repos get
audited, how often, and every audit run is a real, billed `claude` CLI
invocation) that only the machine's owner should make.

1. **Load the launchd job** (safe to do before authoring the config below —
   `audit_dispatch.py` fails safely with a caught, logged error and does
   nothing destructive if the config is absent; the job is genuinely
   dormant in practice until you complete step 2):

   ```bash
   cp ~/.claude/launchd/com.hdc.claude-agent-loop.repo-audit.plist \
      ~/Library/LaunchAgents/
   launchctl bootstrap gui/$(id -u) \
      ~/Library/LaunchAgents/com.hdc.claude-agent-loop.repo-audit.plist
   ```

   Confirm it is loaded:

   ```bash
   launchctl list | grep repo-audit
   ```

2. **Author the audit config** (not done for you — this is a real policy
   decision). Create `~/.claude/metrics/audit/config.json` with at least a
   `workspace` (the directory tree to scan for auditable packages), `tiers`
   (audit-frequency tiers), and `per_night_cap` (max packages audited per
   run). See `payload/tools/audit_store.py`'s `load_config()` for the exact
   schema this file must satisfy, and `payload/tools/audit_dispatch.py` for
   how tiers and the nightly cap are applied.

Until step 2 is done, the job fires nightly, logs a `ConfigError` to
`~/.claude/metrics/audit/logs/repo-audit.err.log`, and exits — no worktree
is created, no `claude` CLI runs, nothing is spent.
```

- [ ] **Step 2: Run the prose-grammar gate on the edited section**

Run: `python3 ~/.claude/tools/prose_grammar_gate.py INSTALL.md` (per this machine's global grammar-quality standard for any user-facing doc) — fix anything it flags.

- [ ] **Step 3: Commit**

```bash
git add INSTALL.md
git commit -m "$(cat <<'EOF'
docs(observability): add the missing repo-audit scheduler section

(1) Task & Change
The source design spec's Phase 3 assumed repo-audit already had a
documented bootstrap recipe the way usage-poll does — it didn't. Adds one,
mirroring the existing two sections' style, plus the config-authoring
step this build deliberately does not automate (a real spend-policy
decision — which repos, how often, real billed claude CLI invocations —
left entirely to the machine owner).

(2) Tests created / modified
None — documentation only.

(3) Test results — evidence
python3 ~/.claude/tools/prose_grammar_gate.py INSTALL.md
[paste real output]
EOF
)"
```

---

### Task 5: Live launchd bootstrap — the one irreversible-ish step in this build

**Files:** None (infrastructure state change, not code).

**Interfaces:** None.

**This task is explicitly, transparently a live-infrastructure action.** Per the source design spec: *"Bootstrap both for real... Confirmed acceptable by the owner."* Announce clearly what is being done before doing it — this is not a step to execute quietly.

- [ ] **Step 1: Re-run `install.sh` to pick up every new file from Phases 0-3**

```bash
bash install.sh 2>&1 | tail -40
```
Confirm no errors, and confirm `~/.claude/launchd/com.hdc.claude-agent-loop.obs-ship.plist` exists (from Phase 2) alongside the other two.

- [ ] **Step 2: Bootstrap all three jobs**

```bash
cp ~/.claude/launchd/com.hdc.claude-agent-loop.repo-audit.plist ~/Library/LaunchAgents/
cp ~/.claude/launchd/com.hdc.claude-agent-loop.usage-poll.plist ~/Library/LaunchAgents/
cp ~/.claude/launchd/com.hdc.claude-agent-loop.obs-ship.plist ~/Library/LaunchAgents/

launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.hdc.claude-agent-loop.repo-audit.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.hdc.claude-agent-loop.usage-poll.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.hdc.claude-agent-loop.obs-ship.plist
```

Note: `usage-poll` additionally requires its one-time `--login` authentication step (documented in `INSTALL.md`'s existing "Usage-budget poller" section, step 1) to do anything useful — bootstrapping the job without that step means it runs every 10 minutes and no-ops (same "fails safely, does nothing destructive" posture as repo-audit without its config). This plan does NOT perform that interactive browser-login step — it requires a human at a real browser, out of scope for an agentic session. State this explicitly in the report.

- [ ] **Step 3: Verify all three are loaded**

```bash
launchctl list | grep -i "claude-agent-loop\|hdc"
```
Expected: all three job labels present (`com.hdc.claude-agent-loop.repo-audit`, `.usage-poll`, `.obs-ship`).

- [ ] **Step 4: Tail each job's log path once, immediately after bootstrap, to confirm no immediate crash loop**

```bash
tail -5 /tmp/com.hdc.claude-agent-loop.obs-ship.out.log /tmp/com.hdc.claude-agent-loop.obs-ship.err.log 2>/dev/null
tail -5 /tmp/com.hdc.claude-agent-loop.usage-poll.out.log /tmp/com.hdc.claude-agent-loop.usage-poll.err.log 2>/dev/null
tail -5 ~/.claude/metrics/audit/logs/repo-audit.out.log ~/.claude/metrics/audit/logs/repo-audit.err.log 2>/dev/null
```
`repo-audit`'s logs won't exist yet (it's calendar-scheduled for 03:17, not `RunAtLoad`) — that's expected, not a failure. `obs-ship`/`usage-poll` are interval-scheduled with `RunAtLoad: true`, so they should have fired at least once within a minute or two of bootstrap — confirm their logs show the expected, already-known-and-documented behavior (obs-ship: retry-and-fail against the unreachable OTLP endpoint, per Phase 2's final review's own I3 finding, now with more accurate INSTALL.md documentation; usage-poll: a login-redirect no-op per its own documented behavior, since the `--login` step wasn't run).

- [ ] **Step 5: No commit** — this task changes live launchd state, not repo content. Report the verification output from Steps 3-4 in full.

## Self-review checklist

- [x] Every spec requirement for Phase 3 (source spec lines 205-239) is covered, with 2 documented corrections this plan's own research found: the missing INSTALL.md repo-audit section (design decision 5) and the missing alerting volume mount (design decision 4).
- [x] The one genuinely irreversible-ish action (launchd bootstrap) is isolated into its own task, announced transparently, and deliberately does NOT bundle in a spend-policy decision (the audit config) that isn't this plan's to make.
- [x] No fabricated dashboard/alert content — every panel and rule traces to a real field this build actually emits, with honest "no data yet" or "no metric yet" callouts where that's true (subagent-fanout-depth's `agent_id` gap, cost-per-day's missing metric).
