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

**Autonomy note (until P5).** Promotions are **manual-approval candidates**, not
auto-created resources. This skill files a candidate stub and rewrites the theme
row's status; it never builds the resource itself. P5's autonomy tooling
(`loop_autocommit.sh`, the visibility classifier) will change how the commit
happens, but the owner-approval gate stays.

## The live file, not the seed

Read the **live** `~/.claude/learning/LOOP_THEMES.md`. The repo ships a
header-only seed; the rows accumulate locally and never leave the machine. A
theme row's `metrics-ref` may point at a metric shard because that file is
local-only state — but **anything you promote into a tracked resource must pass
the P5 visibility classifier first** (metric records carry project slugs and
branch names). Until P5, a promotion stops at a `candidates/` stub for the owner
to review; nothing client-tinged is copied into a publishable file.

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
     one patched (a recurring pain a skill/tool/guide would fix).
   - **DISMISS** — a one-off, noise, or a `wontfix`.
   - **LEAVE** — the signal is too thin to call. The rows stay `NEW` and wait
     for more evidence; do not force a decision.

5. **Act on the decision (until P5's autonomy tooling lands).**
   - **Promotion:** file a stub at
     `~/.claude/registry/candidates/YYYY-MM-DD-<slug>.md` using the candidate
     format (Status: candidate, a `## Evidence` section listing the cluster's
     rows and the metric records that back them). Then rewrite each row in the
     cluster from `| NEW |` to `| PROMOTED:<slug> |`, where `<slug>` matches the
     candidate filename. **Do not create the resource** — the candidate is the
     owner-approval gate.
   - **Dismissal:** rewrite each row's status to `| DISMISSED:<reason-slug> |`
     (a short kebab-case reason such as `one-off` or `wontfix`). Put the full
     rationale in the commit body, not the row.
   - **Leave:** change nothing.

6. **Rewrite in place; never delete.** Statuses are edited on the existing
   rows — rows are marked, never removed, so the history of what was seen and
   decided survives. Commit the `LOOP_THEMES.md` edit (plus any candidate stub)
   in the local `~/.claude` repo per the house three-section protocol
   ((1) Task & Change / (2) Tests or evidence / (3) Results). The metrics
   evidence you cite satisfies section (3) for this doc-only change.

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
