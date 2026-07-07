---
name: connection-pool-and-vacuum-tuning
description: Use when a database shows connection exhaustion ("too many connections," "FATAL: sorry, too many clients already," pool-exhaustion errors under load) or table bloat and autovacuum falling behind. Covers a pgBouncer pool-mode decision tree (session vs. transaction vs. statement pooling), pool sizing, an autovacuum-threshold tuning checklist, a bloat-detection query, and tying every recommendation to a measured symptom rather than a generic default change. Triggers on connection-limit errors, growing table bloat, autovacuum lag, or a request to tune pgBouncer or autovacuum settings.
---

# connection-pool-and-vacuum-tuning

## Overview
Diagnoses and tunes the two most common resource-exhaustion problems on a
relational database — connection pooling and autovacuum/bloat — and ties
every recommendation to a measured symptom instead of a generic
configuration change. The one job it owns: confirm root cause before
touching a pool-mode or autovacuum setting, since the two problems are
easy to mistake for each other.

## When to use
- The application or database is returning connection-limit errors (`too
  many connections`, a pool-exhaustion error from the application's own
  pool client) under load.
- A table shows growing bloat, or `autovacuum` is falling behind on a
  high-write table.
- Query latency has degraded and connection contention or dead-tuple bloat
  is a suspect alongside (or instead of) a query-plan problem.
- Someone asks to tune pgBouncer or `autovacuum` settings directly, without
  a diagnosis already done.

## Workflow
1. **Diagnose which problem it actually is before tuning anything.** Pull
   the connection/lock and autovacuum-lag queries from a read-only
   diagnostic pass first — a symptom that looks like "the pool is too
   small" is sometimes actually "a long-running transaction is holding
   connections open and blocking vacuum," which no amount of pool resizing
   fixes.
2. **Work the connection-pooling decision tree** (pgBouncer as the
   reference pooler):
   - **Session pooling** — a connection is assigned to a client for the
     entire session. Required only when the application depends on
     session-level state (advisory locks held across statements, prepared
     statements reused across a session, `SET` values expected to persist).
     Gives the least connection reuse.
   - **Transaction pooling** — a connection returns to the pool after each
     transaction commits or rolls back. The right default for most
     applications; breaks anything that depends on session-level state
     persisting between transactions.
   - **Statement pooling** — a connection returns to the pool after each
     statement. Rarely appropriate; breaks multi-statement transactions
     outright.
   - **Size the pool to the database, not the app fleet.** `pool_size`
     should sit well below the database's `max_connections`, sized to the
     number of CPU cores or the expected number of genuinely concurrent
     active queries — not to the number of application instances, which
     tends to wildly overshoot what the database can actually execute in
     parallel.
3. **Work the autovacuum-tuning checklist:**
   - **Check for the wraparound emergency signal first.**
     `age(relfrozenxid)` approaching `autovacuum_freeze_max_age` on any
     table is a hard emergency, not a tuning nicety — it takes priority
     over everything else on this list.
   - **Check for a long-running or idle-in-transaction session blocking
     vacuum.** A transaction left open holds back the oldest `xmin`
     horizon, which prevents vacuum from reclaiming dead tuples database
     wide — this is often the actual root cause behind "autovacuum isn't
     keeping up," and no autovacuum setting change fixes it.
   - **Tune hot tables individually, not the global default.** Lower
     `autovacuum_vacuum_scale_factor` and raise
     `autovacuum_vacuum_cost_limit` as a per-table `ALTER TABLE ... SET
     (...)` override on specific high-churn tables, so busy tables get
     vacuumed more aggressively without changing behavior for quiet ones
     across the whole database.
   - **Detect bloat with a dead-tuple ratio or `pgstattuple`.** Compare
     `pg_relation_size` against an estimated live size; a large,
     persistent gap after normal vacuum has run indicates bloat that
     `VACUUM` alone will not reclaim as physical space. `VACUUM FULL`
     reclaims it but takes an exclusive lock for the operation's duration;
     `pg_repack` reclaims it with much less disruption and is the better
     choice on a table with live traffic. Schedule either outside a
     high-traffic window.
4. **State every recommendation against a measured symptom.** "Connection
   exhaustion caused by N application instances each holding M idle
   connections open" or "table X is at a 40% dead-tuple ratio because
   autovacuum has been blocked for six days by an idle-in-transaction
   session" — not a generic "increase `max_connections`" or "tune
   autovacuum more aggressively" with no measurement behind it.

## Checklist / quality gate
- [ ] Root cause confirmed as pooling, vacuum, or both, before recommending
      any configuration change.
- [ ] Pool mode choice matches the application's actual session-state
      usage (checked, not assumed).
- [ ] `pool_size` sized against available database connections and cores,
      not guessed or copied from another project.
- [ ] Any per-table autovacuum override is tied to a measured dead-tuple
      ratio on that specific table.
- [ ] Long-running or idle-in-transaction sessions checked as a vacuum
      blocker before any autovacuum setting is touched.
- [ ] `VACUUM FULL` (or `pg_repack`) recommended only with an explicit
      note on its lock behavior and a maintenance-window scheduling
      consideration.

## References
- [PostgreSQL — Routine Vacuuming documentation](https://www.postgresql.org/docs/current/routine-vacuuming.html)
- [pgBouncer — official documentation on pool modes](https://www.pgbouncer.org/config.html)

## Composition
Consumes lock-contention, connection, and autovacuum-lag findings from
`read-only-diagnostic-query-pack` as its evidence base — this skill acts on
what that one surfaces, rather than re-deriving the diagnosis. Pairs with
`index-strategy-design`, since write-heavy tables carrying many indexes
amplify vacuum cost and are a common root cause behind bloat findings.
Complements `capacity-planning-forecast` for longer-horizon sizing decisions
that go beyond resolving a single incident.
