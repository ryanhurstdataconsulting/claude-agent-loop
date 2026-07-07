---
name: explain-analyze-query-tuning
description: Use when a specific SQL query is slow and needs diagnosis — a dashboard timing out, an API endpoint with a growing p95, a batch job that used to finish in minutes and now takes hours, or a raw request to "make this query faster." Covers reading an EXPLAIN or EXPLAIN ANALYZE plan (seq scan vs. index scan, row-estimate mismatch, join order, disk spills), proposing an index or rewrite, and proving the fix with a before/after timing comparison. Triggers on "why is this query slow," "read this query plan," "EXPLAIN ANALYZE," a seq scan on a large table, or a planner row-estimate that is off by an order of magnitude.
---

# explain-analyze-query-tuning

## Overview
Diagnoses one slow SQL query end to end: capture its execution plan, read the
plan for the actual bottleneck, propose a fix, and prove the fix worked with
measured before/after timing. The one job it owns: no tuning claim ships
without a captured plan backing it up.

## When to use
- A specific query, endpoint, or report is measurably slower than expected.
- Someone hands over an `EXPLAIN` or `EXPLAIN ANALYZE` plan and asks what it
  means.
- A planner row estimate looks wrong (a `LIMIT 10` that scans a million
  rows, a nested loop over a set the planner thought was tiny).
- A query used to be fast and regressed after a data-volume change, a
  statistics staleness issue, or a schema change.

## Workflow
1. **Confirm safety before running anything.** For a pure `SELECT`,
   `EXPLAIN (ANALYZE, BUFFERS)` is safe to run directly — it executes the
   query for real but writes nothing. For `INSERT`/`UPDATE`/`DELETE`, only
   run `EXPLAIN ANALYZE` inside an explicit transaction that gets rolled
   back (`BEGIN; EXPLAIN ANALYZE ...; ROLLBACK;`), or use plain `EXPLAIN`
   (no `ANALYZE`) if a rollback is not an option. Never execute
   `EXPLAIN ANALYZE` on a write query against a live table without an
   explicit rollback plan.
2. **Capture a baseline plan first**, before changing anything:
   ```sql
   EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) <query>;
   ```
   Save the raw output — it is the evidence the "after" comparison is
   measured against.
3. **Read the plan bottom-up**, looking for the node that actually
   dominates `actual time`:
   - **Row-estimate mismatch.** Compare `rows=N` (the planner's estimate)
     against `actual rows=M`. An order-of-magnitude gap usually means stale
     statistics (`ANALYZE <table>;`) or a predicate the planner cannot
     estimate well (a function wrapped around an indexed column, a
     correlated subquery).
   - **Scan type.** A `Seq Scan` on a large table with a selective `WHERE`
     filter is a missing-index signal. An `Index Scan` with a high
     `Filter:` row-removal count means the index exists but does not cover
     the actual predicate.
   - **Join strategy and order.** A nested loop over a large outer set, or
     a hash/merge join built on the wrong side of a size-skewed join, both
     show up as an outsized `actual time` on the join node itself.
   - **Disk spills.** A `Sort` or `Hash` node reporting `Disk:` instead of
     staying in memory means the operation exceeded `work_mem` — either
     raise `work_mem` for the session/role or reduce the row count feeding
     the sort/hash earlier in the plan.
   - **Buffers.** A high `shared read` relative to `shared hit` means the
     working set is not cached; this can point at a memory-sizing issue as
     much as a query issue.
4. **Map the finding to a fix**, not a guess:
   - Missing or wrong-shaped index → hand off to an index-design pass.
   - Stale statistics → run `ANALYZE` on the table (cheap, safe, often the
     whole fix).
   - Function wrapping an indexed column (`WHERE lower(email) = ...`
     against a plain index on `email`) → either rewrite the predicate or
     add a matching expression index.
   - Implicit type cast defeating an index → cast explicitly in the query
     or align the column and literal types.
   - Poor join order the planner cannot fix on its own → rewrite as a CTE
     with an explicit materialization hint, or restructure the predicate so
     the planner can push it down.
5. **Re-run the identical `EXPLAIN (ANALYZE, BUFFERS)`** after the fix and
   record the before/after `actual time`, buffer counts, and any plan-shape
   change (e.g., `Seq Scan` → `Index Scan`). A tuning change with no
   re-measured plan is not verified.

## Checklist / quality gate
- [ ] Baseline `EXPLAIN (ANALYZE, BUFFERS)` output captured before any
      change.
- [ ] Row estimate vs. actual rows checked on every major plan node, not
      just the top one.
- [ ] The proposed fix is tied to a specific plan symptom (scan type,
      estimate mismatch, disk spill, join order) — not a speculative
      change.
- [ ] Fix re-measured with the same `EXPLAIN (ANALYZE, BUFFERS)` command;
      before/after numbers recorded together.
- [ ] No write query executed via `EXPLAIN ANALYZE` outside an explicit
      transaction with a rollback.

## References
- [PostgreSQL `EXPLAIN` documentation](https://www.postgresql.org/docs/current/using-explain.html)
- [EnterpriseDB — PostgreSQL query optimization and performance tuning with EXPLAIN ANALYZE](https://www.enterprisedb.com/blog/postgresql-query-optimization-performance-tuning-with-explain-analyze)
- [Crunchy Data — Get started with EXPLAIN ANALYZE](https://www.crunchydata.com/blog/get-started-with-explain-analyze)
- [Tiger Data — Best practices for query optimization in PostgreSQL](https://www.tigerdata.com/blog/best-practices-for-query-optimization-in-postgresql)

## Composition
Feeds `index-strategy-design` when the diagnosis points at a missing or
wrong-shaped index. Consumes `read-only-diagnostic-query-pack` output to
identify which query is worth this level of attention in the first place.
Hands off to `database-migration-safety-review` if the fix requires a
schema change (a new index or column) on a live table, rather than running
that DDL directly.
