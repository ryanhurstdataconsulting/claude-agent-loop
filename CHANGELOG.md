# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Work-order pipeline** (`payload/tools/plan_task.py`,
  `payload/tools/make_brief.py`, `payload/tools/assess_task.py`) — replaces
  prose-scraped attribution with one JSON artifact per task at
  `~/.claude/metrics/state/workorders/<plan-id>.json` that every loop stage
  reads and writes. Adds the DECOMPOSE stage the loop never had: `route_role`
  now runs per PART rather than once per whole task. `plan_task.py --new`
  refuses a task scoring creative (exit 3) until `superpowers:brainstorming`
  and `superpowers:writing-plans` have run, whose plan document feeds
  `--from-plan`; `--force` overrides but records `"forced": true`.
  `make_brief.py` renders a dispatch prompt carrying the part's ids, skill
  shortlist, and a required JSON return schema, so an agent cannot return a
  valid result without producing its own attribution. `assess_task.py` derives
  a `clean`/`dirty`/`unknown` verdict from tests, tool errors, commits, and
  reverts with no model involvement — a part with no objective signal assesses
  `unknown`, never `clean` — and `--propose-row` prints a project
  `SUBAGENTS.md` row without writing inside a client project. Motivated by two
  months of `~/.claude/metrics/`: the ANNOUNCE line parsed on 21.7% of subagent
  tasks and subjective scores existed on 4.6%, while a git branch was recorded
  on 100% and test results on 64% and neither was read. Covered by 84 cases
  across `test_plan_task.py`, `test_make_brief.py`, and `test_assess_task.py`.
- **Usage-budget hook** (`payload/hooks/usage-budget.sh`, PostToolUse) —
  reads the cached account-usage status that the out-of-band `usage_poll.py`
  launchd poller writes to `~/.claude/metrics/state/usage/status.json`, and
  steers the agent to a durable pause point before a Claude session or weekly
  subscription limit is exhausted: a single warning at 70% of
  `max(session_pct, weekly_pct)`, then a checkpoint directive from 85% that
  repeats on every tool call until a checkpoint file exists at
  `~/.claude/metrics/state/usage/checkpoints/<session>.md`. Reads only the
  local cache (no network in the hot path) and stays silent when the cache is
  missing or older than 30 minutes. Fail-open, always exits 0; kill switch
  `USAGE_BUDGET_DISABLE=1`. Covered by the 17-case
  `payload/tools/tests/test_usage_budget.sh`, including a fixed-string grammar
  regression on the emitted directive prose.
- **`grill-me` skill** — an adversarial plan-stress-testing interview (one
  tough question at a time, each with a recommended answer, no action until
  shared understanding). Vendored from Matt Pocock's `mattpocock/skills`
  (MIT), with the upstream stub/companion pair merged into a single
  `payload/skills/grill-me/SKILL.md`.
- **`react-best-practices` skill** — Vercel Engineering's 70-rule React and
  Next.js performance catalog (`vercel-labs/agent-skills`, MIT): `SKILL.md`
  index plus 72 per-rule files under `rules/` with before/after examples; the
  compiled `AGENTS.md` duplicate was dropped. The skill library grows to 172
  skills; both new skills are MANIFEST-linked and cataloged.
- **Read-guard hook** (`payload/hooks/read-guard.sh`, PreToolUse on Read) —
  hard-blocks (permission deny) reads of file classes that should never enter
  context (lockfiles, minified or bundled assets, source maps, JSONL session
  transcripts, log files, CSV/Parquet data files, and anything under
  `node_modules/`, `dist/`, `build/`, `.vite/`, or `coverage/`), and
  soft-nudges (allow + `additionalContext`) any read of a file over 1,000
  lines or 100 KB made without `offset`/`limit`, prompting a narrow re-read.
  Fail-open, never exits 2. Covered by the 16-case
  `payload/tools/tests/test_read_guard.sh`. (Merged alongside 2.1.0 without a
  changelog entry; recorded here.)
- `score_task.py --task-shape {planning,creation,mechanical}` — an optional
  scoring-time label; when omitted, the score record carries no `task_shape`
  key at all.
- The H5 (route-cost-outlier) evaluator in `heuristics_eval.py`: the route
  tier is derived from each task record's `models` field (dominant model by
  `out` tokens; only Opus is a hit, and the session tier never is), joined to
  the score's `task_shape`. H5 is now the eighth evaluable rule, which also
  makes rulebooks with an ACTIVE H5 lint-clean.
- **Usage-budget poller** (`payload/tools/usage_poll.py`, launchd job
  `com.hdc.claude-agent-loop.usage-poll`) — an out-of-band poller that reads the
  account's session- and weekly-limit percentages from claude.ai's usage page
  through a persisted Playwright session and atomically writes
  `~/.claude/metrics/state/usage/status.json` every 10 minutes, so the
  usage-budget hook can warn before a subscription limit is exhausted. Fail-open:
  any poll failure is logged to `usage_poll.log` and leaves the existing cache
  untouched, and the process always exits 0. Auth is a one-time
  `usage_poll.py --login`; loading the launchd job is a manual `launchctl
  bootstrap` step (see INSTALL.md). Covered by the 28-case
  `payload/tools/tests/test_usage_poll.py`.

### Changed
- Seed `learning/HEURISTICS.md`: H5 moved from the "Planned (not yet
  computable)" lane into the active body; the emptied Planned section was
  removed.

## [2.1.0] - 2026-07-15

### Added

- **Context-budget hook** (`payload/hooks/context-budget.sh`, PostToolUse) —
  watches the session's context-window occupancy from the transcript tail and
  steers the agent to a durable pause point before auto-compaction can destroy
  working state: a single warning at 70% of the 150k-token budget, then a
  checkpoint directive from 85% that repeats on every tool call until a resume
  brief exists at `~/.claude/metrics/state/budget/checkpoints/<session>.md`. Fail-open,
  always exits 0; kill switch `CONTEXT_BUDGET_DISABLE=1`. Covered by the
  13-case `payload/tools/tests/test_context_budget.sh`, including a
  fixed-string grammar regression on the emitted directive prose.

## [2.0.0] - 2026-07-07

Version 2 turns the Resource Loop from an open dispatch loop into a closed,
self-learning one: it measures every task, scores the outcome, accumulates
cross-task signal, and acts on a heuristic rulebook — committing its own
improvements under a hard safety floor. "Learning" here means heuristic scoring
over recorded metrics plus human-curated themes; it is not model training. See
`LEARNING.md` for the full picture.

### Added
- **Objective metrics (passive).** New hooks harvest one record per task and per
  session with no prompting: `SubagentStop` and `SessionEnd` run
  `harvest-metrics.sh`, and `PreCompact` runs `precompact-event.sh`. Records land
  in `~/.claude/metrics/YYYY-MM.jsonl` (`schema: 1`, local-only, untracked) and
  capture tokens by model, cache efficiency, tool mix, error rate, interrupts,
  tests passed/failed, duration, turns, and the deployed resources.
  `harvest_metrics.py` performs the roll-up; the store is append-only with a
  last-record-per-`(task_id, kind)` read rule and a `resources_source` field that
  distinguishes precise (`task`) from coarse (`session-backfill`) attribution.
- **Subjective scoring.** `score_task.py` records an ordinal self-score at task
  close against `SCALES.md` (core scales: outcome, ui, rework, evidence;
  agent-extensible), validated by `lint_scales.py`.
- **Themes.** `LOOP_THEMES.md` is the cross-task backlog; `themes_pending.py`
  nudges at SessionStart once 10 or more `NEW` rows are pending, and the new
  `theme-assessment` skill clusters the rows and promotes, dismisses, or leaves
  each one.
- **Heuristics.** `HEURISTICS.md` holds a linted rulebook (8 seed rules, H1–H8,
  with H5 in a not-yet-computable `Planned` lane); `heuristics_eval.py` evaluates
  it over the metric history and emits a `learn` record for every decision,
  `no-action` included. A coarse-evidence guard downgrades a per-resource
  `improve-now` to `theme-note` until enough precise attribution accumulates.
  `lint_heuristics.py` enforces the rule grammar.
- **Gated autonomy.** `loop_autocommit.sh` is the sole auto-write path, behind an
  ordered safety floor (gated-lane refusal → visibility classify → secret/PII
  scrub → grammar → linters → message-channel scan). `classify_visibility.py` is
  default-deny — CLIENT and UNSURE both route to local-only files.
  `loop_rollback.sh` reverts loop commits, `loop_digest.py` renders the review
  digest and is the only place a push is ever suggested, and `loop_promote.py`
  diffs learned state against the shipped seeds for owner-reviewed promotion.
- **`LEARNING.md`** — a conceptual guide to the whole self-learning layer.
- **Learning seeds** under `payload/learning/`: `SCALES.md`, `HEURISTICS.md`,
  `LOOP_THEMES.md`, and `CLIENT_MARKERS.template.txt`.
- **Repo scaffold:** `payload/MANIFEST` (the explicit
  link-dir/link-file/copy-if-absent install list), the carried test suite under
  `payload/tools/tests/` with a `run_all.sh` runner, and the repo meta `VERSION`,
  `LICENSE` (MIT), and this `CHANGELOG.md`.

### Changed
- **The loop is now a closed six-step cycle** — MATCH → ANNOUNCE → ROUTE →
  EXECUTE → SCORE → LEARN (GAP remains a side behavior), up from the original
  four-step MATCH → ANNOUNCE → GAP → ROUTE. The ANNOUNCE line is now a schema
  contract the metrics harvester parses for per-resource attribution.
- **Distribution is repo-first.** `install.sh` v2 symlinks the framework files
  named in `payload/MANIFEST` into `~/.claude/`; the registry index and the
  `learning/` seeds are copied once and then diverge locally. Updating is
  `git pull && bash install.sh`, live the instant the pull lands.
- **The `settings.json` merge now installs four hook groups** (SessionStart,
  SubagentStop, SessionEnd, PreCompact), deduped by command.
- The framework/local split is enforced structurally: the published framework
  lives in git, while learned state and metrics stay local-only and never enter a
  published repo.

### Security
- Every automated commit passes the visibility classifier, the secret/PII scrub
  gate, and (for prose) the grammar gate before it lands; the commit message is
  scanned like a file, and the staged index is re-scanned as a guard against a
  file mutated mid-flight.
- The gated lane — settings, hook scripts, `fragments/` sources, and the
  `CLAUDE.md` sentinel block — is never auto-committed; it always routes to a
  `candidates/` stub for the owner.
- The loop never pushes; publication is a manual command surfaced only at the
  digest. The residual autonomy risks are documented in `SECURITY.md`.
