# ARCHITECTURE

How this environment fits together: one runtime loop, backed by a static
registry, layered under a cascade of instruction files, with a bootstrap skill
that tailors all three to your machine. Everything below maps to real files in
`payload/`.

---

## Component flow

```
  SESSION STARTS
        │
        ▼
  ┌───────────────────────────────────────────────┐
  │ SessionStart hook                              │   payload/hooks/
  │ inject-resource-loop.sh                        │     inject-resource-loop.sh
  │  • prints the Resource Loop directive          │
  │  • cats the registry index inside              │
  │    <resource-loop> … </resource-loop>          │
  │  • ADDITIVE-ONLY: always exits 0               │
  └───────────────────────┬───────────────────────┘
                          │ injects index + directive into context
                          ▼
  ┌───────────────────────────────────────────────┐
  │ resource-loop  (skill)                         │   payload/skills/
  │                                                │     resource-loop/
  │   MATCH ──► ANNOUNCE ──► GAP ──► ROUTE          │
  └───┬─────────┬──────────┬────────────┬──────────┘
      │         │          │            │
      ▼         ▼          ▼            ▼
   registry  one-line   candidate    subagents by
   lookup    "Resource  stub filed   model tier
             Loop —"    for review   (see table)
      │                    │
      │                    ▼
      │            registry/candidates/
      ▼
  ┌───────────────────────────────────────────────┐
  │ RESOURCES it reaches for                       │
  │  skills · agent · tools · plugins · MCP specs  │
  └───────────────────────────────────────────────┘
```

If the registry file is unreadable, the hook still prints the directive and
exits 0 — a broken registry degrades to directive-only, never to a failed
session start.

---

## The bootstrap skill — tailoring the generic bundle to you

Everything above is generic on first install: the registry lists resources
that *might* apply to you, and the `CLAUDE.md` block carries only
machine-global defaults. The **`environment-bootstrap`** skill closes that
gap in four phases — **EXPLORE → INTERVIEW → TAILOR → VERIFY**:

1. **EXPLORE** — inspect the machine read-only: OS, shell, editor, language
   runtimes, package managers, cloud CLIs, and database clients.
2. **INTERVIEW** — ask only what EXPLORE could not answer, one question at
   a time: what you build, which databases you reach and how, which cloud
   providers, and any compliance constraints (read-only production, PII you
   must never log).
3. **TAILOR** — write the answers back: prune registry rows you do not need
   and enable the ones you do, append a personalized block to `CLAUDE.md`
   below the managed one, and fill in the database/MCP templates with your
   real host, port, and tunnel details (credentials go to `secrets.env`,
   never into a tracked file).
4. **VERIFY** — run the environment and git preflights, confirm the
   SessionStart hook fires, and re-run the registry linter.

Run it once right after `install.sh`, and again any time your setup changes —
it updates in place rather than starting over.

---

## The three layers

### 1. Registry layer — the static catalog

The source of truth for "what resources exist." All under
`payload/registry/`:

- **`REGISTRY.md`** — a compact one-line-per-resource index (the hook injects
  this). Grouped into superpowers, skills, agents, MCPs, and tools.
- **`TRIGGERS.md`** — a keyword / file-glob → resource shortcut map that
  accelerates the MATCH step.
- **`guides/`** — 25 per-resource guides plus `_TEMPLATE.md`. Each guide carries
  the why, the when-to-deploy triggers, the interface, and composition notes.
- **`candidates/`** — proposed resources awaiting approval; the GAP step writes
  stubs here.

The linter `payload/tools/lint_registry.py` checks the index against the guides
and must stay green after any edit.

### 2. Runtime loop layer — the per-session behavior

The registry is inert until a session runs the loop over it:

- **`payload/hooks/inject-resource-loop.sh`** injects the index every session
  (wired through `settings.json → hooks.SessionStart`).
- **`payload/skills/resource-loop/`** is the skill that executes
  MATCH → ANNOUNCE → GAP → ROUTE against the injected index.

### 3. Doc-cascade layer — the instruction precedence

The starter directives live in a cascade, highest precedence last:

```
  ~/.claude/CLAUDE.md            ← machine-global (this export appends here,
     (AGENT-LOOP block)            between the sentinels; environment-bootstrap
                                   appends a personalized block below it)
        ▼
  <workspace>/CLAUDE.md          ← your own per-workspace conventions
        ▼
  <project>/CLAUDE.md            ← the specific project's operating manual
        ▼
  session-level user instruction ← always wins
```

This export installs only the machine-global block:
`payload/fragments/CLAUDE.starter.md` (the Resource Loop protocol, the
token-and-context discipline, the grammar standard, the data-visualization
directive, and the subagent-routing pointer). Your workspace and project
layers travel with your own repositories.

---

## Resource categories (accurate to `payload/`)

| Category | Count | Location | Examples |
|---|---|---|---|
| Skills | 10 | `payload/skills/` | `resource-loop`, `token-efficiency`, `environment-bootstrap`, `data-visualization`, `document-render`, `tauri-desktop-dev` |
| Agents | 1 (+1 from the plugin catalog) | `payload/agents/` | `sql-safety-reviewer` (bundled); `cloud-architect` is also available, sourced from the VoltAgent plugin catalog rather than a bundled file |
| Tools | 11 | `payload/tools/` | `lint_registry.py`, `prose_grammar_gate.py`, `secret_pii_scrub_gate.py`, `git_safety_preflight.py`, `ssh_tunnel_keepalive.sh` |
| Plugins | 11 | `settings.json` | `superpowers`, 10 VoltAgent categories |
| MCP specs | 3 files | `payload/mcp-specs/` | `postgres-readonly` (read-only Postgres/MySQL spec), `global-mcps` (`playwright`, `google_workspace`), `secrets.env.template` |

MCP servers are the one category shipped as **specs, not wired config**: the
database server needs your own credentials and, often, an SSH tunnel, so
`payload/mcp-specs/` documents how to register it rather than doing it for you.

---

## How resources are discovered and added

**Discovered** at runtime: the hook injects `REGISTRY.md`; the loop's MATCH step
consults it (and `TRIGGERS.md` for keyword shortcuts) to pick a resource for the
task at hand.

**Added** deliberately, never silently:

1. The GAP step notices a recurring need (≥ 2 sessions, or ≥ 3× in one session)
   with no matching resource and files a stub in `registry/candidates/`.
2. You approve it; the resource is built (a new skill, agent, or tool).
3. A row is added to `REGISTRY.md`, a guide is written under `guides/`, and any
   keyword shortcut is added to `TRIGGERS.md`.
4. `lint_registry.py` is run to confirm the index and the guides agree.

---

## Metrics store contract

The Resource Loop records one JSON object per line to a monthly shard at
`~/.claude/metrics/YYYY-MM.jsonl` (`schema: 1`). The harvester
(`payload/tools/harvest_metrics.py`) and the PreCompact hook are the only
writers; everything downstream is a reader.

| Field | Meaning |
|---|---|
| `kind` | `task` · `session` · `score` · `learn` · `compaction` |
| `task_id` | the join key: `agent-<id>` for a task, `session-<sid>` for a session |
| `resources_source` | how `resources_deployed` was attributed (see below) |

**Kinds.** A `task` record rolls up one subagent transcript; a `session`
record rolls up the main thread and carries `tasks_harvested`; a `compaction`
record is one line per PreCompact event; `score` and `learn` records (P3 / P6)
attach a subjective self-score and a heuristic action to an existing task.

**Join.** Records are correlated by `task_id`. A `score` or `learn` record
shares the `task_id` of the task it annotates, so a consumer joins them on that
key.

**Last-wins (the append-only rule).** Records are keyed by `(task_id, kind)`
and are **only ever appended** — a record is never rewritten in place. When a
transcript grows, or when the SessionEnd backfill enriches a task, a fresh
REPLACEMENT record is appended after the stale one. **Consumers MUST take the
LAST record per `(task_id, kind)`** and ignore every earlier copy. This keeps
each write a single atomic append and preserves the full history.

**`resources_source`.** Every task and session record states where its
`resources_deployed` list came from:

- `task` — parsed from the subagent's own ANNOUNCE line;
- `session` — parsed from the main thread's ANNOUNCE (session records);
- `session-backfill` — copied from the session's ANNOUNCE onto a subagent that
  never announced. Subagents rarely announce, so most task records are enriched
  this way: at SessionEnd, once the session's `resources_deployed` is known, the
  harvester re-emits a replacement task record (last-wins) for every subagent
  whose own announce was empty. A subagent that announced its own resources
  keeps them and is left untouched.

**Not publishable — local-only by design.** Metrics records embed project
slugs and git branch names that identify client work, and `redact()` scrubs
credentials only — not those identifiers. The `metrics/` directory is untracked
for exactly this reason. A metrics record MUST NOT be copied into any tracked or
publishable file without first passing the P5 visibility classifier
(`classify_visibility.py`); default-deny routes anything CLIENT or UNSURE back
to local-only files.

---

## Model-routing table

The ROUTE step dispatches subagents at the tier that fits the work:

| Task shape | Model tier | Why |
|---|---|---|
| Planning, architecture, review | session model | Keeps continuity with the driving session. |
| Creation-heavy (new skill / agent / feature) | `opus` | Highest-quality generation; Opus creators sub-delegate the mechanical parts. |
| Mechanical (extraction, file sweeps, lint fixes, probes) | `sonnet` | Fast and cheap for well-scoped, deterministic work. |
| Trivial probes | `haiku` | Lowest-latency for a one-shot check. |

The rule of thumb baked into the loop: **delegate by default.** Decompose a
non-trivial task and fan out independent subtasks as parallel subagents in a
single message, each briefed with the grammar standard and the Resource Loop
directive.
