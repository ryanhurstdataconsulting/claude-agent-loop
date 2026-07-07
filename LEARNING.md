# LEARNING — the self-learning layer

This file explains how `claude-agent-loop` *learns*: how it measures every task,
accumulates signal across tasks, acts on that signal, and commits its own
improvements — all under a hard safety floor. Read `README.md` first for the
one-minute picture and `ARCHITECTURE.md` for the component map; this file is the
conceptual guide to the layer that makes the loop a *loop*.

---

## What "learning" means here

Be clear on this before anything else: **the learning in this framework is
heuristic scoring over recorded metrics plus human-curated themes. It is NOT
model training. No model weights are updated, no gradients are computed, and
there is no reinforcement-learning policy.** When the docs say the loop
"learns," they mean a small, auditable, file-based system:

- it **records** objective numbers about each task (tokens, tool errors, tests,
  duration) into plain JSONL;
- it **records** a short subjective self-score against a fixed set of ordinal
  scales;
- it runs a **rulebook** of transparent `if threshold crossed then act`
  heuristics over that recorded history;
- and it collects longer-lived patterns in a **theme log** that a human works
  through.

Everything is a text file you can open, diff, and revert. The "intelligence" is
the same Claude model reading its own metrics through an explicit rulebook — not
a trained artifact. This design is deliberate: it keeps the whole system legible
and keeps a human in the loop for every change that could matter.

---

## The closed loop

The `resource-loop` skill runs six steps for every task. The first four were the
original open loop; **SCORE** and **LEARN** close it.

1. **MATCH** — semantically match the task against the resource registry (task
   shapes, not keywords), consulting `TRIGGERS.md` as a shortcut.
2. **ANNOUNCE** — emit exactly one line naming the resources being deployed (or
   "proceeding bare"). This line is a *schema contract*: the metrics harvester
   parses it, so each name must be the exact registry id.
3. **ROUTE** — dispatch subagents at the right model tier (planning at the
   session model, creation-heavy work to Opus, mechanical work to Sonnet, and
   trivial probes to Haiku).
4. **EXECUTE** — do the work, carrying the ANNOUNCE contract, the ROUTE table,
   and the SCORE duty into every subagent brief.
5. **SCORE** — at task close, after the objective evidence is in, record a
   subjective self-score with `score_task.py`.
6. **LEARN** — run `heuristics_eval.py` over the recorded metrics and act on the
   highest-priority rule that fired: improve a resource now, drop a theme note,
   or take no action — and log the decision either way.

A **GAP** side behavior rides alongside MATCH and ANNOUNCE: when a recurring
need has no matching resource, the loop files a stub in `registry/candidates/`
for a human to approve. It never auto-creates a resource from a bare match.

A single task therefore flows: MATCH the registry → ANNOUNCE what it deploys →
ROUTE any subagents → EXECUTE and let the hooks harvest the objective metrics →
SCORE the outcome → LEARN by evaluating the rulebook and recording the decision.
Over many tasks, the metric history deepens, the heuristics gain evidence, and
the theme log fills — that accumulation is the learning.

---

## Objective metrics — what the hooks harvest

Three hooks harvest metrics with zero prompting from the model. They are
additive-only, always exit 0, and write one atomic line each, so a broken
harvest can never fail a session:

- **`SubagentStop`** → `harvest-metrics.sh` rolls up the finished subagent
  transcript into one `task` record.
- **`SessionEnd`** → `harvest-metrics.sh` writes a `session` rollup for the main
  thread and catches up any tasks it missed, tracked idempotently through a
  harvest cursor.
- **`PreCompact`** → `precompact-event.sh` writes one `compaction` event line.

`Stop` is deliberately unused — it is chatty and adds no signal the other three
do not already carry.

A `task` (or `session`) record captures, per task:

| Field | What it is |
|---|---|
| tokens by model | input/output tokens summed per `message.model` |
| `cache_efficiency` | share of prompt tokens served from cache |
| tool mix | which tools ran and how often |
| `tool_errors` / `error_rate` | tool failures, absolute and as a rate |
| `interrupted` | whether the user interrupted the task |
| `tests` | `{passed, failed}` parsed from test-runner output |
| `duration_s` | wall-clock seconds |
| `turns` | assistant turns |
| `resources_deployed` | the registry ids from the ANNOUNCE line — the join key |

**Where they land.** One JSON object per line in a monthly shard at
`~/.claude/metrics/YYYY-MM.jsonl` (`schema: 1`). This directory is **local-only
and untracked** — it is in no git repo. Metric records embed project slugs and
git branch names that identify real work, and the harvester's `redact()` scrubs
credentials, not those identifiers. Nothing from `metrics/` reaches a tracked
file without first passing the visibility classifier (see *Autonomy & safety*).

**The store contract, in one paragraph.** Records are keyed by `(task_id, kind)`
and are only ever appended — a record is never rewritten in place. When a
transcript grows, or when the `SessionEnd` backfill enriches a task, a fresh
replacement record is appended after the stale one, so **every consumer must
take the LAST record per `(task_id, kind)` and ignore earlier copies.** Each
record also states where its `resources_deployed` came from, in
`resources_source`: **`task`** means the ids were parsed from that task's own
ANNOUNCE line (*precise* — the resource provably ran on this task), while
**`session-backfill`** means they were copied from the session's ANNOUNCE onto a
subagent that never announced (*coarse* — session-level attribution, not
per-task). Backfill exists because **subagents rarely announce their own
resources, so session-backfill is the normal case, not the exception**: at
`SessionEnd`, once the session's resource list is known, the harvester re-emits a
replacement `task` record (last-wins) for every subagent whose own announce was
empty. Backfill fires only when the session actually deployed something by name;
a bare or silent session backfills nothing.

---

## Subjective scores

Objective metrics cannot tell you whether a chart was ugly or whether the user
had to redo the work. That is what the self-score captures. At task close the
loop runs `score_task.py`, which validates the given levels against `SCALES.md`
and appends a `score` record joined to the task by `task_id`.

`SCALES.md` is a linted, registry-style file (`lint_scales.py` checks its row
grammar) with a fixed core seed and an agent-extensible tail:

| Scale | Levels (best → worst) | Applies to |
|---|---|---|
| `outcome` | great > good > bad > horrible | any task |
| `ui` | pretty > ok > ugly | any UI / report / deliverable task |
| `rework` | none > minor > major | any task |
| `evidence` | proven > partial > asserted | any task |

These are **ordinal** scales — an ordered set of named levels, not numbers, so
"better" and "worse" are well defined without pretending the gaps are equal.
When a niche quality dimension recurs and none of the core scales fit, an agent
extends the registry rather than forcing a poor match, with
`score_task.py --new-scale <id> --levels "best>worst"`; the new row lands in the
`## Extended` section (a 40-row budget keeps the set curated).

---

## Themes — the cross-task backlog

A single task rarely proves anything. `LOOP_THEMES.md` is where a signal that
spans tasks accumulates until a human can judge it. Its rows are:

```
| status | date | project | theme-tag | note | metrics-ref |
```

The LEARN step appends a `| NEW | … |` row whenever a task exposes a recurring
pain or a notable pattern, reusing an existing kebab-case `theme-tag` when the
signal is the same so clusters form. Rows are **marked, never deleted** — the
history of what was seen and decided always survives.

The backlog gets worked in two ways. The `SessionStart` hook runs
`themes_pending.py`; when **10 or more `NEW` rows** are pending, it injects one
nudge line telling you to run the `theme-assessment` skill. That skill (also
runnable on demand) clusters the `NEW` rows by tag, pulls the metric records
each row references, and decides per cluster to **promote**, **dismiss**, or
**leave**:

- **Promote** only when the cluster clears the evidence bar — the same signal in
  **2 or more sessions, or 3 or more times in one session**. A promotion builds
  the resource and rewrites the rows to `PROMOTED:<slug>`.
- **Dismiss** a one-off or noise, rewriting to `DISMISSED:<reason>`.
- **Leave** a signal too thin to call; the rows stay `NEW` and wait for more
  evidence.

---

## Heuristics — the rulebook over metric history

`HEURISTICS.md` is the rulebook the loop evaluates every LEARN step. Each rule is
one block with a strict, linted grammar — an `H<id>` header plus **WHEN**,
**WINDOW**, **THRESHOLD**, **THEN**, **CONFIDENCE**, and **LAST-REVIEWED** — where
**THEN** is one of `improve-now`, `theme-note`, or `no-action`.
`lint_heuristics.py` enforces the grammar and refuses an active rule id that has
no evaluator in code.

The active seed rules, by name and intent:

| Rule | Intent | THEN |
|---|---|---|
| **H1** resource-error-spike | a resource's mean tool-error rate crosses a ceiling | improve-now |
| **H2** interrupt-pressure | the user interrupts an unusually large share of recent tasks | theme-note |
| **H3** test-fail-streak | consecutive tasks report a failing test | theme-note |
| **H4** bare-match-streak | the loop keeps proceeding bare on a similar task shape | improve-now* |
| **H6** cache-efficiency-floor | prompt-cache efficiency drops below a healthy floor | theme-note |
| **H7** rework-signal | the user self-scores `rework` as major repeatedly | improve-now |
| **H8** positive-streak | a resource sustains a long clean run | no-action |

\* H4 files a `registry/candidates/` stub for a human — the loop never
auto-creates a resource from a bare-match streak.

The file also has a **`## Planned`** lane for rules that are fully specified but
whose metric is not in the store yet, so the engine parses them as PLANNED and
never evaluates them, and their ids stay reserved. The seed there is **H5
route-cost-outlier** (mechanical work routed to the Opus tier), which needs a
task-shape/route-tier field at ANNOUNCE time that the schema does not carry yet.

`heuristics_eval.py --task-id <id>` computes each rule's window over the metric
history and prints every rule that fired with its computed value, threshold, and
evidence rows. The loop acts on the **highest-priority** firing —
`improve-now` > `theme-note` > `no-action`, ties broken by confidence then H-id —
and takes one of three actions:

- **improve-now** — create or patch the implicated resource and commit it through
  the sole auto-write path (below).
- **theme-note** — append one `NEW` row to `LOOP_THEMES.md`.
- **no-action** — the resource is healthy; change nothing, but still record the
  decision.

Every decision is logged as a `learn` record — **`no-action` is stored as
positive signal too**, so a clean run is evidence, not silence. The loop may also
*tune* the rulebook within tight bounds (adjust an existing rule's threshold,
window, THEN, or confidence, or retire a rule), but it may **never** add a new
rule id or repoint a rule at a different metric — those are owner code changes,
filed as candidates.

---

## The coarse-evidence guard

This is the honesty at the center of the design, so it gets its own section.

Because session-backfill attribution is the *normal* case (subagents seldom
announce), most of a resource's evidence rows are **coarse** — they say the
resource was deployed somewhere in the session, not that it ran on that specific
task. Acting aggressively on coarse evidence would let the loop "improve" a
resource that may not even have been responsible for the metric it is reacting
to.

So the engine applies a guard: **a per-resource `improve-now` rule (H1, H7)
DOWNGRADES to `theme-note` unless it has at least 3 precise evidence rows —
`resources_source: "task"`, from a self-announced task — and is not
coarse-dominated.** When it downgrades, the engine reports the raw `action`, the
`effective_action`, and a `downgrade_reason` together, and the loop acts on the
**effective** action. This downgrade is engine-authoritative — the loop does not
second-guess it.

The effect is conservative by construction: until precise attribution
accumulates, the loop surfaces most learning to a human as a theme note rather
than committing an automated fix. The system earns the right to act on its own
only when the evidence is genuinely precise.

---

## Autonomy & safety

The loop does not only recommend changes — it commits them. Because that is the
riskiest thing it does, every automated write goes through one heavily gated
tool, and the whole design is **default-deny**: when in doubt, a change lands in
a local-only file that has no remote and therefore cannot leak.

**The sole write path** is `loop_autocommit.sh`. It realpath-resolves each path
and routes it to the **framework** repo (published) or the **local** `~/.claude`
repo (never published); a mixed set becomes two commits. Before anything lands it
runs an ordered, non-bypassable **safety floor**:

1. **Gated-lane refusal** — a `settings*.json`, any `hooks/` path, a `fragments/`
   install source, or a `CLAUDE.md` sentinel block is refused outright and routed
   to a `candidates/` stub. There is no override flag.
2. **Visibility classify** — every framework-bound path must classify GENERIC
   against `CLIENT_MARKERS.txt`; a client marker or a structural signal (a
   `/Users/<name>` path, an email, a `user@host`, an IP) aborts. A missing or
   empty markers file fails **closed**.
3. **Secret/PII scrub** — the scrub gate runs on the explicit paths; any finding
   aborts.
4. **Grammar** — the grammar gate runs on any `.md` path; any finding aborts.
5. **Lints** — `lint_registry.py`, `lint_scales.py`, and `lint_heuristics.py`
   run as their targets are touched.

The commit *message* is scanned too, not trusted — a client-tinged commit body is
blocked exactly like a file — and the staged index is re-scanned once more right
before the commit as a guard against a file mutated mid-flight. On any abort the
index is reset (the caller's edit is preserved), an `autocommit-blocked` row is
appended to `LOOP_THEMES.md`, an OS notification fires, and the exit is non-zero.

Three further guarantees:

- **The gated lane is never auto-committed.** Settings, hook scripts, the
  `CLAUDE.md` sentinel, and `fragments/` sources always stop at a `candidates/`
  stub for the owner.
- **Atomic commits with rollback.** Writes are explicit-staged (never `git add
  -A`), each commit carries a `loop:` subject, and `loop_rollback.sh <sha>` (or
  `--last [N]`) reverts a loop commit — refusing any commit whose subject lacks
  the `loop:` prefix, so human commits are never touched. A mixed two-lane pair
  shares a group id and is rolled back as one unit.
- **Digest at review, manual push.** `loop_digest.py` renders a dated digest of
  every auto-change since the last review; its closing "Push now?" section is the
  **only** place publication is suggested, and even there it is a manual command —
  the tool never pushes. Exactly **two** events raise an OS notification: a new
  resource auto-created, and a safety gate blocking a commit.

For the residual risks that remain by design — exact-substring marker matching,
and best-effort macOS-only notifications — see `SECURITY.md` ("Autonomy residual
risks").

---

## Distribution

The framework is **repo-first**. `install.sh` symlinks every framework file named
in `payload/MANIFEST` out of the repo working tree into `~/.claude/`, so the repo
is the single source of truth and updating is just:

```bash
git -C <this-repo> pull && bash install.sh
```

The symlinked content is live the instant the pull lands — no copy step, no
drift.

The load-bearing split keeps client work structurally unable to leak:

- **Framework** (skills, tools, hooks, guide seeds, and the `SCALES.md` /
  `HEURISTICS.md` *seeds*) lives in git and is published.
- **Learned state** — the live `SCALES.md`, `HEURISTICS.md`, `LOOP_THEMES.md`,
  `CLIENT_MARKERS.txt`, and the auto-change ledger — is **copied once** from the
  seeds at install and then diverges locally; it is never published.
- **Metric data** in `~/.claude/metrics/` is untracked and in no git repo.

Because the learning files diverge from their seeds, `loop_promote.py` gives the
owner a read-only diff of the local `SCALES.md` / `HEURISTICS.md` against the
shipped seeds. Promoting a learned change back into a published seed is a manual,
owner-reviewed act: run the visibility classifier and the scrub gate over the
hunks and generalize anything they flag before it ships.

---

## See also

- **`README.md`** — what the framework is and how to start.
- **`INSTALL.md`** — the install steps, the symlink model, and how to undo.
- **`ARCHITECTURE.md`** — the component flow, the three layers, the metrics store
  contract, and the autonomy mechanics in full.
- **`SECURITY.md`** — the scrub posture and the autonomy residual risks.
