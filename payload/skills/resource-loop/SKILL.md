---
name: resource-loop
description: Run at the start of EVERY session and before every new task — match the task against your resource registry, announce deployments, route subagents by model tier, execute, then score the result so the loop can learn. Triggers - any new user task, any subagent dispatch decision, any "should I build this inline" moment.
---

# Resource Loop

A closed loop: **MATCH+ROUTE → ANNOUNCE → EXECUTE → SCORE → LEARN.** The
registry index is injected at session start inside `<resource-loop>` tags. If it
is absent (hook failure, subagent context), read
`~/.claude/registry/REGISTRY.md` directly.

## The plan pipeline — use this for any task with parts

A task big enough to have parts runs on a **plan**: one JSON file at
`~/.claude/plans/<YYYY-MM-DD>/<task_id>.json` that every stage reads and
writes. It exists because the ANNOUNCE line below is prose a harvester has to
scrape back out of a transcript, and measured over two months that scrape
succeeded on 21.7% of subagent tasks. A plan is written by a tool, so
attribution is precise by construction.

```
DECOMPOSE  plan_task.py --new "<task>"                     one step, assigned + briefed
+ASSIGN    plan_task.py --from-plan <doc> --task "<task>"  one step per plan task,
+BRIEF                                                       assigned + briefed
EXECUTE    dispatch the step's brief; agent returns JSON, not prose
RECORD     plan_task.py --record <task_id> --step <id> --json <file-or-json>
                                            (a file path is safer than inline
                                             JSON — return prose has quotes)
SCORE      score_task.py --auto <task_id>   (objective verdict, folds in what
                                              assess_task.py used to do)
LEARN      heuristics_eval.py, reading that objective evidence
```

**PLAN is judgment, not a gate.** Decide for yourself whether a task is big
enough for a plan artifact — multi-step, multi-agent, or ambiguous work is; a
one-line fix or a question is not. There is no keyword-scored backstop forcing
this anymore. `pipeline-relay.sh` still nudges the next link once you've
launched `superpowers:brainstorming` or `superpowers:writing-plans`, so a
session that settles a design doesn't stop at the spec. Creative work is still
worth designing before it's decomposed — that used to be a hard refusal
`plan_task.py --new` enforced with exit 3; now it is guidance, not a rule any
tool checks, so make the call yourself and run brainstorming/writing-plans
first when the task warrants it.

`pipeline-relay.sh` then keeps the chain moving: launching
`superpowers:brainstorming` or `superpowers:writing-plans` injects the next
link. It exists because a spec is where the chain kept dying — a session would
settle the design, write a spec, and start implementing from it. **A spec is a
design, not a decomposition.** Kill switch: `PIPELINE_RELAY_DISABLE=1`.

**What SCORE's `--auto` mode decides, and what it does not.** Internally it
still computes a `clean`, `dirty`, or `unknown` verdict per step, from tests,
tool errors, commits, and reverts — never from anyone's opinion of the work. A
step with no objective signal assesses `unknown`, never `clean`; silence is not
success. There is no separate bespoke verdict field anymore: that internal
verdict maps onto the SCALES.md evidence scale (`clean` → `proven`,
`dirty`/`unknown` → `asserted`), and `--auto` appends one `scales.evidence`
record **per step**, plus `scales.rework` on any step that needed a revert or
a follow-up fix. Each record is keyed exactly like that step's own
`kind:"task"` record, which is the only way LEARN can ever reach it; the worst
verdict across the plan is printed for you, not stored.

**Where an improvement lands.** A machine-global lesson patches the skill or
role doc through `loop_autocommit.sh`, exactly as before. A project-specific
lesson belongs in that project's `.claude/SUBAGENTS.md` instead — propose the
row yourself and ASK before writing it; no tool auto-drafts it. That path
never writes inside a client project on its own.

Skip the plan for a trivial single-step task: measuring a one-line fix costs
more than the measurement is worth.

## The five steps

1. **MATCH+ROUTE** — dispatch the `resource-router` agent (not a hand-read of
   the registry) for every non-trivial task, before deploying anything else.
   Give it the task text and, if you know it, the project's absolute path so
   it can check for a `.claude/SUBAGENTS.md` override. It reads the live
   registry, the skill catalog, and the agent roster itself — you do not need
   to paste any of that into its prompt. It returns a structured loadout:
   the exact ANNOUNCE line(s), ordered lead skills, agents to dispatch (each
   with model/effort and a brief outline), MCPs, tools, any ephemeral
   task-scoped resource it composed on the spot, and any durable gaps.

   Relay its ANNOUNCE block verbatim as your own ANNOUNCE (step 2, below) —
   do not re-derive it. Dispatch the agents/MCPs/tools it returned at the
   model/effort it specified. If it returned GAPS, file the candidate stub
   yourself exactly as the "Gaps" section below describes — the router only
   recommends the stub, it never writes one.

   **Skip this step only for genuinely trivial or conversational turns** —
   answering a quick question, a one-line fix, or continuing an
   already-routed task from earlier in the same session. Anything with
   independent parts, an unfamiliar domain, or a task-shape you haven't
   already routed this session goes through the router.

   **Deterministic fallback.** `route_role.py`'s keyword-phrase scoring and
   `TRIGGERS.md`'s keyword rows still exist and still work — they are what
   `plan_task.py --new`/`--assign` calls directly (a CLI tool has no Agent
   tool to dispatch a router with), and what a subagent context falls back to
   if it has no Agent tool of its own:
   ```
   python3 ~/.claude/tools/route_role.py "<the task text>"
   ```
   It scores the task against every role agent in `~/.claude/agents/roles/`
   by plain keyword arithmetic — the same task always routes the same way.
   On a confident match it prints a `Role — <role> (…) · skills: … · mcps: …`
   line; `Role — generalist` means no confident match. Read
   `~/.claude/registry/guides/resource-router.md` for the composition
   contract between the two: a supervisor session that already has a router
   loadout for a given ask may override a plan step's deterministic
   assignment with it before dispatch; nothing else changes about how
   `plan_task.py` runs.

   *(Model-tier reference the router applies: planning/architecture/synthesis
   → session model; creation-heavy code/guides/skills/prose → `model: opus`;
   mechanical extraction/sweeps/lint-fixes/probes → `model: sonnet` (`haiku`
   for trivial probes). Opus creators sub-delegate mechanical subtasks to
   Sonnet.)*
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
3. **EXECUTE** — do the work. Carry the whole loop into every subagent brief:
   paste the ANNOUNCE contract (exact registry ids, comma-separated), the
   relevant guide pointers, the ROUTE table, and the SCORE duty below. A
   subagent that does not announce and score is a task the loop cannot see.
4. **SCORE** — at task close, first fill in the objective half, then the
   subjective one. For a task run through `plan_task.py` (a plan with steps),
   assess it objectively before self-scoring:
   ```
   python3 ~/.claude/tools/score_task.py --auto <task_id>
   ```
   This loads the plan, fills every step's verdict from tests, tool errors,
   commits, and reverts — never from anyone's opinion of the work — and
   appends one `scales.evidence` (`proven`/`asserted`) record per step, plus
   `scales.rework` on any step that needed a revert or a follow-up fix. Then
   record a subjective self-score:
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
5. **LEARN** — the loop's closing act. After SCORE, run the heuristics engine
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
