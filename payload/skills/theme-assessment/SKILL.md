---
name: theme-assessment
description: Work the loop-themes backlog — cluster the unprocessed NEW rows in LOOP_THEMES.md, pull the metric records they reference, and decide per cluster to promote, dismiss, or leave. Triggers - the SessionStart nudge line "Loop themes: N unprocessed — run Skill(theme-assessment)", "assess themes", 10 or more NEW rows pending, or run it any time by hand.
---

# Theme Assessment

`LOOP_THEMES.md` is the loop's cross-task memory: the LEARN step of the
`resource-loop` drops a `NEW` row whenever a task exposes a recurring pain or a
notable signal. Those rows are inert until someone reads them together. This
skill is that read: it turns a pile of `NEW` rows into decisions — a resource to
propose, a dead end to dismiss, or a signal too thin to call yet.

Run it when the SessionStart hook nudges you (`Loop themes: N unprocessed`), when
the count crosses 10, or any time you want to clear the backlog by hand.

**Autonomy (P5 and later).** A PROMOTE may now **auto-create** the resource: this
skill builds the new skill/agent/tool/guide and commits it through
`loop_autocommit.sh` (subject `loop: feat(<kind>): <slug> (theme promotion)`, a
three-section body that **summarizes** the evidence). The **gated lane** is the
sole exception — a promotion that would touch a `settings.json`, a hook script,
a `fragments/` source, or the `CLAUDE.md` sentinel block still stops at a
`candidates/` stub for the owner, because `loop_autocommit.sh` refuses those
paths by design. Everything the tool commits passes the visibility classifier,
the secret/PII scrub gate, and the grammar gate first, so nothing client-tinged
reaches a tracked file.

**Write the commit body as a GENERIC evidence summary — never paste raw
records.** The commit subject and `-b` body are now scanned exactly like the
files: for a framework commit `loop_autocommit.sh` runs the visibility
classifier and the scrub gate over the message and **blocks** it on any CLIENT,
UNSURE, or scrub finding. A body that pastes a raw metric slug, a git branch
name, a project path, or any client-tinged record will therefore abort the
commit. Summarize the evidence instead — "the same tunnel-drop signal recurred
in three sessions," not the verbatim shard rows — and keep counts and shapes,
not identifiers. The evidence still has to satisfy section (3) of the
three-section body; it just has to do so in generic terms.

## The live file, not the seed

Read the **live** `~/.claude/learning/LOOP_THEMES.md`. The repo ships a
header-only seed; the rows accumulate locally and never leave the machine. A
theme row's `metrics-ref` may point at a metric shard because that file is
local-only state — but **anything you promote into a tracked resource passes the
visibility classifier first** (metric records carry project slugs and branch
names). `loop_autocommit.sh` runs that classifier on every framework-bound path
and aborts on any CLIENT or UNSURE verdict, so nothing client-tinged is copied
into a publishable file.

## Procedure

1. **Read** the live `~/.claude/learning/LOOP_THEMES.md`. Work only the `NEW`
   rows; `PROMOTED:<slug>` and `DISMISSED:<reason>` rows are already settled.

2. **Cluster** the `NEW` rows by `theme-tag`. Group exact-tag matches first,
   then fold in semantic near-duplicates (`flaky-tunnel` and `tunnel-drops` are
   one theme). A cluster can be a single row.

3. **Pull the evidence.** Each row's `metrics-ref` is `<shard>#task_id=<id>`
   (for example `2026-07#task_id=agent-abc123`). For each row, read the shard at
   `~/.claude/metrics/<shard>.jsonl` (via Grep for the `task_id`, or Read for a
   small shard) and take the referenced records. **Last-record-per-`(task_id,
   kind)` wins** — the store is append-only, so a `task_id` may appear several
   times per `kind`; ignore every copy but the last. Weight a record whose
   `resources_source` is `"task"` above a `"session-backfill"` one — backfilled
   attribution is coarse (session granularity, not per task).

4. **Decide per cluster**, one of three:
   - **PROMOTE** — the evidence shows a resource should be created or an existing
     one patched (a recurring pain a skill/tool/guide would fix). Promote only
     when the cluster clears the **candidates evidence bar**: the same signal in
     **2 or more sessions**, or **3 or more times in one session**. A singleton
     cluster does not clear the bar — route it to LEAVE and let more evidence
     accumulate.
   - **DISMISS** — a one-off, noise, or a `wontfix`.
   - **LEAVE** — the signal is too thin to call. The rows stay `NEW` and wait
     for more evidence; do not force a decision.

5. **Act on the decision.**
   - **Promotion (standard lane):** build the resource, then commit it with
     `loop_autocommit.sh -m "loop: feat(<kind>): <slug> (theme promotion)"
     -b <bodyfile> <paths...>`, where `<kind>` is `skill`/`agent`/`tool`/`guide`
     and the body is the house three-section format whose (1)/(2)/(3) sections
     **summarize** the cluster's rows and the metric records that back them in
     generic terms (see the warning above — a body that pastes client-tinged
     records is blocked by the message-channel scan). Add the registry row and
     the guide in the same invocation so the linter's bijection holds. Then
     rewrite each cluster row from `| NEW |` to `| PROMOTED:<slug> |`.
     `loop_autocommit.sh` gates the whole commit (visibility classifier, scrub,
     grammar, linters) and routes framework-generic and local-client paths into
     separate commits automatically.
   - **Promotion (gated lane):** if the fix would touch a `settings*.json`, any
     `hooks/` path, a `fragments/` install source, or the `CLAUDE.md` sentinel
     block, do **not** auto-create it — `loop_autocommit.sh` refuses those
     paths. File a stub at
     `~/.claude/registry/candidates/YYYY-MM-DD-<slug>.md` (use
     `registry/guides/_TEMPLATE.md` for the structure — Status: candidate, plus a
     `## Evidence` section listing the cluster and its metric records) and set the
     rows to `| PROMOTED:<slug> |`. The owner builds it.
   - **Dismissal:** rewrite each row's status to `| DISMISSED:<reason-slug> |`
     (a short kebab-case reason such as `one-off` or `wontfix`). Put the full
     rationale in the commit body, not the row.
   - **Leave:** change nothing.

6. **Rewrite in place; never delete.** Statuses are edited on the existing
   rows — rows are marked, never removed, so the history of what was seen and
   decided survives. The `LOOP_THEMES.md` status rewrite is a local edit; it can
   ride in the same `loop_autocommit.sh` invocation as the resource (the tool
   splits the framework and local paths into two commits), and the metrics
   evidence you cite satisfies section (3) of the body for this doc-only part.

7. **Lint after any registry edit.** A promotion writes into
   `~/.claude/registry/`, so run `python3 ~/.claude/tools/lint_registry.py`
   afterward and confirm it is clean before you commit.

## Writing theme rows

This is the format WRITERS follow — chiefly the `resource-loop` LEARN step, which
appends one row when a task exposes a recurring signal. One theme per row:

```
| status | date | project | theme-tag | note | metrics-ref |
```

| Column | Value |
|---|---|
| `status` | `NEW` on write. Assessment rewrites it to `PROMOTED:<slug>` or `DISMISSED:<reason>`. |
| `date` | the task's date, `YYYY-MM-DD`. |
| `project` | the project slug the task ran in (for example `68_playground`). |
| `theme-tag` | kebab-case, one concept (`flaky-tunnel`, `slow-intake`, `route-cost-outlier`). Reuse an existing tag when the signal is the same — that is what makes clusters form. |
| `note` | one line, plain: what recurred and why it matters. |
| `metrics-ref` | `<shard>#task_id=<id>` — the metric shard month and the task's `task_id` (`2026-07#task_id=agent-abc123`), so the assessment can pull the evidence. |

Append rows; never rewrite an earlier one except to change its `status` during
assessment. Keep the note to a single line — the depth lives in the referenced
metric records, not in the row.
