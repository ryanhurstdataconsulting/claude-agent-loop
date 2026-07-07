---
name: add-caching-layer
description: Use when a latency or hot-path performance request calls for a caching layer — "this endpoint is slow under load," "cache this query," "add Redis in front of X," or a database showing high read load from repeated identical queries. Walks through the cache-aside-vs-write-through decision, a TTL and invalidation strategy, and a Redis (or equivalent) integration checklist, rather than reflexively wrapping a function in a cache decorator. Also triggers on cache-stampede symptoms, stale-data bug reports traced to a cache, or a request to add a CDN/edge cache in front of an API.
---

# add-caching-layer

## Overview
Adds a caching layer to a slow or high-read-load code path with a deliberate
strategy choice and invalidation plan, rather than a reflexive cache wrapper
that trades a latency problem for a stale-data problem. The one job it owns:
every cache added has an explicit answer to "how does this become stale, and
what happens then?"

## When to use
- A specific endpoint or query is reported slow under load, and profiling
  shows the same read repeated with unchanged inputs.
- A database is showing high read load from requests that could tolerate
  eventually-consistent data.
- A team is debugging stale-data symptoms traced back to an existing cache
  with an unclear invalidation rule.
- A request explicitly asks to "add Redis" or a similar in-memory store in
  front of a hot path, without yet specifying the strategy.

## Workflow
1. **Confirm this is a caching problem before reaching for a cache.** If
   profiling shows an N+1 query, a missing index, or an unnecessarily large
   payload, fix that first — a cache in front of an inefficient query hides
   the inefficiency instead of removing it, and the cache-miss path stays slow.
2. **Choose a strategy based on the read/write ratio and staleness tolerance,
   not by default:**
   - **Cache-aside (lazy load)** — the application checks the cache, and on
     a miss reads from the source of truth and populates the cache. Simplest
     option; the default choice for read-heavy, write-light data where a
     brief cache miss is acceptable. Handles cache failures gracefully
     because the source of truth is always the fallback.
   - **Write-through** — every write goes to the cache and the source of
     truth together, synchronously. Keeps the cache always warm and
     consistent, at the cost of extra write latency; use it when read-after-
     write consistency matters and write volume is manageable.
   - **Write-behind (write-back)** — writes land in the cache and are
     flushed to the source of truth asynchronously. Lowest write latency,
     highest risk of data loss on a cache crash before flush; reserve for
     workloads that can tolerate that risk (e.g., high-volume metrics/counters).
   - **Read-through** — the cache itself owns the miss-fill logic instead of
     the application. Useful when multiple services share one cache and
     should not each reimplement the fill logic.
3. **Pick an invalidation approach and write it down before shipping:**
   - **TTL expiration** — simplest, works well when brief staleness is
     acceptable. Choose the TTL based on how often the underlying data
     actually changes, not a round number picked without data.
   - **Explicit invalidation on write** — the write path deletes or updates
     the relevant cache key(s) directly. More precise than TTL alone, but
     every write path that touches the cached data must remember to do it —
     audit for write paths that bypass the invalidation (batch jobs, admin
     tools, direct database edits).
   - **Versioned/namespaced keys** — bump a version component in the cache
     key (e.g., a model's `updated_at` or a global version counter) so old
     entries become unreachable without an explicit delete. Useful when
     precise invalidation is hard to guarantee across every write path.
4. **Guard against cache stampede** on hot keys with high concurrency: use a
   short lock/single-flight pattern so only one request repopulates an
   expired key while others wait or serve stale data briefly, rather than
   every concurrent request missing simultaneously and hammering the source
   of truth at once.
5. **Design the key scheme deliberately.** Include every input that affects
   the cached value (tenant/user ID, locale, filter parameters, a schema
   version) in the key — a cache key that's too coarse serves the wrong data
   to the wrong caller; one that's too granular defeats the hit rate.
6. **Decide the failure mode up front.** If the cache is unavailable, does
   the request fall through to the source of truth (fail open — usually
   correct for a performance cache) or fail the request (fail closed —
   correct only when the cache is standing in for data too expensive or
   dangerous to compute on every request)? Make this explicit in code, not
   an accident of how the client library handles a connection error.
7. **Instrument it.** Emit a hit/miss ratio, at minimum. A cache added
   without visibility into its own effectiveness cannot be tuned or proven
   worth the added complexity.

## Checklist / quality gate
- [ ] Root cause is confirmed to be repeated identical reads, not an
      inefficient query or an oversized payload that should be fixed instead.
- [ ] Strategy (cache-aside / write-through / write-behind / read-through) is
      chosen deliberately and matches the read/write ratio and consistency
      need.
- [ ] Invalidation approach is written down, and every write path that
      touches the cached data honors it (including batch jobs and admin
      tools).
- [ ] Cache key includes every input that affects the cached value.
- [ ] Stampede protection exists on any key expected to see concurrent
      traffic at expiry.
- [ ] Failure mode (fail open vs. fail closed) on cache unavailability is an
      explicit decision, not accidental default behavior.
- [ ] Hit/miss ratio (or equivalent) is instrumented and visible.

## References
- [Backend Developer Roadmap — roadmap.sh](https://roadmap.sh/backend) (Databases and Caching)
- [Redis: Caching strategies documentation](https://redis.io/docs/latest/develop/use/patterns/)

## Composition
Often follows a `profile-and-fix-slow-request` diagnosis skill — profile first,
cache second. Shares its idempotency/staleness discipline with an
idempotency-and-retry-design skill for write-behind and dual-write scenarios.
Hands off to `add-structured-logging-and-tracing` to wire the hit/miss metric
into existing observability rather than a one-off log line.
