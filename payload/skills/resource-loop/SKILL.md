---
name: resource-loop
description: Run at the start of EVERY session and before every new task — match the task against your resource registry, announce deployments, route subagents by model tier, execute, then score the result so the loop can learn. Triggers - any new user task, any subagent dispatch decision, any "should I build this inline" moment.
---

# Resource Loop

A closed loop: **MATCH → ANNOUNCE → ROUTE → EXECUTE → SCORE → LEARN.** The
registry index is injected at session start inside `<resource-loop>` tags. If it
is absent (hook failure, subagent context), read
`~/.claude/registry/REGISTRY.md` directly.

## The six steps

1. **MATCH** — semantically match the task against the index. Think in task
   shapes, not keywords: "make the chart pop" matches
   visual-hierarchy-layered-charts. Consult `~/.claude/registry/TRIGGERS.md` as a
   keyword and file-glob shortcut alongside the semantic match — it is an
   accelerator, not a replacement for reading the task. Read the full guide
   (`~/.claude/registry/guides/<name>.md`) for anything you will deploy.
2. **ANNOUNCE** — before work starts, output exactly one line:
   `Resource Loop — deploying: <name> (<category>) — <reason>[; …]`
   or, when nothing matches:
   `Resource Loop — no registry match; proceeding bare.`
   **This line is a schema contract, not just chatter.** The metrics harvester
   parses it for per-resource attribution, so each deployed `<name>` MUST be the
   exact registry id. When several resources each carry their own reason,
   SEMICOLON-separate the deployments
   (`a (skill) — reason-a; b (tool) — reason-b`): the harvester treats each
   `;` segment as one deployment and drops everything after its `— reason`. The
   COMMA form is reserved for a bare id list that shares one reason
   (`a, b, c — shared reason`). A paraphrased or misspelled name silently breaks
   the learning loop — the score you record later cannot be tied back to the
   resource.
3. **ROUTE** — when dispatching subagents:
   | Work type | Model |
   |---|---|
   | Planning, architecture, synthesis review | session model |
   | Creation-heavy (code, guides, skills, prose) | `model: opus` |
   | Mechanical (extraction, sweeps, lint fixes, probes) | `model: sonnet` (haiku for trivial probes) |
   Opus creators sub-delegate mechanical subtasks to Sonnet.
4. **EXECUTE** — do the work. Carry the whole loop into every subagent brief:
   paste the ANNOUNCE contract (exact registry ids, comma-separated), the
   relevant guide pointers, the ROUTE table, and the SCORE duty below. A
   subagent that does not announce and score is a task the loop cannot see.
5. **SCORE** — at task close, after the objective evidence is in, record a
   subjective self-score:
   ```
   python3 ~/.claude/tools/score_task.py --task-id <id> \
       --scale outcome=<level> [--scale ui=<level>] \
       [--scale rework=<level>] [--scale evidence=<level>] [--note "…"]
   ```
   Score the core scales that apply plus any applicable Extended scale. Pass
   `--task-id session-<session-id>` for main-thread work — the harvester keys
   the main session rollup `session-<sid>`, so a bare session id would orphan
   the score (score_task prefixes a bare id with `session-` for you and prints a
   note, but pass it explicitly). Pass `--task-id agent-<id>` for a subagent's
   own score; subagent task records are keyed `agent-<id>` and are backfilled
   automatically. When a niche quality dimension recurs and no scale fits, extend
   the registry rather than forcing a poor match:
   `score_task.py --new-scale <id> --levels "best>worst" --applies-to "…" --desc "…"`.
   Read `~/.claude/learning/SCALES.md` for the current scales.
6. **LEARN** — the loop's closing act. After SCORE, run the heuristics engine
   over the recorded metrics and act on what fired:
   ```
   python3 ~/.claude/tools/heuristics_eval.py --task-id <id>
   ```
   It reads the rulebook `~/.claude/learning/HEURISTICS.md` against the metrics
   store and prints every FIRING rule with its computed value, threshold, and
   evidence rows (each row tagged with its `resources_source`; a
   `session-backfill` row is flagged coarse). Act on the **highest-priority**
   firing rule. Priority is `improve-now` > `theme-note` > `no-action`, with ties
   broken by CONFIDENCE (`high` > `medium` > `low` > `seed`) then H-id order; the
   engine already sorts its output this way and labels the top one
   `<- recommended`. The three actions:

   - **improve-now** — create or patch the implicated resource, then commit it
     through `loop_autocommit.sh` (the ONLY sanctioned write path). Use the
     subject `loop: <type>(<scope>): <what> (H<id>)` and a three-section body
     that **summarizes the metric evidence in GENERIC terms** — never paste raw
     project slugs, branch names, or task ids. The commit message is scanned
     exactly like the files, so a client-tinged body is blocked before anything
     lands. Two cases file a `~/.claude/registry/candidates/` stub INSTEAD of
     auto-creating: rule **H4** (bare-match-streak — the owner creates the
     resource, never the loop), and any **gated-lane** target (a `settings*.json`,
     a `hooks/` path, a `fragments/` source, or the `CLAUDE.md` sentinel block),
     which `loop_autocommit.sh` refuses by design.
   - **theme-note** — append exactly ONE `| NEW | … |` row to
     `~/.claude/learning/LOOP_THEMES.md`, in the format the `theme-assessment`
     skill's "Writing theme rows" section defines (kebab-case `theme-tag`;
     `metrics-ref` is `<shard>#task_id=<id>`). Reuse an existing tag when the
     signal is the same, so clusters form.
   - **no-action** — the resource is healthy; change nothing, but still record
     the decision (next step) so a clean run is stored as positive signal.

   Whenever a rule fires and you act on it, **log the decision** so the loop can
   see its own moves:
   ```
   python3 ~/.claude/tools/heuristics_eval.py --emit-learn <action> \
       --rule H<id> --task-id <id>
   ```
   This appends a `kind:"learn"` record — even a `no-action` is stored. If
   `heuristics_eval.py` prints `no rules fired`, LEARN is a no-op for this task
   and there is nothing to log.

   **Tuning the rulebook.** When the evidence warrants, the loop MAY edit its own
   `HEURISTICS.md` — adjust a THRESHOLD, add a rule, or retire one to the
   `## Retired` section, bumping the rule's `LAST-REVIEWED` date. Each such edit
   is itself a `loop_autocommit.sh` commit whose body summarizes the metric
   evidence generically; the autocommit gate runs
   `python3 ~/.claude/tools/lint_heuristics.py` for you and blocks on a dirty
   rulebook. At 10 or more unprocessed `NEW` theme rows the SessionStart hook
   nudges you to run `Skill(theme-assessment)` to work the backlog.

## Gaps

If the task exposes a recurring need (seen in ≥ 2 sessions, or ≥ 3 times this
session) with no matching resource: write
`~/.claude/registry/candidates/YYYY-MM-DD-<slug>.md` and tell the user. NEVER
auto-create the resource — creation is gated on your approval.

## First run

Run `Skill(environment-bootstrap)` once to tailor this registry — and the
directives in `~/.claude/CLAUDE.md` — to your machine, stack, and databases.

## Maintenance

After ANY registry edit: `python3 ~/.claude/tools/lint_registry.py`. After ANY
scales edit: `python3 ~/.claude/tools/lint_scales.py`. After ANY heuristics edit:
`python3 ~/.claude/tools/lint_heuristics.py`. Registry drift checks are
manual (there is no scheduled ritual): re-run the lints after edits, and
`bash ~/.claude/tools/check_coverage.sh` when project wiring changes.
