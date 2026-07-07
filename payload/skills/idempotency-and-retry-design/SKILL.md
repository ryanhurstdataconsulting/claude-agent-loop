---
name: idempotency-and-retry-design
description: Use when any operation might be executed more than once for the same logical intent — a client retrying a timed-out request, a message queue redelivering, a backfill job being re-run after a partial failure, or a mobile client replaying a queued action after reconnecting. Triggers include "make this endpoint safe to retry", a duplicate-charge or duplicate-record bug traced to a retry, a request for an idempotency-key pattern, or designing exponential backoff for a flaky downstream dependency. Produces an idempotency-key scheme, a deduplication mechanism, and a retry/backoff policy that together guarantee at-least-once delivery never becomes more-than-once effect.
---

# idempotency-and-retry-design

## Overview
Provides the general-purpose pattern for making an operation safe to execute
more than once with the same intent — the shared discipline behind webhook
consumers, caching layers, offline-sync clients, and backfill jobs that would
otherwise each reinvent (or half-invent) the same dedup and retry logic. Owns
the idempotency-key contract and the backoff policy; specific consumers
(webhooks, mobile sync, batch backfills) apply it to their own transport.

## When to use
- Designing a new API endpoint, queue consumer, or batch job where a caller,
  network layer, or scheduler might deliver or invoke the same logical
  operation more than once.
- A duplicate-processing incident (duplicate charge, duplicate record,
  duplicate notification) is traced back to a retry or redelivery.
- A flaky downstream dependency needs a retry policy, and the current
  approach is either "retry forever" or "fail on the first error" — both of
  which cause real problems at scale.
- A mobile or offline-first client needs to replay a queue of pending actions
  after reconnecting without double-applying any of them.
- A batch or backfill job needs to be safely re-runnable after a partial
  failure, without reprocessing already-completed records or skipping ones
  that failed.

## Workflow
1. **Distinguish the two problems being solved.** Idempotency prevents a
   *repeated* operation from having more than the intended effect. Retry/
   backoff decides *whether and when* to repeat a failed operation. They are
   designed together but are not the same mechanism — an operation can be
   idempotent without any retry logic (a client-generated idempotency key on
   a one-shot request), and retry logic without idempotency is what causes
   duplicate-effect bugs in the first place.
2. **Choose the idempotency-key source.** Prefer a key the *caller* generates
   and owns for the life of the logical operation (a client-generated UUID
   sent with the request, reused verbatim on every retry of that same
   attempt) over a key derived server-side from payload content, which breaks
   if the payload legitimately changes between retries. For inbound
   events (webhooks, queue messages), use the sender's event ID if present.
3. **Persist the key with the operation's outcome, not just its existence.**
   A dedup store keyed on the idempotency key should record: pending,
   succeeded (with the result to return on a duplicate), or failed (with
   enough detail to decide whether a retry should proceed). A store that only
   tracks "have I seen this key" without the outcome cannot correctly answer
   a retry that arrives while the first attempt is still in flight.
4. **Close the concurrent-retry race.** Two copies of the same retry can
   arrive close enough together that a naive "check-then-act" dedup check
   allows both through. Use a database-level unique constraint or a
   compare-and-swap on the key's state (pending → succeeded) so the second
   concurrent attempt is rejected or made to wait, not double-executed.
5. **Scope the key correctly.** An idempotency key should be scoped to the
   specific operation and, where relevant, to the caller/tenant — a key that
   is globally unique but not tenant-scoped can accidentally collide across
   unrelated callers; a key that is too narrowly scoped can fail to catch a
   genuine duplicate.
6. **Design the retry policy for the failure, not with one policy for
   everything.** Classify failures before deciding to retry:
   - **Retryable** (timeout, connection reset, `503`/`429`) — retry with
     exponential backoff and jitter, capped at a maximum number of attempts
     or total elapsed time.
   - **Not retryable** (`400`/`422` validation failure, `401`/`403` auth
     failure, `404` on a resource that will not appear) — fail fast and
     surface the error; retrying a request that will never succeed only
     delays the failure and adds load.
   - **Ambiguous** (a request timed out with no confirmation of server-side
     effect) — this is exactly the case idempotency keys exist for: retry
     safely because the key guarantees the operation will not double-apply.
7. **Add jitter to backoff**, not just exponential growth — synchronized
   retries from many callers hitting the same downstream dependency at the
   same moment (a thundering herd) can turn a brief blip into an outage.
8. **Set a retry ceiling and a terminal path.** Every retry loop needs a
   maximum attempt count or elapsed-time budget, after which the operation
   routes to a dead-letter queue or surfaces to a human/caller — "retry
   forever" is not a policy, it is a deferred outage.
9. **Expire dedup records deliberately**, not never. Choose a TTL longer than
   the sender's maximum realistic redelivery window (check the vendor's or
   client's documented retry window), but not indefinite — an unbounded dedup
   store is a slow, silent storage leak.

## Checklist / quality gate
- The idempotency key is caller-generated (or sender-provided for inbound
  events) and stable across retries of the same logical attempt.
- The dedup store records outcome, not just presence, and closes the
  concurrent-retry race with a unique constraint or compare-and-swap.
- Failures are classified retryable vs. not-retryable before any retry logic
  runs — no blanket retry-everything policy.
- Backoff is exponential with jitter, and every retry loop has a maximum
  attempt count or time budget with a terminal (dead-letter or surfaced-error)
  path.
- Dedup records expire on a TTL longer than the realistic redelivery window,
  not indefinitely.

## References
- Stripe idempotency-key documentation — the widely adopted reference
  implementation for client-generated idempotency keys on API requests.
- Exponential-backoff-with-jitter guidance from distributed-systems and cloud
  architecture literature (the "thundering herd" problem and its standard
  mitigation).
- At-least-once-delivery semantics from message-queue and event-streaming
  documentation, as the baseline assumption this pattern is designed against.

## Composition
The shared primitive behind `implement-webhook-consumer-with-idempotency`
(inbound webhook redelivery), mobile offline-first sync retry queues, and
re-runnable batch/backfill jobs referenced from
`build-data-mapping-transform-layer`. Pairs with `add-structured-logging-and-tracing`
to correlate retried attempts of the same logical operation across logs.
