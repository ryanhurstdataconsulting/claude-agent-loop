---
name: profile-and-fix-slow-request
description: Use when a user reports "this is slow," a specific endpoint or page shows a measured latency regression, or a request/response cycle needs diagnosis across the network, API, database, and render layers. Triggers include a slow page-load or API-timeout complaint, a spike in p95/p99 latency on a dashboard, a suspected N+1 query, or a task that says "profile this" or "why is X slow." Also load it once a bottleneck is found and needs a fix — this skill owns both the bisection workflow that locates the problem and the fix patterns matched to each layer, though the final trade-off call on a fix stays with a human.
---

# profile-and-fix-slow-request

## Overview
Bisects a slow request across the four layers it typically passes through —
network, API, database, render — to isolate where time is actually being
spent, then proposes a fix matched to that layer. It owns the diagnosis
workflow; a human still signs off on the fix, since the cheap fix (add an
index) and the right fix (redesign the query) are not always the same one.

## When to use
- A user or dashboard reports a specific slow page, endpoint, or interaction,
  with or without a number attached.
- p95 or p99 latency has regressed and the cause is not obvious from a code
  read alone.
- A loop over rows is suspected to be issuing one query per row (N+1).
- A fix has already been proposed ("just add caching," "just add an index")
  and needs to be verified against the actual bottleneck before landing.

## Workflow

**1. Reproduce with a measurement, not a guess.** Capture a browser network
waterfall, an HTTP client's timing breakdown (for example `curl -w`), or an
equivalent trace for the actual slow request. Note total time, time to first
byte, and how much of that is DNS/TLS/queueing versus body transfer.

**2. Bisect layer by layer, in this order:**
- **Network** — DNS/TLS/CDN overhead, uncompressed payloads, missing
  multiplexing, or a waterfall showing serial requests that could run in
  parallel.
- **API / application** — add timing around the handler; is time spent in
  business logic, serialization, or waiting on a downstream call?
- **Database** — enable query logging or an execution-plan explain on every
  query the request triggers. Look first for an N+1 pattern (one query per
  row in a loop) before assuming the fix is an index.
- **Render (client)** — for frontend-bound slowness, profile main-thread
  work: layout thrashing, large re-renders, or an unmemoized expensive
  computation running on every render.

**3. Confirm the bottleneck quantitatively before proposing a fix.** The
layer responsible should account for the dominant share of total latency, not
just look slow in isolation.

**4. Match the fix to the diagnosed cause:**
| Bottleneck | Fix |
|---|---|
| N+1 queries | Batch or eager-load the related rows — not a blanket index |
| Missing index | Confirm with an execution plan, add the narrowest index that satisfies the query, and verify the plan changes from a sequential or nested-loop scan |
| Chatty network | Batch requests or add caching; cache-invalidation strategy is a design decision — escalate to a human |
| Render-bound | Memoize, virtualize long lists, or code-split |

**5. Re-measure using the same method from step 1, before and after.** A fix
without a recorded before/after delta is not verified.

## Checklist / quality gate
- [ ] Bottleneck identified from a measurement (trace, execution plan, or
      profiler output), not inferred from a code read alone
- [ ] The isolated layer accounts for the dominant share of total latency
- [ ] The fix matches the diagnosed cause, not a generic caching or
      indexing reflex
- [ ] Before/after measurement captured using the same method
- [ ] Any caching or invalidation-strategy decision flagged to a human
      before it lands
- [ ] Both a typical-case metric (p50) and a tail metric (p95/p99) are
      checked, not just the one that triggered the report

## Gotchas
- A slow p50 and a slow p99 usually have different causes — a slow median
  points to a systemic issue, a slow tail points to contention, garbage
  collection, or a cold cache. Fixing one does not fix the other.
- Local development environments hide network and cold-cache effects; profile
  against a production-like environment or production-scale data volume.
- Caching can mask a real fix. A cache hit that lowers the number does not fix
  an underlying N+1 query — it just hides the cost until the cache misses.

## References
- [Full Stack Developer Roadmap](https://roadmap.sh/full-stack)

## Composition
Shares its bisection shape with a Core Web Vitals audit skill for the
frontend-only case, and with a caching-layer skill once the fix is "cache
this." Hands the database-layer diagnosis to a query-tuning skill when the
bottleneck is a complex execution plan. Pairs with a structured-logging and
tracing skill so future regressions surface without a manual bisection.
