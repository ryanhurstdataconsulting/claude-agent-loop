# claude-agent-loop-starter

A self-contained, portable Claude Code environment for VS Code: a curated set
of skills, an agent, tools, plugins, MCP specs, and a generic **Resource
Loop**, packaged so any machine can be configured the same way in one command.

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
| `skills/` | 10 | Process and domain skills: `resource-loop`, `token-efficiency`, and the self-configuring `environment-bootstrap`, plus `data-visualization`, `visual-hierarchy-layered-charts`, `explain-code`, `excalidraw-diagram`, `document-render`, `tauri-desktop-dev`, and `aws-local-emulation`. |
| `agents/` | 1 | `sql-safety-reviewer` — a read-only SQL safety gate. |
| `tools/` | 11 | Python and shell helpers (registry linter, grammar gate, secret/PII scrub gate, git and environment preflights, an SSH-tunnel keepalive, dev-server orchestration, background build-watch, a transcript distiller, and coverage/canary checkers), plus a `templates/` directory. |
| `registry/` | index + 25 guides | The resource registry the Resource Loop reads: `REGISTRY.md`, `TRIGGERS.md`, `guides/`, and `candidates/`. |
| `hooks/` | 1 | `inject-resource-loop.sh` — the SessionStart hook. |
| plugins | 11 | `superpowers` plus the ten VoltAgent subagent-catalog categories, from two marketplaces (`claude-plugins-official`, `voltagent-subagents`). |

Into `~/.claude/settings.json` (merged, never clobbered): the SessionStart
hook entry, the 11-plugin `enabledPlugins` map, and the two marketplace
registrations.

Into `~/.claude/CLAUDE.md` (appended between `<!-- BEGIN AGENT-LOOP -->`
sentinels): the operating directives — the Resource Loop protocol, the
token-and-context discipline, the grammar standard, the data-visualization
directive, and a pointer to subagent routing.

**Not installed:** any secret, any hostname, or a live database MCP
registration. Those ship as *specs* under `payload/mcp-specs/`, which you wire
up yourself with your own credentials — the `environment-bootstrap` skill
walks you through it. See `payload/mcp-specs/postgres-readonly.md`.

## The Resource Loop in 60 seconds

The Resource Loop is a start-of-session habit that keeps the environment
self-aware: before it starts your first task, Claude checks what tools
already exist so it reaches for them instead of rebuilding them.

A SessionStart hook injects a compact **registry index** into the session.
The `resource-loop` skill then runs four steps:

1. **MATCH** — compare your task against the registry (by task shape, not
   just keywords).
2. **ANNOUNCE** — state, in one line, which resource it is deploying, or that
   there was no match and it is proceeding bare.
3. **GAP** — when a recurring need has no matching resource, file a candidate
   stub for review (it never auto-creates one).
4. **ROUTE** — dispatch subagents at the right model tier: planning at the
   session model, creation-heavy work to Opus, and mechanical work to Sonnet
   (or Haiku for trivial probes).

The payoff: less duplicated work, a visible announcement of what is in play,
and a growing catalog of reusable resources. The full mechanics are in
`ARCHITECTURE.md`.

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
- **`ARCHITECTURE.md`** — the component diagram, the three layers, the
  resource categories, and the model-routing table.
- **`SECURITY.md`** — what the installer will and will not touch, and the
  secrets/PII posture.
