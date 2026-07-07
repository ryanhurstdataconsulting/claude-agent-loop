---
name: build-data-mapping-transform-layer
description: Use when syncing or transforming data between two systems with mismatched schemas — a CRM, ERP, payment gateway, or any external system whose field names, types, or semantics differ from the internal model. Triggers include "map fields from <vendor> into our schema", a sync job silently dropping or corrupting records, a field-type mismatch (a string where a number is expected, a null where a required field is assumed present), or a request to detect drift between two systems that should be in sync. Produces a field-mapping spec, a tested transform layer, and a reconciliation job.
---

# build-data-mapping-transform-layer

## Overview
Builds the translation layer that lets two systems with different schemas
exchange data correctly and stay correct over time. Owns three artifacts
together: an explicit field-mapping specification (not tribal knowledge), a
transform layer with unit tests covering the edge cases, and a reconciliation
job that catches drift before it becomes a silent data-quality incident.

## When to use
- Two systems (internal service and a CRM/ERP/payment gateway/partner API)
  need their data kept in sync and their schemas do not match field-for-field.
- An existing sync job has a history of dropping, truncating, or misassigning
  data — a strong signal that the mapping was implicit in code rather than
  specified and tested.
- A new field is being added on one side and it is unclear whether or how it
  should map to the other system.
- Two systems that should agree on a value (a status, a total, a count) have
  drifted, and nobody can say when or why.

## Workflow
1. **Write the field-mapping spec before writing transform code.** For every
   field: source field name and type, destination field name and type, the
   transform rule (direct copy, type coercion, lookup/enum translation,
   computed/derived value), and explicit handling for null/missing on either
   side. Treat an unmapped field as a deliberate decision to record ("dropped,
   not needed") rather than an oversight to discover later.
2. **Resolve type and semantic mismatches explicitly**, not through implicit
   coercion. Common trouble spots: different units (cents vs. dollars,
   kilometers vs. miles), different timezone or date-format assumptions,
   enum values that do not have a 1:1 mapping (a source status with more
   granularity than the destination supports), and different null semantics
   (a source system that uses an empty string where the destination expects
   an actual `null`).
3. **Decide direction and conflict resolution up front.** One-way sync is
   simplest; bidirectional sync needs an explicit last-write-wins,
   field-level-merge, or manual-review policy for conflicting concurrent
   updates — pick this before writing code, since it shapes the transform
   layer's error paths.
4. **Build the transform layer as pure, independently testable functions** —
   one function per entity or field group, not a monolithic sync script. Each
   function takes a source record and returns a destination record (or an
   explicit rejection with a reason), with no side effects, so it can be unit
   tested against a fixture set covering: the happy path, every null/missing
   field case from the spec, a malformed/unexpected value, and an enum value
   not present in the mapping table.
5. **Fail loud on unmapped or unexpected values, not silent.** An enum value
   the mapping table has never seen should raise or route to a review queue,
   never silently map to a default that might be wrong. A default that
   "seems safe" is exactly how a quiet data-corruption bug survives for
   months.
6. **Build the reconciliation job.** On a schedule (or after each sync run),
   compare a sample or full set of records between the two systems on a
   handful of high-value fields, and alert on drift beyond a defined
   tolerance. This is the safety net that catches mapping bugs the unit tests
   did not anticipate, plus drift introduced by manual edits on either side.
7. **Version the mapping spec alongside the transform code.** When a source
   or destination schema changes, the spec update and the code update land in
   the same change — a stale spec is worse than no spec, because it looks
   authoritative while being wrong.

## Checklist / quality gate
- A field-mapping spec exists, covers every field on both sides (including
  explicitly dropped fields), and is checked into version control next to the
  code.
- Every transform function has unit tests covering null/missing, malformed,
  and unmapped-enum-value cases — not only the happy path.
- Unmapped or unexpected values fail loud (reject, log, or route to review),
  never silently default.
- Conflict-resolution policy for bidirectional sync is documented, not
  implicit in code order.
- A reconciliation job runs on a schedule and alerts on drift beyond a stated
  tolerance.
- The mapping spec and transform code are updated together whenever either
  schema changes.

## References
- API integration and SaaS-to-SaaS synchronization best-practice guidance on
  field mapping, schema drift, and reconciliation (general API-integration
  practice literature).
- Data-quality-check-suite patterns for reconciliation and drift-detection
  job design, adapted here to a two-system sync context rather than a single
  warehouse.

## Composition
Often follows `design-external-integration-with-vendor-quirks` once the
vendor's schema and quirks are understood. Shares its rigorous null/edge-case
testing discipline with `write-openapi-spec-and-contract-tests`. Pairs with
`idempotency-and-retry-design` when the sync job itself needs to be safely
re-runnable (a backfill or a retried batch) without duplicating records.
