# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
