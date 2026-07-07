---
name: read-only-diagnostic-query-pack
description: Use to profile a database's health when only a read-only credential or role is available — no DDL, no DML, no write access at all. Covers a curated library of read-only queries (top-offender queries from pg_stat_statements, table/index bloat estimates, connection and lock contention, autovacuum lag, cache hit ratio, replication lag) each wrapped by default in a read-only transaction with a bounded statement timeout. Triggers on "check database health with a read-only account," "profile this database without touching it," "what's slow, with no write access," or a project rule stating all database access must be read-only.
---

# read-only-diagnostic-query-pack

## Overview
A curated library of read-only diagnostic queries for profiling database
health, each run under a default safety wrapper — a read-only transaction
with a bounded statement timeout — so diagnosis never risks a write, even
by accident. The one job it owns: surface what is wrong without touching
anything. Fixing what is found is a different skill's job.

## When to use
- The only database credential available is read-only, or a project rule
  requires all database access to be read-only regardless of the
  credential's actual permissions.
- Someone needs a database health check ("what's slow," "any lock
  contention," "is autovacuum keeping up") without a specific query already
  identified as the culprit.
- A recurring health-check routine needs a standard query set rather than
  ad hoc, one-off queries written from scratch each time.

## Workflow
1. **Wrap every query by default**, with no exceptions, before running
   anything:
   ```sql
   BEGIN;
   SET TRANSACTION READ ONLY;
   SET statement_timeout = '30s';
   -- diagnostic query here
   COMMIT;
   ```
   The read-only flag rejects any accidental write inside the transaction;
   the timeout prevents a runaway diagnostic query from adding load to an
   already-struggling database.
2. **Run the relevant category from the pack** rather than writing a new
   query from scratch each time:
   - **Top offenders** — requires the `pg_stat_statements` extension:
     ```sql
     SELECT query, calls, total_exec_time, mean_exec_time, rows
     FROM pg_stat_statements
     ORDER BY total_exec_time DESC
     LIMIT 20;
     ```
     If the extension is not enabled and cannot be (a read-only role
     cannot `CREATE EXTENSION`), fall back to repeated sampling of
     `pg_stat_activity` to approximate which queries are running longest
     and most often.
   - **Table/index bloat estimate:**
     ```sql
     SELECT relname, n_dead_tup, n_live_tup,
            round(n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0), 3) AS dead_ratio
     FROM pg_stat_user_tables
     ORDER BY n_dead_tup DESC
     LIMIT 20;
     ```
   - **Connection and lock contention:**
     ```sql
     SELECT pid, state, wait_event_type, wait_event, query, now() - query_start AS running_for
     FROM pg_stat_activity
     WHERE state != 'idle'
     ORDER BY running_for DESC;
     ```
     Join `pg_locks` on `pid` to find blocking chains when a query is
     stuck waiting rather than running.
   - **Autovacuum lag:**
     ```sql
     SELECT relname, last_autovacuum, last_autoanalyze, n_dead_tup
     FROM pg_stat_user_tables
     ORDER BY n_dead_tup DESC
     LIMIT 20;
     ```
     A `last_autovacuum` far in the past on a high-write table, paired
     with a high dead-tuple count, is the signal worth escalating.
   - **Cache hit ratio:**
     ```sql
     SELECT relname,
            heap_blks_hit::float / NULLIF(heap_blks_hit + heap_blks_read, 0) AS hit_ratio
     FROM pg_statio_user_tables
     ORDER BY hit_ratio ASC NULLS LAST
     LIMIT 20;
     ```
   - **Replication lag** (only where replicas exist):
     ```sql
     SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn
     FROM pg_stat_replication;
     ```
3. **Summarize, do not dump.** Report the top two or three issues that
   actually matter, with the numbers that back each one, rather than
   pasting forty rows of raw output. A health check that produces a wall
   of numbers with no interpretation has not done the diagnostic job.
4. **Hand off findings rather than fixing them here.** This skill's job
   ends at diagnosis — route a slow-query finding to a query-tuning skill,
   an indexing finding to an index-design skill, and a pooling or vacuum
   finding to a connection/vacuum-tuning skill.

## Checklist / quality gate
- [ ] Every query executed inside a `READ ONLY` transaction with a bounded
      `statement_timeout` — no exceptions, including "just checking one
      thing."
- [ ] No query in the run contains `INSERT`, `UPDATE`, `DELETE`, or any DDL
      statement.
- [ ] Findings summarized to what matters (top few issues with supporting
      numbers), not a raw table dump.
- [ ] Any finding that needs a fix is handed off to the appropriate
      skill rather than resolved inline.

## References
- [PostgreSQL — `pg_stat_statements` documentation](https://www.postgresql.org/docs/current/pgstatstatements.html)
- [PostgreSQL — The Cumulative Statistics System (`pg_stat_activity`, `pg_locks`, `pg_stat_user_tables`)](https://www.postgresql.org/docs/current/monitoring-stats.html)

## Composition
Feeds `explain-analyze-query-tuning` (identifies which specific query
deserves a full plan-level diagnosis) and `index-strategy-design`
(surfaces missing-index candidates via scan patterns and unused-index
scores). Supplies the evidence base for
`connection-pool-and-vacuum-tuning` (lock contention and autovacuum-lag
findings) and for the lock-duration estimates in
`database-migration-safety-review`. The read-only-transaction wrapper
pattern here is the default any database-diagnostic skill should reuse
before running an ad hoc query against a live database.
