---
name: idempotent-backfill-authoring
description: Use when backfilling historical data, re-running a pipeline over a date range, reprocessing a large table, or fixing data corrupted by a prior bad run — any task shaped like "backfill the last N months," "recompute this column for all rows," or "rerun the pipeline for this date range." Triggers on requests to bulk-update or bulk-recompute production data, duplicate-row incidents from a rerun, and partial-failure recovery for a long-running batch job.
---

# idempotent-backfill-authoring

## Overview
Designs and executes large-scale historical reprocessing — backfills,
recomputes, bulk corrections — so that a rerun (partial or full) produces
the same end state every time, without locking up the source table or
losing progress on failure. Owns the "safely rewrite a lot of history"
job; distinct from a routine incremental pipeline run.

## When to use
- A task asks to backfill historical data over a date range.
- A task asks to recompute a derived column, metric, or aggregate for
  existing rows.
- A prior pipeline run produced wrong or missing data and needs correction
  across many rows.
- A batch job needs to process a table too large for a single transaction.
- A previous backfill attempt failed partway through and needs a safe
  resume, not a full restart.

## Workflow

1. **Choose the recompute strategy before writing any code:**
   - **Deterministic full recompute** (preferred when feasible) — the
     output for a given key/date is a pure function of stable inputs.
     Recomputing and overwriting is always safe to rerun; no branching
     logic needed.
   - **UPSERT / merge** — when only a subset of rows changed and a full
     recompute is too expensive. Use `INSERT ... ON CONFLICT DO UPDATE`
     (Postgres) or `MERGE` (warehouses that support it) keyed on a stable
     natural or surrogate key — never a plain `INSERT`, which duplicates
     rows on rerun.
   - **Partition overwrite** — for partitioned tables (date-partitioned
     fact tables, Iceberg/Parquet partitions), overwrite the whole
     partition rather than delete-then-insert individual rows; this is
     both faster and immune to partial-delete failures leaving a
     half-written partition.

2. **Never touch millions of rows in one transaction.** Batch the work:
   - Chunk by key range or date range (e.g., one transaction per day, or
     per 10k-row key block).
   - Keep each transaction short enough that it does not hold locks or
     bloat the transaction log for an extended period — this matters most
     on a live table other processes are reading from concurrently.
   - Between batches, check for lock contention or replication lag and
     back off if the batch is visibly affecting production traffic.

3. **Make the operation resumable, not all-or-nothing.** Persist progress
   outside the transaction that's doing the work:
   ```sql
   -- checkpoint table, updated after each successful batch
   CREATE TABLE backfill_progress (
     job_name text PRIMARY KEY,
     last_completed_key text,
     last_completed_at timestamptz
   );
   ```
   On restart, read the checkpoint and resume from the next unprocessed
   batch instead of reprocessing from the beginning. This is what turns a
   crashed 6-hour job into a 20-minute fix instead of a full redo.

4. **Always build and exercise a dry-run mode first.** The dry-run should
   execute the full read/compute path and report exactly what would
   change (row counts, a sample diff, aggregate before/after) without
   writing anything. Run it against production data before the real run —
   this is the single highest-leverage safety step and the most commonly
   skipped one.

5. **Verify idempotency by actually rerunning a batch twice** in a
   non-production environment (or against a narrow, low-risk key range in
   production) and confirming the second run changes nothing. If it does,
   the operation is not actually idempotent yet — fix it before scaling
   up.

6. **Write the rollback plan before running, not after something breaks.**
   Options, cheapest first:
   - Recompute-based: rerun the deterministic recompute with the prior
     inputs (only works if inputs are still available/versioned).
   - Snapshot-based: `CREATE TABLE ... AS SELECT * FROM target` (or a
     warehouse time-travel / point-in-time restore feature) taken
     immediately before the run.
   - Log-based: capture a before-value for every row touched, keyed by the
     same batch/checkpoint scheme, so a targeted rollback is possible
     without a full table restore.

7. **Respect the read-only/no-DDL boundary if one applies to the
   environment.** If the calling project restricts write or DDL access
   against a given database, this skill's output is a reviewed runbook and
   dry-run report for someone with write access to execute — not a script
   this agent runs itself. Check the project's own data-access rules
   before assuming execution is in scope.

## Checklist / quality gate
- [ ] The recompute strategy (full recompute / UPSERT / partition
      overwrite) is chosen deliberately and matches the data's actual
      determinism.
- [ ] Writes are batched — no single transaction touches an unbounded
      number of rows.
- [ ] Progress is checkpointed outside the write transaction, and a
      restart resumes rather than reprocesses from scratch.
- [ ] A dry-run mode exists, was run against real data, and its output was
      reviewed before the real run.
- [ ] Idempotency was verified by actually rerunning a batch twice with no
      resulting change.
- [ ] A rollback plan is written down and, where feasible, tested before
      the real run — not improvised after a failure.
- [ ] If the environment is write-restricted, the deliverable is a runbook
      for a human executor, not a self-executed write.

## References
- PostgreSQL migration and backfill safety practices:
  https://oneuptime.com/blog/post/2026-02-02-postgresql-database-migrations/view
- Schema-migration safety patterns (batching, checkpointing):
  https://www.getdefacto.com/article/database-schema-migrations

## Composition
- Pairs with **airflow-dag-authoring** when the backfill runs through an
  orchestrated DAG rather than a standalone script — the DAG's `catchup`
  and idempotent-task design should follow the same principles.
- Shares its batching/UPSERT/checkpointing discipline with
  **database-migration-safety-review** at the schema-DDL altitude — same
  pattern, different object (data rows vs. table structure).
- Hands off to **data-quality-check-suite** to validate the backfilled
  range (row counts, distribution, freshness) once the run completes.
