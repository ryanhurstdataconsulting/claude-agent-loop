# Agent Observability Layer — Phase 0: Native Telemetry + Inert Backend Config — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn on Claude Code's own built-in OTel export (metrics + logs) pointed at `localhost:4318`, and ship an inert `docker-compose.yml` for the `grafana/otel-lgtm` all-in-one backend — neither started nor required by anything yet, just present so Phase 3's dashboards have something to provision into once a human runs `docker compose up`.

**Architecture:** Two independent, small changes. Task 1 is a hand-edit to the real, live `~/.claude/settings.json` (a gated lane, explicitly owner-authorized for this build per the source spec) adding an `env` block. Task 2 is a new, never-executed compose file in `payload/observability/`.

**Tech Stack:** No code. JSON config + a YAML compose file.

## Global Constraints

- **`~/.claude/settings.json` is the real, live settings file on this machine** — not a template, not `payload/fragments/settings.fragment.json`. This edit is a genuine, immediate change to how every future Claude Code session on this machine behaves (it starts emitting OTel metrics/logs on every session once this lands). Per the source spec: "Exact variable/metric names — verify against current Claude Code monitoring docs at implementation time; the mechanism (OTLP metrics + logs via env config) is the stable part." That verification happened in this plan's own research (see design decision #1 below) — the mechanism and most variable names check out; one variable (`OTEL_RESOURCE_ATTRIBUTES`) is flagged as not officially documented by Claude Code specifically, kept anyway per the documented rationale below.
- **Export target is `http://localhost:4318` — localhost only.** No backend is running. This is explicitly safe and expected to fail silently (Claude Code's own OTel SDK integration handles export failures the same way any OTel SDK does — silently, never blocking the CLI). Nothing in this phase depends on a live backend.
- **`docker-compose.yml` is never run in this plan.** Ship the file, validate its YAML syntax, done. Starting the container is explicitly out of scope for the entire observability-layer build's Phase 0 per the source spec ("Not started as part of this build").

## Design decisions locked in for this plan

1. **Env var verification result** — confirmed via direct research against current Claude Code documentation: `CLAUDE_CODE_ENABLE_TELEMETRY`, `OTEL_METRICS_EXPORTER`, `OTEL_LOGS_EXPORTER`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_EXPORTER_OTLP_ENDPOINT` are all real, current, correctly-named Claude Code telemetry env vars. Value corrections from the source spec's draft: `CLAUDE_CODE_ENABLE_TELEMETRY` value is the string `"1"` (confirmed, matches spec). `OTEL_EXPORTER_OTLP_PROTOCOL` value is `"http/protobuf"` for an HTTP (not gRPC) endpoint (matches spec). `OTEL_RESOURCE_ATTRIBUTES` is flagged as **not enumerated in Claude Code's own documented telemetry variable list** — it's a standard OTel SDK convention that most OTel exporters (including whatever SDK Claude Code's telemetry integration wraps) read regardless of whether the wrapping application's own docs mention it, and worst case it's silently unused, never an error. **Kept in this plan's config anyway** — the identifying metadata (`service.name=claude-code,deployment.environment=hdc-local`) is exactly what distinguishes this machine's Claude Code sessions from any other OTel-emitting source once dashboards exist in Phase 3, and the downside risk of including an unused env var is zero. This is a deliberate, documented risk-free bet, not an oversight.
2. **Default OTel port note**: standard OTel convention is gRPC on 4317, HTTP on 4318. This plan and the whole observability-layer build standardize on 4318 (HTTP) throughout every phase — `obs_ship.py` (Phase 2), this phase's Claude Code env config, and the compose file below all agree on 4318/HTTP. No mixed-protocol risk.

---

### Task 1: `~/.claude/settings.json` — native OTel env block

**Files:**
- Modify: `~/.claude/settings.json` (the real, live file — NOT `payload/fragments/settings.fragment.json`, which only carries hook bindings, not this kind of top-level `env` config)
- Test: manual verification (JSON validity + `claude doctor`-equivalent sanity check, or a direct `python3 -c` load-and-inspect) — no automated test suite covers a live machine's own settings.json content, matching this framework's existing convention for gated-lane hand-edits.

**Interfaces:** None — this is configuration, not code.

- [ ] **Step 1: Read the current live file in full**

Run: `python3 -c "import json; print(json.dumps(json.load(open('/Users/ryanhurst/.claude/settings.json')), indent=2))" | head -60` and read the whole file (it's not large) to confirm the exact current top-level key structure — specifically whether an `"env"` key already exists (if so, this task ADDS to it, never replaces it) and what, if anything, already lives there.

- [ ] **Step 2: Back up the file**

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak-pre-otel-phase0
```

- [ ] **Step 3: Add the env block**

Using Python (safer than manual JSON editing for a live file — guarantees valid JSON out):
```bash
python3 -c "
import json

path = '/Users/ryanhurst/.claude/settings.json'
with open(path) as fh:
    settings = json.load(fh)

env = settings.setdefault('env', {})
env['CLAUDE_CODE_ENABLE_TELEMETRY'] = '1'
env['OTEL_METRICS_EXPORTER'] = 'otlp'
env['OTEL_LOGS_EXPORTER'] = 'otlp'
env['OTEL_EXPORTER_OTLP_PROTOCOL'] = 'http/protobuf'
env['OTEL_EXPORTER_OTLP_ENDPOINT'] = 'http://localhost:4318'
env['OTEL_RESOURCE_ATTRIBUTES'] = 'service.name=claude-code,deployment.environment=hdc-local'

with open(path, 'w') as fh:
    json.dump(settings, fh, indent=2, sort_keys=True)
    fh.write('\n')
print('written')
"
```
(`setdefault` on `'env'` means this is safe to run even if an `env` block already exists with unrelated keys — those are preserved, only the 6 OTel keys are added/overwritten.)

- [ ] **Step 4: Verify**

Run: `python3 -c "import json; d=json.load(open('/Users/ryanhurst/.claude/settings.json')); print(json.dumps(d['env'], indent=2))"` — confirm all 6 keys present with the exact values above, and confirm the file is still valid JSON (the load itself proves this) with nothing else in the file altered (diff against the backup, ignoring the expected `env` addition):
```bash
diff <(python3 -c "import json; d=json.load(open('/Users/ryanhurst/.claude/settings.json.bak-pre-otel-phase0')); d.pop('env', None); print(json.dumps(d, indent=2, sort_keys=True))") \
     <(python3 -c "import json; d=json.load(open('/Users/ryanhurst/.claude/settings.json')); d.pop('env', None); print(json.dumps(d, indent=2, sort_keys=True))")
```
Expected: empty diff (only `env` differs between the two files; everything else is byte-identical once `env` is excluded from both sides).

- [ ] **Step 5: Confirm this doesn't break a live session**

Run any harmless Claude Code CLI invocation this environment supports non-interactively (e.g. `claude --version` or equivalent) to confirm the CLI still starts cleanly with the new env vars present. If no safe non-interactive smoke-test command exists in this environment, state that explicitly rather than skipping verification silently — this step's evidence requirement is "the CLI does not fail to start because of this env block," by whatever means available.

- [ ] **Step 6: No git commit** (this file lives outside any git repo — it's `~/.claude/settings.json`, not `payload/fragments/settings.fragment.json`). Note the change and its backup path in your report; there is nothing to `git add`.

---

### Task 2: `payload/observability/docker-compose.yml` — inert backend config

**Files:**
- Create: `payload/observability/docker-compose.yml`
- Modify: `payload/MANIFEST` (already has `link-dir observability` from Phase 2 Task 4 — confirm this new file lands inside that same linked directory automatically; no new MANIFEST line should be needed, but verify)

**Interfaces:** None.

- [ ] **Step 1: Write the compose file**

```yaml
# docker-compose.yml — inert backend config for the agent-observability-layer
# build. NOT started as part of this build (see the design spec's Phase 0
# section) — this file exists so a human can `docker compose up` once ready,
# at which point Phase 2's obs_ship.py sidecar and this machine's native
# Claude Code OTel export both already point at the ports this brings up.
services:
  otel-lgtm:
    image: grafana/otel-lgtm:latest
    container_name: claude-agent-loop-otel-lgtm
    ports:
      - "4317:4317"   # OTLP gRPC receiver
      - "4318:4318"   # OTLP HTTP receiver (the port every phase of this build uses)
      - "3000:3000"   # Grafana UI
    volumes:
      - ./dashboards:/otel-lgtm/grafana/dashboards
    restart: unless-stopped
```

(`./dashboards` doesn't exist yet — that's Phase 3's deliverable; the volume mount reference here is forward-looking and harmless since this compose file is never started in this plan.)

- [ ] **Step 2: Validate YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('payload/observability/docker-compose.yml'))" 2>&1 || python3 -c "import json,sys; sys.path" ` — if the `yaml` module isn't available, validate via `docker compose config --dry-run -f payload/observability/docker-compose.yml` if `docker`/`docker compose` is installed on this machine (this only parses/validates, does not start anything), or as a last resort confirm no obvious syntax errors by careful visual inspection and note which validation method was actually used in your report.

- [ ] **Step 3: Confirm MANIFEST already covers this file**

Run: `grep -n "link-dir observability" payload/MANIFEST` — confirm the existing entry (from Phase 2 Task 4) is present. Since `link-dir` symlinks the WHOLE directory, this new file is automatically covered with no MANIFEST change needed. Confirm by checking whether `~/.claude/observability/` (if it exists from Phase 2's install) already reflects this new file once `bash install.sh` is re-run, OR simply confirm the directory-level symlink mechanism logically covers a new file added to an already-`link-dir`'d directory without needing to actually re-run install.sh (a symlinked directory automatically reflects new files added inside the real directory — no action needed).

- [ ] **Step 4: Run the full existing test suite to confirm no regression**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -20` — this task touches no code, sanity check only.

- [ ] **Step 5: Commit**

```bash
git add payload/observability/docker-compose.yml
git commit -m "$(cat <<'EOF'
feat(observability): add inert grafana/otel-lgtm docker-compose.yml

(1) Task & Change
Ships the backend config for the agent-observability-layer build's Phase 0
— a single grafana/otel-lgtm service with OTLP receivers on 4317 (gRPC)
and 4318 (HTTP, the port every phase of this build standardizes on) plus
Grafana UI on 3000. Not started as part of this build; Phase 3 will mount
its dashboards-as-code into ./dashboards once that directory exists.

(2) Tests created / modified
None — infrastructure config only.

(3) Test results — evidence
YAML syntax validated (see report for the exact method used on this
machine). bash payload/tools/tests/run_all.sh — no regressions.
EOF
)"
```

- [ ] **Step 6: Push**

```bash
git push origin feat/agent-observability-layer
```

## Self-review checklist

- [x] Both spec requirements for Phase 0 (spec lines 185-204) are covered: the env block (Task 1) and the inert compose file (Task 2).
- [x] The `[assumed]` flag on Claude Code's env var names is resolved via direct research, not left as a guess — see design decision #1, including the one variable (`OTEL_RESOURCE_ATTRIBUTES`) that isn't officially documented but is kept for a stated, risk-free reason.
- [x] Task 1 explicitly distinguishes the LIVE `~/.claude/settings.json` from the repo's `payload/fragments/settings.fragment.json` — these are different files with different purposes, and this plan is unambiguous about which one it touches.
