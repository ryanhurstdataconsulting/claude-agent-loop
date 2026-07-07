---
name: plan-zero-downtime-migration
description: Use when a large-scale schema, service, data-store, or platform migration needs to ship without a maintenance window — a table rename or column-type change on a live table, splitting a service's database, swapping a data store, or cutting a client over between two backend implementations. Triggers include "how do we migrate this without downtime," "we can't take an outage window," a schema change on a high-traffic table, a request for a rollback plan, or "dual-write" / "backfill" / "cutover" appearing in a design discussion. Produces an expand/contract phase plan with explicit dual-write, backfill, verification, and rollback-trigger steps per phase.
---

# plan-zero-downtime-migration

## Overview
Turns "we need to migrate X without an outage" into a phased plan using the
expand/contract pattern: add the new shape alongside the old, move traffic and data
over gradually with verification at each step, then remove the old shape only once
everything depends on the new one. This skill owns the *plan* — the phase sequence,
the dual-write/backfill mechanics, and the rollback trigger for each phase — not the
migration code itself, which is typically handled by a scaffolding skill downstream.

## When to use
- A schema change (column type, rename, split, new constraint) is needed on a table
  that cannot take a lock or downtime window.
- A service's data store is being split, merged, or replaced (Postgres → a different
  engine, a monolith's shared database being carved apart per service).
- Two backend implementations need a gradual client cutover (old service → new
  service) with the ability to revert mid-flight.
- A request explicitly asks for a rollback plan, a phased rollout, or mentions
  "dual-write," "backfill," or "cutover."
- A prior migration attempt caused an incident and the redo needs an explicit
  verification gate between phases.

## Workflow

**1. State the end state and the current state precisely** before phasing anything.
   Write both schemas/systems down side by side — most migration plans fail not in
   the mechanics but because the target shape was underspecified (e.g., "make the
   column nullable" without saying what happens to existing NULL-intolerant readers).

**2. Apply the expand/contract skeleton.** Four phases, always in this order, never
   collapsed:

   - **Expand** — add the new shape without removing the old. New column, new table,
     new service endpoint, new topic — additive only. The system must be fully
     functional with only the old shape in use at the end of this phase; nothing
     reads the new shape yet.
   - **Migrate (dual-write + backfill)** — the application writes to *both* old and
     new shapes simultaneously (dual-write) while a background job backfills
     historical data into the new shape. Reads still come from the old shape only.
     This is the highest-risk phase — see step 3.
   - **Cutover** — reads switch to the new shape, typically behind a feature flag or
     staged rollout (a percentage of traffic, then all of it). The old shape keeps
     receiving writes during this phase so a revert is still cheap.
   - **Contract** — once 100% of reads and writes are confirmed on the new shape for
     a soak period, stop writing to the old shape, then remove it (drop the column,
     decommission the old service, delete the old topic). This phase is only safe
     once rollback is no longer required — it is the one phase that is *not*
     trivially reversible.

**3. Design dual-write for consistency, not just presence.** Dual-writing to two
   stores is not itself safe — decide explicitly:
   - **Write order and failure handling**: if the write to the new store fails after
     the old store succeeds (or vice versa), does the whole operation fail, or does
     it proceed with a reconciliation job catching the drift later? State this per
     migration; "best effort" silently chosen by default is how the two stores drift.
   - **Backfill vs. live traffic race**: the backfill job and live dual-writes can
     race on the same row. Use a backfill strategy that is safe against this — e.g.,
     only backfill rows the dual-write hasn't already touched (a watermark or
     updated-at cursor), or make the backfill idempotent so a re-run is harmless.
   - **Verification before cutover**: run a reconciliation check (row counts, checksum
     sample, or a shadow-read comparison) comparing old and new shapes before flipping
     any read traffic. Cutting over without this step is the single most common cause
     of a "the migration looked fine until users started reporting stale/wrong data."

**4. Name a rollback trigger for every phase**, not just a generic "roll back if
   something breaks":
   - **Expand** — rollback is a no-op deploy revert; the old shape was never touched.
   - **Migrate** — rollback means turning off dual-write; the new store is simply
     abandoned or discarded. State the condition that triggers this (error-rate
     threshold, backfill-consistency check failing, an explicit go/no-go review).
   - **Cutover** — rollback means flipping the read flag back to the old shape;
     confirm the old shape is still receiving writes and hasn't started to drift
     stale during the cutover soak.
   - **Contract** — state explicitly that this phase has **no rollback** once
     executed, and gate it behind a soak period (a stated number of days of clean
     operation on the new shape) plus an explicit human go/no-go, not an automatic
     timer.

**5. Size the backfill for the actual table/data volume.** For large tables, batch
   the backfill (bounded transactions, not one giant `UPDATE`) to avoid long locks or
   replication lag, and throttle it against production load. Call this out explicitly
   when the migration involves a high-traffic or large table — this is where naive
   plans cause the exact outage the plan was meant to avoid.

**Common gotchas:**
- Collapsing dual-write and cutover into one deploy — this removes the safety margin
  the whole pattern exists to provide.
- Treating the contract phase as reversible — it generally is not; drop it behind an
  explicit, delayed, human-approved gate.
- A backfill job that isn't idempotent, so retrying after a partial failure
  double-processes rows.
- No reconciliation step before cutover — the plan "worked" until the first
  data-integrity bug report weeks later.

## Checklist / quality gate
- [ ] Current-state and target-state shapes are both written down explicitly.
- [ ] All four phases (expand, migrate, cutover, contract) are present and in order —
      none collapsed together.
- [ ] Dual-write failure handling (fail-both vs. reconcile-later) is stated, not
      left as an unstated default.
- [ ] Backfill strategy is idempotent and race-safe against concurrent dual-writes.
- [ ] A verification/reconciliation step exists before the cutover phase.
- [ ] Each phase names its own rollback trigger and mechanism; the contract phase
      is explicitly flagged as non-reversible and gated behind a soak period.
- [ ] Large-table backfills are batched and throttled, not a single unbounded
      operation.
- [ ] The plan is presented as a draft for a human owner to approve the cutover and
      contract go/no-go — the agent does not authorize the irreversible step.

## References
- [Backend Developer Roadmap — Databases and Caching](https://roadmap.sh/backend)
- Expand/contract migration pattern — established industry practice for zero-downtime
  schema and service migrations (no single canonical source; cross-reference against
  your organization's own prior migration postmortems where available).

## Composition
- Consumes a boundary or store decision from `design-service-boundary-and-api-contract`
  when the migration is splitting or replacing a service's data store.
- Often cites, or should be recorded in, an `adr-authoring` record — a migration of
  this scale is exactly the kind of hard-to-reverse decision an ADR exists to capture.
- Hands off to `write-database-migration-with-rollback` for the forward/rollback
  migration-file mechanics within a single phase.
- Pairs with `run-architecture-review-checklist` for a pre-launch review of the full
  migration plan before the cutover phase begins.
