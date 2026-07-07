---
name: implement-offline-first-sync
description: Use when a mobile feature needs local persistence with server reconciliation — designing a conflict-resolution strategy (last-write-wins, merge, or user-prompt), a local database schema (Room, Core Data, SQLite, WatermelonDB), and a sync queue with retry for actions taken while offline. Triggers include "make this work offline", "queue writes when there's no connection", sync conflicts overwriting user data, a request to cache server data locally, or an app that loses in-progress user work whenever connectivity drops.
---

# implement-offline-first-sync

## Overview
Designs and scaffolds the local-persistence-plus-reconciliation layer that lets a mobile
feature keep working without connectivity and sync cleanly once it returns. The one job this
skill owns is the offline-write queue and conflict-resolution policy — not general local
caching of read-only data, which is a simpler problem that does not need this skill's
machinery.

## When to use
- A feature currently requires connectivity for every read or write, and the ask is to make it
  usable offline.
- Users report lost work (form submissions, edits) after a connectivity drop mid-action.
- Two clients editing the same record produce silent data loss — the last sync to hit the
  server wins with no user visibility into what was overwritten.
- A request explicitly mentions offline queueing, background sync, or a local-first data
  architecture.

## Workflow
1. **Classify the data by conflict risk before choosing a strategy.** Not everything needs the
   same policy:
   - Append-only or user-scoped data (a note only its author edits) → last-write-wins is
     usually fine; the risk of a real conflict is near zero.
   - Multi-user or multi-device shared state (a shared record, a counter, an inventory count)
     → needs either a merge strategy (CRDT-style, field-level merge) or an explicit
     user-facing conflict prompt — pick based on whether the data has a natural, safe merge
     function.
   - Financial or otherwise irreversible actions → never resolve automatically; queue the
     conflict for explicit user or backend adjudication.
2. **Design the local schema** (Room/SQLite on Android, Core Data/SQLite on iOS, WatermelonDB/
   SQLite on React Native) with an explicit sync-state column per record: `synced`,
   `pending_create`, `pending_update`, `pending_delete`, `conflict`. Do not rely on timestamp
   comparison alone to infer sync state — make it an explicit field.
3. **Build the write path to always hit local storage first**, then enqueue a sync job — never
   block a user action on network availability. The UI reflects the local write immediately;
   the sync queue reconciles with the server asynchronously.
4. **Build the sync queue with retry and backoff:**
   - Persist the queue itself (not just in-memory) so pending actions survive an app kill.
   - Retry with exponential backoff on network failure; distinguish a transient failure (retry)
     from a rejected request (surface to the user, do not silently retry a 4xx forever).
   - Process the queue in order per record to avoid out-of-order writes clobbering each other;
     cross-record ordering usually does not matter and can parallelize.
5. **Use an idempotency key on every queued mutation** so a retried request that actually
   succeeded server-side (but whose response was lost) does not double-apply. Reuse the
   idempotency/retry pattern rather than inventing a new dedup scheme per feature.
6. **Surface conflicts, don't hide them**, for any data classified as needing a user prompt in
   step 1 — a silent overwrite is worse than an explicit "keep mine / keep theirs / merge"
   choice, even if it costs a UI affordance.
7. **Trigger sync on connectivity restore and on a periodic background interval**, not only on
   app foreground — a user who stays backgrounded for hours should not return to a stale queue.
8. **Test the queue under realistic failure injection**: kill the app mid-sync, simulate a
   network drop between request-sent and response-received, and confirm no duplicate writes and
   no lost writes in either case.

## Checklist / quality gate
- [ ] Every write path hits local storage first; no user action blocks on network availability.
- [ ] The sync queue persists across app restarts/kills, not just in memory.
- [ ] Every queued mutation carries an idempotency key.
- [ ] Conflict-resolution policy is chosen deliberately per data type (last-write-wins, merge,
      or user-prompt) — not defaulted to last-write-wins everywhere.
- [ ] Rejected requests (4xx) are surfaced, not retried indefinitely as if transient.
- [ ] A kill-mid-sync test and a response-lost test both show no duplicate and no lost writes.

## References
- [Android Developer Roadmap](https://roadmap.sh/android)
- [iOS Developer Roadmap](https://roadmap.sh/ios)
- Android offline-first guidance: [Build an offline-first app — developer.android.com](https://developer.android.com/topic/architecture/data-layer/offline-first)

## Composition
Shares its idempotency/retry discipline with the cross-cutting
`implement-webhook-consumer-with-idempotency` skill — reuse the same dedup-key pattern on both
sides of a sync relationship. Consumed by `scaffold-mobile-screen-with-viewmodel` whenever a new
screen's state holder needs to read from and write to a syncing local store rather than a
simple network call. Hands off to `integrate-crash-reporting-and-monitoring` to alert on sync
failures that exceed a retry budget.
