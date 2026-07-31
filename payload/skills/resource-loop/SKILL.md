---
name: resource-loop
description: Run at the start of EVERY session and before every new task — match the task against your resource registry, announce deployments, route subagents by model tier, execute, then score the result so the loop can learn. Triggers - any new user task, any subagent dispatch decision, any "should I build this inline" moment.
---

# Resource Loop

A closed loop: **MATCH → ANNOUNCE → ROUTE → EXECUTE → SCORE → LEARN.** The
registry index is injected at session start inside `<resource-loop>` tags. If it
is absent (hook failure, subagent context), read
`~/.claude/registry/REGISTRY.md` directly.

## The work-order pipeline — use this for any task with parts

A task big enough to have parts runs on a **work order**: one JSON file at
`~/.claude/metrics/state/workorders/<plan-id>.json` that every stage reads and
writes. It exists because the ANNOUNCE line below is prose a harvester has to
scrape back out of a transcript, and measured over two months that scrape
succeeded on 21.7% of subagent tasks. A work order is written by a tool, so
attribution is precise by construction.

```
DECOMPOSE  plan_task.py --new "<task>"                     one part
           plan_task.py --from-plan <doc> --task "<task>"  one part per plan task
ASSIGN     plan_task.py --assign <plan-id>                 route_role per PART
BRIEF      make_brief.py <plan-id> <part-id>               the dispatch prompt
EXECUTE    dispatch; agent returns JSON, not prose
LOG        plan_task.py --log <plan-id> --part <id> --json <file>
ASSESS     assess_task.py <plan-id> [--repo .] [--propose-row]
LEARN      heuristics_eval.py, now reading objective evidence
```

**You do not have to remember this.** `workorder-gate.sh` runs on
`UserPromptSubmit` and scores every prompt. A conversational prompt or a slash
command passes in silence; a prompt at or above the creativity threshold injects
the decomposition directive before you answer, at most once per hour per session
so a long build is not nagged every turn. The gate is keyword arithmetic and can
misjudge — when it does, say so in one sentence and carry on. Kill switch:
`WORKORDER_GATE_DISABLE=1`.

**The superpowers gate.** `--new` REFUSES a creative task with exit 3. That is
deliberate: a task worth building is worth designing first. Run
`Skill(superpowers:brainstorming)` to settle the design, then
`Skill(superpowers:writing-plans)` to produce the breakdown, then feed that plan
document to `--from-plan`. `--force` overrides the refusal but records
`"forced": true` on the work order, so the shortcut shows up in the data.

**What ASSESS decides, and what it does not.** The verdict is `clean`, `dirty`,
or `unknown`, computed from tests, tool errors, commits, and reverts — never
from anyone's opinion of the work. A part with no objective signal assesses
`unknown`, never `clean`; silence is not success. `score_task.py` is retained
but demoted to a tiebreaker.

**Where an improvement lands.** A machine-global lesson patches the skill or
role doc through `loop_autocommit.sh`, exactly as before. A project-specific
lesson belongs in that project's `.claude/SUBAGENTS.md` instead —
`assess_task.py --propose-row` prints the row, and you ASK before writing it.
That path never writes inside a client project on its own.

Skip the work order for a trivial single-step task: measuring a one-line fix
costs more than the measurement is worth.

## The six steps

1. **MATCH** — semantically match the task against the index. Think in task
   shapes, not keywords: "make the chart pop" matches
   visual-hierarchy-layered-charts. Consult `~/.claude/registry/TRIGGERS.md` as a
   keyword and file-glob shortcut alongside the semantic match — it is an
   accelerator, not a replacement for reading the task. Read the full guide
   (`~/.claude/registry/guides/<name>.md`) for anything you will deploy.

   **Role hop (the deterministic HOOK → AGENT edge).** Before the semantic
   match, run the role router:
   ```
   python3 ~/.claude/tools/route_role.py "<the task text>"
   ```
   It scores the task against every role agent in `~/.claude/agents/roles/`
   (data-scientist, data-engineer, dba, cloud-architect, product-manager, …) by
   plain keyword arithmetic — the same task always routes the same way. On a
   confident match it prints a `Role — <role> (…) · skills: … · mcps: …` line:
   include that line with your ANNOUNCE, treat the role's declared skills as
   your MATCH shortlist (AGENT → SKILL), and prefer its declared MCPs where they
   are configured (connect nothing new — nudge `environment-bootstrap` for
   unconfigured ones). `Role — generalist` means no confident role: skip the
   hop and match normally. The role layer organizes; it never gates — any
   library skill remains directly invocable.
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
   python3 ~/.claude/tools/heuristics_eval.py --task-id <id> [--session-id <current>]
   ```
   Pass `--session-id <current>` when you know it — the bare-match-streak rule
   (H4) counts within the current session and otherwise falls back to recent
   project records. The engine reads the rulebook
   `~/.claude/learning/HEURISTICS.md` against the metrics store and prints every
   FIRING rule with its computed value, threshold, and evidence rows (each row
   tagged with its `resources_source`; a `session-backfill` row is flagged
   coarse). **Act on each firing's `effective_action`, never the raw THEN.** The
   engine downgrades a per-resource improve-now (H1, H7) to theme-note when its
   evidence is coarse-dominated or thin on precise (`resources_source: "task"`)
   rows — session-backfill does not establish the resource ran on those specific
   tasks — and shows the raw `action` plus a `downgrade_reason` alongside. This
   downgrade is engine-authoritative; do not second-guess it. Act on the
   **highest-priority** firing. Priority is `improve-now` > `theme-note` >
   `no-action` (on the effective action), with ties broken by CONFIDENCE
   (`high` > `medium` > `low` > `seed`) then H-id order; the engine already sorts
   its output this way and labels the top one `<- recommended`. The three actions:

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
     which `loop_autocommit.sh` refuses by design. **If the commit is BLOCKED**
     (`loop_autocommit.sh` exits 3/4/5/6 — a safety-gate abort, a gated-lane
     refusal, or a two-lane failure), the improve-now did not happen: record the
     ACTUAL outcome by logging `--emit-learn theme-note` (below) and file the
     theme row or candidate stub — never log `improve-now` for a commit that
     never landed.
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
   `HEURISTICS.md`, but ONLY within these bounds: adjust an EXISTING rule's
   THRESHOLD value, WINDOW size, THEN, or CONFIDENCE, or retire a rule to the
   `## Retired` section — always bumping its `LAST-REVIEWED` date. **Do NOT add a
   new rule id, and do NOT change which metric a rule watches.** The engine binds
   each metric to its rule by id in code, so a brand-new rule (or a rule pointed
   at a different metric) is inert until an owner writes its evaluator — and
   `lint_heuristics.py` now FAILS an active rule id that has no evaluator, so the
   autocommit gate refuses the commit. A genuinely new rule is an owner code
   change: file it as a candidate, not an autocommit. Each in-bounds edit is
   itself a `loop_autocommit.sh` commit whose body summarizes the metric evidence
   generically; the autocommit gate runs
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
