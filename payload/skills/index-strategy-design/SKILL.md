---
name: index-strategy-design
description: Use when recurring slow queries against a table point to a missing or wrong index, when someone asks "what index should I add here," or when a table needs an index audit for duplicates and unused entries before a cleanup. Covers choosing an index type (B-tree, GIN, GiST, BRIN, partial, covering, multi-column), weighing the read/write tradeoff of adding one, and auditing existing indexes with pg_stat_user_indexes. Triggers on "add an index," "which index type," "unused index," "duplicate index," or a query plan showing a sequential scan that a targeted index should eliminate.
---

# index-strategy-design

## Overview
Designs the right index for a measured query pattern — the correct type,
column order, and scope — and audits existing indexes for duplicates or
dead weight. The one job it owns: every index recommendation ties back to a
representative query, never a speculative "might help."

## When to use
- A query plan shows a sequential scan on a large table against a selective
  filter, sort, or join key.
- A recurring slow-query pattern spans several similar queries, not just
  one, and needs a single index (or small set) that serves all of them.
- A table's index list has grown organically and needs an audit for
  duplicate, overlapping, or unused indexes before a cleanup.
- Write latency or table bloat has increased and an over-indexed table is a
  suspect.

## Workflow
1. **Collect representative queries first.** Gather two or three real
   queries the index needs to serve — not one synthetic example. An index
   tuned to a single query often fails the others that hit the same table.
2. **Choose the index type by predicate shape:**
   - **B-tree (default)** — equality and range predicates, `ORDER BY`,
     `<`/`>`/`BETWEEN`. Correct choice unless a specific reason points
     elsewhere.
   - **GIN** — full-text search (`tsvector`), JSONB containment (`@>`),
     array membership (`@>`, `&&`). Slower to write, fast to query.
   - **GiST** — geometric types, range types, nearest-neighbor search, or
     any type with a custom operator class GIN does not support.
   - **BRIN** — very large tables with a natural physical ordering (an
     append-only, timestamp-ordered event log). Tiny compared to a B-tree
     on the same column, at the cost of being effective only when physical
     and logical order correlate.
   - **Partial index** — the query always filters on a fixed condition
     (`WHERE deleted_at IS NULL`, `WHERE status = 'active'`). Index only
     the relevant subset; smaller and cheaper to maintain than a full
     index.
   - **Covering / index-only** — add `INCLUDE`d columns so the planner can
     satisfy the query from the index alone, without a heap fetch.
   - **Multi-column** — order columns by equality predicates first, most
     selective first, then the range/sort column last. Column order
     determines whether the index serves a given query at all.
3. **Weigh the read/write tradeoff before adding.** Every index adds write
   overhead (each `INSERT`/`UPDATE` on an indexed column touches every
   index on that table) and storage. Do not add an index on a hunch — tie
   it to a measured query pattern from step 1, and prefer extending an
   existing index (adding a column, converting to a covering index) over
   creating a near-duplicate.
4. **Audit for duplicate or unused indexes** before adding anything new:
   ```sql
   -- Unused indexes (never scanned since the last stats reset)
   SELECT schemaname, relname, indexrelname, idx_scan, pg_size_pretty(pg_relation_size(indexrelid))
   FROM pg_stat_user_indexes
   WHERE idx_scan = 0
   ORDER BY pg_relation_size(indexrelid) DESC;

   -- Candidate duplicates: same table, overlapping leading columns
   SELECT indrelid::regclass AS table_name, indexrelid::regclass AS index_name, indkey
   FROM pg_index
   WHERE indrelid = 'target_table'::regclass
   ORDER BY indkey;
   ```
   A near-zero `idx_scan` count on an index older than a full traffic cycle
   is a drop candidate; confirm it is not used by a rarely run report or
   an off-hours batch job before dropping it.
5. **Build without blocking writes.** On a table live traffic touches, use
   `CREATE INDEX CONCURRENTLY` — it takes longer and cannot run inside a
   transaction block, but avoids the exclusive lock a plain `CREATE INDEX`
   holds for the build's duration. If a concurrent build fails partway, it
   can leave an invalid index behind; check `pg_index.indisvalid` and drop
   and retry rather than assuming success.
6. **Validate with a plan comparison.** Hand off to a query-tuning pass
   (`EXPLAIN (ANALYZE, BUFFERS)` before and after) to confirm the planner
   actually picks the new index and that it produces the expected speedup —
   an unused index is worse than no index at all.

## Checklist / quality gate
- [ ] Index type matches the predicate shape of the representative queries
      collected, not just a default guess.
- [ ] Validated against two or more real queries, not a single example.
- [ ] Checked for an existing overlapping or duplicate index before adding
      a new one.
- [ ] Built with `CREATE INDEX CONCURRENTLY` on any table with live
      traffic; validity confirmed after the build.
- [ ] Before/after `EXPLAIN ANALYZE` confirms the planner picks the new
      index.
- [ ] Unused-index audit run and any zero-scan indexes flagged (not
      silently dropped without confirming no scheduled job needs them).

## References
- [Tiger Data — Best practices for query optimization in PostgreSQL](https://www.tigerdata.com/blog/best-practices-for-query-optimization-in-postgresql)
- [PostgreSQL performance tips documentation](https://www.postgresql.org/docs/current/performance-tips.html)

## Composition
Consumes findings from `explain-analyze-query-tuning` (the plan diagnosis
that identifies the missing index in the first place) and from
`read-only-diagnostic-query-pack` (index-scan and bloat statistics that
surface unused-index candidates). Hands the actual `CREATE INDEX` /
`DROP INDEX` statement to `database-migration-safety-review` before it
ships against a live table. Complements `connection-pool-and-vacuum-tuning`
— write-heavy tables with many indexes amplify vacuum cost, so the two
tradeoffs should be weighed together.
