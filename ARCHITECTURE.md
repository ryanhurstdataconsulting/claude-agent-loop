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
  │ resource-loop  (skill) — the closed loop      │   payload/skills/
  │                                               │     resource-loop/
  │   MATCH     read the registry (+ TRIGGERS)    │
  │   ANNOUNCE  emit the "Resource Loop —" line   │
  │   ROUTE     dispatch subagents by model tier  │
  │   EXECUTE   run work; hooks harvest metrics   │
  │   SCORE     record a self-score               │
  │   LEARN     evaluate heuristics; act + log    │
  └───────────────────────┬───────────────────────┘
                          │ reaches for resources
                          ▼
  ┌───────────────────────────────────────────────┐
  │ RESOURCES it reaches for                      │
  │  skills · agent · tools · plugins · MCP specs │
  └───────────────────────────────────────────────┘

  GAP is a side behavior of MATCH/ANNOUNCE: a recurring need with no
  resource files a registry/candidates/ stub for review — never auto-made.
```

If the registry file is unreadable, the hook still prints the directive and
exits 0 — a broken registry degrades to directive-only, never to a failed
session start.

---

## The role stack — HOOK → AGENT → SKILL → TOOL

MATCH's first move is the **role hop**, the deterministic edge from the HOOK
layer to the AGENT layer:

```
  HOOK   inject-resource-loop.sh directs: run the router on the task
    │
    ▼
  AGENT  route_role.py scores the task against every agents/roles/<role>.md
    │    (routes: phrases; multi-word hit = 2, word hit = 1; below the floor
    │    → "generalist", stated). The winning role's frontmatter declares
    │    skills: and mcps: — no model judgment anywhere on this edge.
    ▼
  SKILL  the role's declared skills become the MATCH shortlist
    │    (each is a skill-library SKILL.md; all remain directly invocable —
    │    the role layer organizes, it never gates)
    ▼
  TOOL   each skill's guide names the leaf executables it drives
         (gates, linters, query packs, preflights, scorers)

  MCP    cross-cut: the role's mcps: are preferred where configured;
         unconfigured ones get an environment-bootstrap nudge, never
         an invented registration.
```

Role files carry harness-compatible `name`/`description` keys too, so a role
is also directly dispatchable as a subagent. `lint_roles.py` enforces the
contract (name == role == filename; every declared skill exists; every
declared MCP has a registry row) exactly the way `lint_registry.py` guards the
index. Adding a role is one file plus a lint run.

---

## The contribution pipeline (fleet feedback)

`loop_contribute.py` closes the loop across installs: local resources built by
the loop (non-symlink entries under `~/.claude/{skills,tools,agents}`) are
detected, gated, measured, summarized, and **auto-pushed to a
`contrib/<date>-<slug>` branch** with the branch link printed. The gates are
default-deny — `classify_visibility` must say GENERIC, the secret/PII scrub
must pass, the grammar gate must pass on markdown — so CLIENT or UNSURE
content never leaves the machine. Packaging happens in a temporary `git
worktree` (the checkout is never disturbed), the MANIFEST line for each
resource is added in the same commit, and `learning/contributed.json` dedups
re-contribution. Pushes never target `main`; merging the pull request is a
human decision; `AGENT_LOOP_CONTRIBUTE=0` disables the pipeline. SessionStart
surfaces a one-line nudge when gate-cleared contributions are pending (the
nudge itself never pushes), and the auto-update hook is the return path — the
fleet pulls merged contributions on its next session.

---

## The repo-audit scheduling layer

A separate subsystem wraps the pre-existing `repo-security-auditor` agent (an
owner-local resource, not bundled by this export) in unattended runs across
many packages. It has **two triggers, both built**: a launchd nightly sweep on
a cadence tiered by how sensitive or fast-moving each package is, and a
GitHub Actions workflow that fires on every push and pull request. Where the
resource loop above is session-shaped — one hook, one skill, driven by a human
starting a session — this layer is calendar- and event-shaped: it runs whether
or not anyone is at the keyboard, so its whole design leans on non-disturbance
and severity-gated surfacing rather than on a human being present to notice
something going wrong.

The nightly path is the complete one, and it is the one diagrammed below. The
Actions path is deliberately reduced — see "The Actions trigger" after the
diagram.

```
  launchd (03:17 daily, off the :00 mark so a fleet does not stampede)
        │
        ▼
  audit_dispatch.py                          payload/tools/audit_dispatch.py
   • resolves the workspace root: --workspace, else audit/config.json's
     `workspace` key, else ~/dev. The plist passes no --workspace at
     all — it is a template shipped verbatim to every machine, and a
     home-relative path baked into it is wrong everywhere else, and
     wrong silently
   • reads audit_store's audit/config.json tiers
   • per package: head_sha() + is_due() — tier interval elapsed AND HEAD
     moved, never audited, or unverifiable all count as due
   • then DRIVES the sweep: one audit_run.sh per due package, in
     sequence, and one closing digest — --dry-run prints the plan and
     invokes nothing
        │ due list (package, reason), longest-overdue first, capped
        ▼
  audit_run.sh <pkg> <store> --key KEY       payload/tools/audit_run.sh
   • throwaway `git worktree`, detached HEAD — the live checkout is
     never read or written
   • headless `claude --agent repo-security-auditor`, scoped to the
     worktree, tool allowlist narrowed to read-only git subcommands
   • secret/PII scrub + grammar gates run on the findings BEFORE any
     branch or commit exists; a credential in a CODE FIX aborts, one in
     the findings doc quarantines into the store instead
   • commits to `audit/security-<date>` in the package's own repo, with
     the audited repo's hooks disarmed; NEVER pushes
        │ run-log JSON, one per package per night, at runs/<key>/
        ▼
  audit_store.py                             payload/tools/audit_store.py
   • ~/.claude/metrics/audit/{runs,findings,digests,quarantine,logs}
   • its own nested git repo, no remote, scoped .gitignore, and
     commit_paths() as the only writer of its history — see the
     amended metrics store contract below
        │
        ▼
  audit_digest.py                            payload/tools/audit_digest.py
   • severity-gated: Critical/High, a blocked/failed/quarantined
     verdict, or findings that could not be parsed at all interrupt
     immediately; everything else waits
   • --nudge surfaces an unread digest once at SessionStart, the same
     self-consuming shape as the loop-close digest nudge
```

**The chain is wired end to end.** The launchd job's `ProgramArguments`
invoke `audit_dispatch.py`, and that one process now owns the whole night:
select the due packages, run `audit_run.sh` against each in turn, render one
digest, and fire the alerts. One package failing never aborts the rest.
`--dry-run` prints exactly what would happen and invokes nothing, so the job
can be exercised without spending a cent. What remains reserved for the owner
is loading the job (`launchctl bootstrap`) and the first live run, which
spends real budget against a real repository.

**The Actions trigger is built, and it is honest about being partial.**
`payload/templates/repo-security-audit.yml` is a generic workflow template —
copy it to `.github/workflows/` in any repository, no edits needed. It fires
on push and pull request and runs the four categories a checkout can answer:
dependency CVEs, application-layer SAST, secrets in tracked code, and CI/CD
readiness. It does not attempt the other two, and the reason is structural
rather than an omission. Untracked-PII and gitignore compliance is
unanswerable in CI by construction — a checkout contains only tracked files,
so the very files that category exists to find are the ones a runner can never
be shown. And `secrets.env` symlink integrity is a property of a developer's
machine, which does not exist on a runner at all. Every run therefore states
its own limits in one fixed sentence, in the job summary and in a
pull-request comment, and a fixed-string test
(`payload/tools/tests/test_actions_template.sh`) pins that sentence so a later
edit cannot quietly soften or drop it. A green check that is silently partial
is worse than no check: it retires the question.

The workflow's authority is deliberately smaller than the nightly runner's.
It holds `contents: read`, is granted no file-writing tool, and creates no
commit, no branch, and no findings document — the nightly path's output is a
reviewable branch in the package's own repository, and this path's output is a
comment. Findings never turn the check red; failing a build on them is a
decision to take once signal quality is proven over real runs, not a default
to ship with. The one thing it needs, an `ANTHROPIC_API_KEY` repository
secret, is a manual owner step by design: distributing an API key across
repositories has a real cost and a real blast radius, and it sits outside a
workflow file's authority. Without the secret — and on pull requests from
forks, where GitHub withholds secrets — the job reports the audit as skipped
and exits green rather than going red on an infrastructure fact.

**The store key is passed, never re-derived.** `audit_dispatch` hands
`audit_run.sh` the package's own `config.json` string with `--key`, and that
string is the path the run log is written under. A package key is a
workspace-relative path, so a runner that derived its own key from
`basename <package-path>` wrote state one level shallower than
`last_state()` read it — every nested package then reported "never audited"
every night, at the cost of a full agent session per package per night.
Passing the key makes the two sides the same string by construction.

**Two safety rulings recorded here, not re-litigated.** First, the secret
gate is split by what a hit means. Over the auditor's code fixes a hit aborts
the commit, because an unattended agent must never introduce a credential
into a client's source. Over `SECURITY_AUDIT.md` a hit *quarantines*: quoting
the credential it found is a findings document's job, so the most valuable
audits are exactly the ones guaranteed to trip the gate, and discarding them
with the worktree would mean the layer structurally cannot deliver its best
output. The document is copied to `audit/quarantine/<key>/` in the local-only
store and the package repository receives nothing. Second, git calls run with
the audited repository's hooks disarmed. A worktree shares `.git/hooks` with
the checkout it came from, so `worktree add`, `checkout`, `add`, `commit`, and
`branch -D` all execute whatever hooks that repository happens to ship —
unattended, at 03:17, in a script whose entire purpose is to leave it
undisturbed. Three defences, in order of what each actually stops: every such
call passes `-c core.hooksPath=/dev/null`, so git finds no hook of any name
and runs none, including the `post-checkout`, `post-commit`, and
`reference-transaction` hooks that no command-line flag can suppress;
`--no-verify` on the commit holds the line for a git old enough to ignore
`core.hooksPath`, and stops a `pre-commit` that stages files of its own from
putting unscanned content into the index the gates had just cleared; and each
call is backgrounded, waited on, and bounded by `AUDIT_GIT_TIMEOUT`, because
bash defers a trapped signal until the current foreground command returns —
one hanging hook would otherwise make the run un-interruptible and leave a
worktree registered in the developer's repository indefinitely.

**A decision recorded here, not re-litigated: the git tool allowlist.**
`audit_run.sh` narrows the headless agent's Bash allowlist to read-only git
subcommands named one at a time (`git log`, `git diff`, `git ls-files`, `git
status`, `git rev-parse`) instead of the blanket `Bash(git:*)` the original
design spec specified. `--add-dir` constrains the file-editing tools to the
worktree, but it has no effect on `Bash`, and the live package checkout sits
one `git rev-parse --git-common-dir` away from inside that worktree — a
blanket git allowlist would let an unattended agent, reading a package's own
(potentially adversarial) content, run `checkout`/`reset`/`push` against the
developer's real repository, with nothing but prompt text standing in the
way. Prompt text is not a control for an unattended auditor. The controller
ruling on this: the spec is amended, not the script loosened — the
`2026-07-31-repo-security-audit-scheduling-design.md` spec (local-only, kept
outside this repo) has been updated to match the shipped allowlist, which is
authoritative.

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
  this). Grouped into superpowers, skills, agents, MCPs, and tools; each row
  also carries a `domain` column (one of 10 VoltAgent-matching values) that
  the MATCH step uses to narrow its candidate set before it reads triggers.
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
- **`payload/skills/resource-loop/`** is the skill that executes the six-step
  closed loop — MATCH → ANNOUNCE → ROUTE → EXECUTE → SCORE → LEARN — against the
  injected index, with GAP a side behavior that files a `candidates/` stub when a
  recurring need has no resource.
- **`payload/hooks/harvest-metrics.sh`** (SubagentStop, SessionEnd) and
  **`payload/hooks/precompact-event.sh`** (PreCompact) passively record the
  objective metrics the SCORE and LEARN steps read back. See the metrics store
  contract below, and `LEARNING.md` for the whole self-learning layer.
- **`payload/hooks/context-budget.sh`** (PostToolUse) watches the session's
  context-window occupancy from the transcript tail and steers the agent to a
  durable pause point — one warning at 70% of the token budget, then a repeating
  checkpoint directive from 85% until a resume brief exists on disk. It acts
  *before* compaction; `precompact-event.sh` records and escalates *after* it.
- **`payload/hooks/usage-budget.sh`** (PostToolUse) reads a small JSON cache
  that an out-of-band launchd poller (`usage_poll.py`) refreshes every ~10
  minutes with the account's session-limit and weekly-limit percentages, and
  steers the agent to a durable pause point before either Claude subscription
  ceiling is exhausted — one warning at 70% of the higher percentage, then a
  repeating checkpoint directive from 85% until a checkpoint file exists on
  disk. It reads only the cache (never the network), and it stays silent
  whenever that cache is missing or stale. Kill switch: `USAGE_BUDGET_DISABLE=1`.
- **`payload/tools/bb_write.py` / `bb_read.py` / `bb_gc.py`** (backed by
  `bb_common.py`) are the sanctioned access path to
  `~/.claude/state/blackboard.db` — a single-file, WAL-mode SQLite store for
  cross-agent shared state (hints/results, a phase-transition event log,
  consensus votes, resumable plan checkpoints, and large-payload artifact
  pointers) that sits alongside, not instead of, the metrics `*.jsonl`
  ledger: metrics is the permanent record, the blackboard is working state.
- **`payload/tools/worktree_exec.py`** creates and merges back a per-step
  git worktree at `~/.claude/worktrees/<task_id>/<step_id>/` for any EXECUTE
  step whose plan (Phase 1 schema) marks `"worktree": true` — opt-in per
  step. Merge-back is a normal `git merge` in that step's own project repo,
  gated on the step's recorded `return.ok`, not on `loop_autocommit.sh`
  (which only ever commits to this framework repo or `~/.claude`).
- **`payload/tools/consensus_vote.py`** records and tallies a 2-of-3
  consensus vote for a gated action (`git push`, publish/release, an AWS
  mutation) into the blackboard's `consensus_state` table — a queryable
  audit trail, not an enforcement mechanism; nothing in this codebase
  currently blocks any of those three action types on a vote tally.
- **`payload/coordination/`** (`claims.json`, `handoffs.json`,
  `results.json`, `agents.json`) — four filenames reserved for a future
  multi-machine GNAP-style coordination protocol, per the agent-loop-v2
  design spec's Phase 7. Each file holds only
  `{"_reserved": "not implemented — see agent-loop-v2-design.md §7"}`.
  Nothing reads or writes them yet — this section only exists so a future
  implementer doesn't have to pick these names under time pressure.

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
| Skills | 11 | `payload/skills/` | `resource-loop`, `theme-assessment`, `token-efficiency`, `environment-bootstrap`, `data-visualization`, `document-render`, `tauri-desktop-dev` |
| Agents | 1 (+1 from the plugin catalog) | `payload/agents/` | `sql-safety-reviewer` (bundled); `cloud-architect` is also available, sourced from the VoltAgent plugin catalog rather than a bundled file |
| Tools | 22 | `payload/tools/` | the learning tools (`harvest_metrics.py`, `score_task.py`, `heuristics_eval.py`, `classify_visibility.py`, `loop_autocommit.sh`, `loop_rollback.sh`, `loop_digest.py`, `loop_promote.py`, `lint_scales.py`, `lint_heuristics.py`, `themes_pending.py`) plus the carried set (`lint_registry.py`, `prose_grammar_gate.py`, `secret_pii_scrub_gate.py`, `git_safety_preflight.py`, `ssh_tunnel_keepalive.sh`, …) |
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

**`~/.claude/metrics/` is now a standalone nested git repo, and only
`audit/` is tracked in it.** The repo-audit scheduling layer's
`audit_store.ensure_store()` git-inits the metrics directory in place the
first time it runs and writes a scoped `.gitignore` — `/*`, then `!/audit/`,
then `/audit/logs/` back out. That scope is load-bearing: the shards,
checkpoints, and caches described below are siblings of `audit/`, and an
empty ignore file (what the first version wrote) would leave every one of
them untracked-but-not-ignored, one `git add -A` away from being committed
wholesale. `ensure_store()` rewrites the file whenever its content drifts, so
a store created by an older version is repaired on the next nightly run.
`audit_store.commit_paths()` is the only writer of that history — explicit
paths, never `git add -A`, never a push, and never fatal to its caller — and
`audit_run.sh` and `audit_digest.write_digest()` both call it immediately
after writing an artifact. That is what makes "a recoverable, versioned home"
a fact about the store rather than a claim about it.

`assert_no_remote()` is the
enforcement point — checked by asking `git remote` directly (failing CLOSED on
any non-zero exit, since an unverifiable answer is not evidence the invariant
holds) and by confirming no enclosing repository tracks the path without
gitignoring it — but it runs at two specific call sites, not on every access:
once per nightly dispatch, in `audit_dispatch.py` before `load_config()` reads
anything, and in `audit_store.py`'s own manual `check` action. Neither of the
other two audit tools re-verifies it: `audit_digest.py`'s reads
(`_iter_runs`, `write_digest`, `nudge`) and `audit_run.sh`'s run-log write
(`_write_run_log`) both trust the invariant the nightly dispatch already
checked, rather than confirming it again themselves. `~/.claude/metrics` is
the loop output root for every agent, not only the audit layer: the
`YYYY-MM.jsonl` shards described below and the audit layer's
`audit/{runs,findings,digests,quarantine,logs}` tree are siblings under the
same root. Only the audit tree is tracked, for the reason given above;
nothing about the shards' own format, writers, or "not publishable" contract
changes — see below.

| Field | Meaning |
|---|---|
| `kind` | `task` · `session` · `score` · `learn` · `compaction` |
| `task_id` | the join key: `agent-<id>` for a task, `session-<sid>` for a session |
| `resources_source` | how `resources_deployed` was attributed (see below) |

**Kinds.** A `task` record rolls up one subagent transcript; a `session`
record rolls up the main thread and carries `tasks_harvested`; a `compaction`
record is one line per PreCompact event; `score` and `learn` records (P3 / P6)
attach a subjective self-score and a heuristic action to an existing task.

A `score` record carries `{task_id, scales, note, resources_deployed, ts_end}`,
where `task_id` is `agent-<id>` for a subagent's own score or `session-<sid>`
for main-thread work — a bare session id is normalized to the `session-` prefix
before it joins, so it lands on the harvester's session rollup rather than
being orphaned — `scales` is the ordinal self-assessment map, `note` is a redacted
free-text remark, `resources_deployed` is copied from the joined `task` record
(or, for a `session-*` id with no task record, the joined `session` record), and
`ts_end` is the score's single timestamp.

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

Two boundary rules govern the backfill:

- It fires only when the session's `resources_deployed` is **non-empty**. A
  session that announced bare ("no registry match") or never announced at all
  backfills nothing — its subagents keep their empty lists.
- A subagent whose own announce was bare (`bare: true`, an empty list) **is**
  backfilled with the session list: bare says "nothing deployed by name," so
  the session-level attribution still applies. Because that attribution is
  coarse (session granularity, not task granularity), heuristics consumers may
  weight `resources_source: "task"` records above `"session-backfill"` records
  when computing per-resource statistics.

The backfill is idempotent across repeated SessionEnd events (resumed
sessions): the harvest cursor records which session resource list each agent
was backfilled with, and an unchanged session re-emits nothing.

**Not publishable — local-only by design, unchanged by the nested repo.**
Metrics records embed project slugs and git branch names that identify client
work, and `redact()` scrubs credentials only — not those identifiers. The
`metrics/` directory is untracked by every enclosing repo for exactly this
reason, and giving it its own local git history does not loosen that: the
nested repo carries no remote, so versioning run history in place creates no
new publication path, only a recoverable one. A metrics record MUST NOT be
copied into any tracked or publishable file without first passing the P5
visibility classifier (`classify_visibility.py`); default-deny routes anything
CLIENT or UNSURE back to local-only files.

---

## Autonomy mechanics

The loop does not just recommend changes — it commits them. This is the riskiest
part of the system, so the write path is a single, heavily gated tool and the
whole design is **default-deny**: when in doubt, a change lands in a local-only
file that has no remote and therefore cannot leak.

**Self-tuning is `HEURISTICS.md`-only.** The LEARN flow may adjust a rule's
declarative fields in `HEURISTICS.md` (threshold, window, THEN, confidence) or
retire a rule, but it never edits a tool or any `.py` file — every code change is
a human change, so the engine's behavior only ever moves under owner review.

**The one write path.** `payload/tools/loop_autocommit.sh` is the ONLY sanctioned
auto-write. It realpath-resolves each caller-supplied path and routes it to the
**framework** repo (`~/dev/claude-agent-loop`, published) or the **local** repo
(`~/.claude`, never published). A mixed set becomes two commits — framework
first, then local — each subject suffixed `[framework]` / `[local]`.

**Gate order** (all gates run BEFORE any commit lands, so an abort leaves both
repos exactly as they were):

0. **Gated lane** — REFUSED (exit 4), routed to a `registry/candidates/` stub,
   with no override flag. This covers both the INSTALLED artifacts (a `~/.claude`
   `settings*.json`, any `hooks/` path, a `CLAUDE.md` sentinel block) and the
   framework SOURCES that become them on install: any path under a `fragments/`
   directory (catching `settings.fragment.json` and `CLAUDE.starter.md`), any
   `settings*.json` basename anywhere, and any path under a `hooks/` directory
   regardless of extension (a `hooks/*.py` or an extensionless hook is refused
   too).
1. **`classify_visibility.py`** — every framework-bound path must classify
   GENERIC. A CLIENT marker (from `learning/CLIENT_MARKERS.txt`) or a structural
   risk signal (a `/Users/<name>` path, an email, a `user@host`, an IP) aborts
   (exit 3). A missing OR empty markers file fails CLOSED — every input becomes
   UNSURE. A framework path that cannot be text-scanned (a NUL-byte binary) is
   refused as well. Local-lane paths are exempt (local-only, no remote).
2. **`secret_pii_scrub_gate.py`** on the explicit paths — any finding aborts.
3. **`prose_grammar_gate.py`** on any `.md` paths — any finding aborts.
4. **`lint_registry.py`** (registry paths), **`lint_scales.py`** (`SCALES.md`),
   **`lint_heuristics.py`** (`HEURISTICS.md`, if the P6 tool is present).
5. **Message channel** — the commit subject and `-b` body are committed content
   too, so they are scanned, not trusted. For a framework commit the message
   must classify GENERIC and pass the scrub gate; for a local commit it is
   scrub-scanned (no remote to leak to, but a secret must not be logged). A
   CLIENT/UNSURE/finding aborts before anything lands. As a further belt, after
   `git add` and before the commit the staged index is scrub-scanned once more
   (a TOCTOU guard against a file mutated mid-flight).

On a gate abort, the affected index is reset (the working tree — the caller's
edit — is preserved), an `autocommit-blocked` NEW row is appended to
`LOOP_THEMES.md`, an OS notification fires, and the exit is non-zero. On success
the tool stages the explicit paths only (never `-A`) and commits them with a
pathspec (`--only`) so any pre-staged entry is left untouched, using a `loop:`
subject and a `Co-Authored-By: claude-agent-loop autonomy` trailer, and appends
one line to `learning/AUTO_COMMITS.log`. Each ledger line carries a trailing
GROUP id (the framework sha's first eight characters) that both halves of a
mixed commit share, so a two-lane pair can be rolled back as one unit. **It
never pushes.**

**Honest two-lane exit codes.** The framework and local commits are as atomic as
two separate repos allow. If the first (or only) lane's commit fails, nothing
lands and the exit is non-zero (5). If the framework lane committed but the
local lane then fails, the tool logs a `PARTIAL` line naming the orphaned
framework sha, fires a notification, prints a `loop_rollback.sh <sha>` hint, and
exits non-zero (6). The tool never reports success for a commit that did not
land.

**Rollback.** `payload/tools/loop_rollback.sh <sha>` (or `--last [N]`) reverts a
loop commit with `git revert --no-edit`, logging each revert. `--last [N]`
operates on N logical GROUPS, so a mixed two-lane pair (two ledger lines sharing
one group id) is undone together, newest group first. It REFUSES (exit 4) to
revert any commit whose subject lacks the `loop:` prefix — human commits are
never touched — and re-runs the registry/scales linters after a revert as a
guard (a lint failure is warned, never undoes the revert).

**Digest cadence.** `payload/tools/loop_digest.py` renders
`learning/digests/YYYY-MM-DD.md` from the auto-change ledger since the last
digest: auto-commits grouped by repo (with an unpushed count), blocked attempts,
theme transitions, and a current-month metrics summary. Its closing "Push now?"
section is the ONLY place publication is ever suggested, and even there it is a
manual command — the tool never runs it. The SessionStart hook injects a one-line
digest nudge (its second and last budgeted line) when 10 or more entries are
undigested, or when `.last-digest` is absent or older than seven days with at
least one undigested entry.

**Notifications.** `_notify` fires a macOS `osascript` notification on exactly
two events: a new resource auto-created, and a safety gate blocked a commit. It
is a no-op off macOS and never fails the commit path.

**Promote flow.** Learning files diverge from their repo seeds locally.
`payload/tools/loop_promote.py` is a read-only diff of `learning/{SCALES,
HEURISTICS}.md` against `payload/learning/*`; promoting a learned change back into
a published seed is a manual, owner-reviewed act — run `classify_visibility.py`
and the scrub gate over the hunks and generalize anything they flag before it
ships.

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
