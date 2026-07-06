---
name: environment-bootstrap
description: Run once after install (and any time your setup changes) to tailor this Claude Code environment to YOUR machine. It inspects the system, interviews you, then personalizes ~/.claude/CLAUDE.md, the resource registry, and the database/MCP templates. Triggers - "set me up", first run, a new machine, a new database or cloud account, "reconfigure my environment".
---

# Environment Bootstrap

Turn the generic starter into a setup fitted to this user's machine, stack, and
databases. Four phases: **EXPLORE → INTERVIEW → TAILOR → VERIFY**. It is
re-runnable — run it again whenever the environment changes; it updates in place
rather than starting over. Announce a checklist item per phase.

## Phase 1 — EXPLORE (no questions yet)

Inspect the machine read-only and record what you find. Do NOT guess; run the
checks and note which succeed:

- OS + arch (`uname -sm`), shell (`echo $SHELL`). On macOS, note the system
  bash is 3.2 — keep any scripts portable.
- Editor: VS Code present (`code --version`) and the Claude Code extension
  installed?
- Languages/runtimes: `python3 --version`, `node --version`, `go version`,
  `rustc --version`, `java -version` — record which exist.
- Package managers: `brew`, `npm`/`pnpm`/`yarn`, `pip`/`uv`, `cargo`.
- Cloud CLIs: `aws sts get-caller-identity`, `gcloud config list`, `az account
  show` — which are installed and authenticated.
- Database clients: `psql`, `mysql`, `mongosh`, `sqlplus`, `sqlite3`.
- Existing config: what already lives in `~/.claude/` (skills, registry, a
  `CLAUDE.md`), so you extend rather than clobber.

Summarize the findings back to the user in one compact block before asking
anything.

## Phase 2 — INTERVIEW (one question at a time)

Ask only what EXPLORE could not answer. One question per turn, multiple-choice
where possible; never batch. Cover:

1. **Primary work** — what do you build or operate? (data/DBA · backend · web ·
   infra/devops · data science · other)
2. **Databases** — which engines, and how do you reach them? (local · SSH
   tunnel · cloud endpoint · none). For each: is production access read-only?
3. **Cloud** — which providers, and do you provision infrastructure
   (Terraform/IaC)?
4. **Languages/frameworks** you work in daily.
5. **Constraints** — any compliance rules? (read-only production, PII you must
   never log, a secrets policy)
6. **Model routing** — default to session model for planning, Opus for creation,
   Sonnet/Haiku for mechanical work? (recommend yes)

If the user is unsure on any point, offer a sensible default and move on.

## Phase 3 — TAILOR (write the config)

Apply the answers:

- **CLAUDE.md** — append a personalized block (between its own sentinels, BELOW
  the managed `<!-- BEGIN AGENT-LOOP -->` block) to `~/.claude/CLAUDE.md`
  capturing the user's domain, database safety rules (e.g. read-only production →
  wrap every connection in a read-only transaction with a statement timeout),
  secrets/PII policy, and model-routing defaults.
- **Registry** — enable the rows that fit and prune the rest (e.g. keep
  `sql-safety-reviewer`, `postgres-readonly`, `ssh-tunnel-keepalive` for a DBA;
  drop `tauri-desktop-dev` if they never build desktop apps). Anything they need
  that has no resource → file a candidate in `~/.claude/registry/candidates/`;
  never auto-build it.
- **Database MCP** — fill the `postgres-readonly` MCP registration (or the MySQL
  variant) with their host/port/tunnel from the interview. Put credentials in
  `secrets.env` (gitignored), NEVER in the registration or any tracked file.
  Confirm the connection is read-only.
- **Subagents** — name the VoltAgent categories that fit their domain and how to
  enable them (`/plugin`).
- Run `python3 ~/.claude/tools/lint_registry.py` after any registry edit.

## Phase 4 — VERIFY

- Run the env and git preflights (`python3 ~/.claude/tools/env_tooling_preflight.py`,
  `python3 ~/.claude/tools/git_safety_preflight.py`) and report gaps (a missing
  tool, no git identity).
- Confirm the SessionStart hook fires: the next session should print a
  `Resource Loop —` line. If it does not, tell the user to open `/hooks` once (or
  restart) to reload the config.
- Summarize what you configured and what you deferred to candidates. Remind the
  user they can re-run this skill anytime their setup changes.

## Safety

Read-only exploration only — never write outside `~/.claude/` without saying so
first. Never put a real credential in the registry or any tracked file; secrets
belong in `secrets.env` (gitignored). Scan anything you hand off with
`secret-pii-scrub-gate` first.
