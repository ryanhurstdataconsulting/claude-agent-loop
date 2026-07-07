---
name: implement-webhook-consumer-with-idempotency
description: Use when building or hardening an endpoint that receives inbound webhooks from a vendor or partner system. Triggers include "consume webhooks from <vendor>", duplicate-processing bugs (a charge applied twice, a duplicate notification sent), signature-verification failures, out-of-order delivery, or a partner support ticket about a webhook that "didn't fire" when it actually fired more than once. Produces a receiver with signature verification, an idempotency-key dedup store, and retry/dead-letter handling.
---

# implement-webhook-consumer-with-idempotency

## Overview
Builds the receiving side of an inbound-webhook integration so that at-least-once
delivery — which is what nearly every webhook provider actually guarantees, despite
looser-sounding docs — never turns into duplicate side effects. Owns three things
together: verifying the request is genuinely from the vendor, deduplicating
redelivered events, and handling processing failures without silently dropping
data.

## When to use
- A new inbound webhook integration is being built from scratch.
- An existing webhook consumer has caused a duplicate-processing incident (double
  charge, double notification, double record creation).
- A partner reports "the webhook fired but nothing happened" — often a silent
  signature-verification failure or an unhandled exception with no dead-letter
  path.
- Webhook events are arriving out of order and downstream state is getting
  clobbered by a stale event overwriting a newer one.

## Workflow
1. **Verify the signature before touching the payload.** Compute the HMAC (or
   vendor-specific scheme) over the raw request body using the shared secret,
   compare with a constant-time comparison, and reject with `401`/`403` on
   mismatch — before any deserialization or business logic runs. Never trust an
   unsigned or unverifiable webhook. If the vendor supports a timestamp header
   alongside the signature, reject requests outside a tolerance window (for
   example, five minutes) to block replay attacks.
2. **Extract a stable idempotency key.** Prefer the vendor's own event ID; if
   none is provided, derive a key from a stable combination of fields (event
   type, resource ID, and a version/sequence number if present) — never from a
   field that can repeat across genuinely distinct events, like a timestamp
   alone.
3. **Check the dedup store before processing.** Look up the idempotency key in
   a persistent store (a dedicated table, or a keyed cache with a TTL long
   enough to outlast the vendor's redelivery window — often 24–72 hours). If
   the key exists and processing already completed, return success
   immediately without reprocessing. If the key exists but is mid-processing,
   return a retryable response rather than double-executing side effects —
   this is the race condition that naive dedup checks miss.
4. **Make the store write and the side effect atomic, or make the side effect
   itself idempotent.** The strongest pattern: write the dedup record inside
   the same transaction as the business-logic write. Where that is not
   possible (a call to a separate system), design the downstream operation to
   be safe to repeat — an upsert keyed on the same idempotency key rather than
   an insert or increment.
5. **Handle out-of-order delivery explicitly.** If the vendor does not
   guarantee ordering (most do not), compare an event's sequence number or
   timestamp against the last-applied value for that resource before
   overwriting state, and discard or queue events that arrive stale.
6. **Respond fast, process async for anything non-trivial.** Acknowledge
   receipt (`200`) as soon as the event is durably queued, then process
   asynchronously — a slow synchronous handler risks the vendor's delivery
   timeout, which triggers an unnecessary retry storm.
7. **Design retry and dead-letter handling for processing failures.**
   Transient failures (a downstream dependency timeout) should retry with
   exponential backoff and jitter; failures that will never succeed
   (a malformed payload, an unknown event type) should route straight to a
   dead-letter queue with enough context to replay manually, not retry
   forever.
8. **Instrument delivery health.** Track received-vs-processed counts,
   signature-verification failure rate, and dead-letter volume — a silent
   drop in received events usually means the vendor-side webhook configuration
   broke, not that traffic stopped.

## Checklist / quality gate
- Signature verification runs before any payload parsing, using a
  constant-time comparison, with an optional timestamp-tolerance replay guard.
- Every event has a stable idempotency key, and the dedup store is checked
  before any side effect runs.
- The mid-processing race (two redeliveries arriving concurrently) is closed,
  not just the already-completed case.
- Out-of-order delivery is either impossible by design or explicitly guarded
  with a sequence/timestamp comparison.
- Failures are triaged into retryable-with-backoff vs. dead-letter, not a
  single undifferentiated retry-forever loop.
- Delivery-health metrics exist and are wired to an alert on an unexplained
  drop in received events.

## References
- Stripe webhook signature verification and idempotency-key documentation —
  the de facto reference implementation most vendors' docs point back to.
- Contract-testing and consumer-driven-contract practice for keeping the
  receiver's assumptions about the payload shape verified against the
  vendor's actual contract.
- General at-least-once-delivery and dead-letter-queue patterns from
  distributed-systems and message-queue literature.

## Composition
Builds on the vendor-quirk reference produced by
`design-external-integration-with-vendor-quirks` (auth scheme, retry timing).
Shares its dedup and retry-with-backoff discipline with
`idempotency-and-retry-design`, which generalizes the same pattern to outbound
calls and backfills. Pairs with `add-structured-logging-and-tracing` for
correlating a webhook event through async processing.
