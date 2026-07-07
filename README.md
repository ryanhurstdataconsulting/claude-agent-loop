# claude-agent-loop

A self-contained, portable Claude Code environment: a curated set of skills, an
agent, tools, plugins, MCP specs, and a self-learning **Resource Loop**,
packaged so any machine can be configured the same way in one command. The loop
does not just deploy resources — it measures every task, scores the outcome, and
acts on that history under a hard safety floor. See **`LEARNING.md`** for how
that works.

## Quickstart

```bash
bash install.sh
```

Then, in Claude Code, run:

```
/environment-bootstrap
```

That inspects your machine, asks a few questions, and tailors the registry,
your `CLAUDE.md`, and the database/MCP templates to your stack. Restart Claude
Code (or run `/hooks` to reload), give it a task, and you should see a line
that begins with `Resource Loop —`. That is the environment working.

The installer is **idempotent** — safe to run twice — and it **merges** into
your existing config rather than overwriting it. It backs up your
`settings.json` and `CLAUDE.md` once, to `*.bak-agentloop`, before it changes
anything.

## What gets installed

Into `~/.claude/`:

| Resource | Count | What it is |
|---|---|---|
| `skills/` | 11 | Process and domain skills: `resource-loop`, `theme-assessment`, `token-efficiency`, and the self-configuring `environment-bootstrap`, plus `data-visualization`, `visual-hierarchy-layered-charts`, `explain-code`, `excalidraw-diagram`, `document-render`, `tauri-desktop-dev`, and `aws-local-emulation`. |
| `agents/` | 1 | `sql-safety-reviewer` — a read-only SQL safety gate. |
| `tools/` | 22 | Python and shell helpers: the learning tools (metrics harvester, task scorer, `SCALES.md`/`HEURISTICS.md` linters, the heuristics engine, the pending-themes check, the visibility classifier, and the autocommit/rollback/digest/promote scripts), plus the carried set (registry linter, grammar gate, secret/PII scrub gate, git and environment preflights, an SSH-tunnel keepalive, background build-watch, a transcript distiller, and coverage/canary checkers), plus `templates/` and `tests/`. |
| `registry/` | index + 25 guides | The resource registry the Resource Loop reads: `REGISTRY.md`, `TRIGGERS.md`, `guides/`, and `candidates/`. |
| `hooks/` | 3 | `inject-resource-loop.sh` (SessionStart), `harvest-metrics.sh` (SubagentStop + SessionEnd), and `precompact-event.sh` (PreCompact). |
| `learning/` | 4 seeds | The self-learning state: `SCALES.md`, `HEURISTICS.md`, `LOOP_THEMES.md`, and `CLIENT_MARKERS.txt`, copied once from the shipped seeds and then kept local-only (never published). |
| plugins | 11 | `superpowers` plus the ten VoltAgent subagent-catalog categories, from two marketplaces (`claude-plugins-official`, `voltagent-subagents`). |

Into `~/.claude/settings.json` (merged, never clobbered): the four hook groups
(SessionStart, SubagentStop, SessionEnd, PreCompact), the 11-plugin
`enabledPlugins` map, and the two marketplace registrations.

Into `~/.claude/CLAUDE.md` (appended between `<!-- BEGIN AGENT-LOOP -->`
sentinels): the operating directives — the Resource Loop protocol, the
token-and-context discipline, the grammar standard, the data-visualization
directive, and a pointer to subagent routing.

**Not installed:** any secret, any hostname, or a live database MCP
registration. Those ship as *specs* under `payload/mcp-specs/`, which you wire
up yourself with your own credentials — the `environment-bootstrap` skill
walks you through it. See `payload/mcp-specs/postgres-readonly.md`.

## The Resource Loop in 60 seconds

The Resource Loop is a closed, self-learning loop that runs for every task:
before Claude starts, it checks what resources already exist so it reaches for
them instead of rebuilding them — and after the work is done, it measures the
result and acts on what it learns.

A SessionStart hook injects a compact **registry index** into the session. The
`resource-loop` skill then runs six steps:

1. **MATCH** — compare your task against the registry (by task shape, not just
   keywords).
2. **ANNOUNCE** — state, in one line, which resource it is deploying, or that
   there was no match and it is proceeding bare. (When a recurring need has no
   resource, it files a candidate stub for review — it never auto-creates one.)
3. **ROUTE** — dispatch subagents at the right model tier: planning at the
   session model, creation-heavy work to Opus, and mechanical work to Sonnet
   (or Haiku for trivial probes).
4. **EXECUTE** — do the work while three hooks passively harvest objective
   metrics (tokens, cache efficiency, tool errors, tests, duration).
5. **SCORE** — record a short subjective self-score of the outcome.
6. **LEARN** — evaluate a rulebook of heuristics over the metric history and act
   on what fired: improve a resource now, note a cross-task theme, or do nothing
   — logging the decision either way.

Underneath those steps sit the learning layers: a local-only **metrics** store,
ordinal **scoring** scales, a cross-task **theme** log, a **heuristics** rulebook,
and a gated **autonomy** path that commits the loop's own improvements under a
hard safety floor. All of it is explained in **`LEARNING.md`**; the full
mechanics are in `ARCHITECTURE.md`.

The payoff: less duplicated work, a visible announcement of what is in play, a
growing catalog of reusable resources, and a system that measures whether its
own choices worked.

## Making it yours

This bundle ships generic. The `environment-bootstrap` skill is what turns it
into *your* setup: it inspects your OS, editor, languages, cloud CLIs, and
database clients; interviews you about what you build and which databases you
touch; then tailors the registry (pruning what you don't need, enabling what
you do), appends a personalized block to your `CLAUDE.md`, and fills in the
database/MCP templates with your own connection details. Run it once after
install, and again any time your setup changes.

The bundle is DBA-friendly out of the box — a read-only SQL safety reviewer, a
read-only Postgres/MySQL MCP template, and an SSH-tunnel keepalive are
included — but none of it is required if that is not your work; the
interview simply skips or prunes what does not apply.

## Documentation in this folder

- **`README.md`** (this file) — what it is and how to start.
- **`INSTALL.md`** — the manual, step-by-step fallback, plus exactly what the
  installer changes and how to undo it.
- **`ARCHITECTURE.md`** — the component diagram, the three layers, the resource
  categories, the metrics store contract, the autonomy mechanics, and the
  model-routing table.
- **`LEARNING.md`** — the self-learning layer: what "learning" means here,
  objective metrics, subjective scores, themes, heuristics, and the gated
  autonomy path.
- **`SECURITY.md`** — what the installer will and will not touch, the secrets/PII
  posture, and the autonomy residual risks.
