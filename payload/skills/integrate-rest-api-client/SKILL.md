---
name: integrate-rest-api-client
description: Use when wiring a frontend to a new or changed backend REST endpoint. Generates a typed fetch/axios wrapper, loading/error/empty-state handling, retry-with-backoff, and cache configuration for a data-fetching library (React Query/SWR or equivalent). Triggers include "call this endpoint from the UI", a new API route with no client-side consumer yet, a component doing raw `fetch` calls inline, or a changed response shape that needs the client updated to match.
---

# integrate-rest-api-client

## Overview
Wires a frontend component or module to a REST endpoint with a typed client wrapper,
full loading/error/empty-state handling, and sane retry and caching behavior — so no
component ends up with a bare, untyped `fetch` call and no failure-state handling. Owns
the client-side integration layer, not the backend endpoint itself.

## When to use
- A new backend endpoint needs a first frontend consumer.
- A component currently calls `fetch`/`axios` directly inline with no error handling,
  no loading state, and no typed response.
- A backend response shape changed and the client needs to be updated to match, ideally
  against a contract (OpenAPI spec) rather than by inspecting a sample payload.
- Introducing a data-fetching library (React Query, SWR, RTK Query) to a codebase that
  currently manages fetch state by hand with `useState`/`useEffect`.

## Workflow
1. **Get the contract before writing the client.** Prefer an OpenAPI/Swagger spec or a
   documented contract over inspecting one sample response — a hand-typed guess from a
   single payload misses optional fields, error shapes, and pagination. If no contract
   exists, request one or generate types from a live response with explicit optional
   markers on anything not confirmed present in every case.
2. **Generate a typed wrapper, not a raw call site.** One function per endpoint (or a
   generated client from the OpenAPI spec) that takes typed parameters and returns a
   typed result — never a component that calls `fetch(url)` inline with an untyped
   `.json()`. See `convert-js-to-typescript` if the codebase is still JS.
3. **Handle every request state explicitly**, not just the happy path: `loading`,
   `error` (with the actual error surfaced, not swallowed), `empty` (a successful
   response with zero results, distinct from an error), and `success`. A component
   that only renders the success state is not done.
4. **Add retry and backoff for transient failures, but scope it correctly:**
   - Retry idempotent reads (GET) automatically on network errors and 5xx with
     exponential backoff and a capped attempt count (2–3 retries is typical).
   - Never blindly retry non-idempotent writes (POST/PATCH/DELETE) without an
     idempotency key or explicit user confirmation — a naive retry on a write can
     double-submit.
   - Respect a `Retry-After` header when the API returns one (commonly on 429).
5. **Configure caching deliberately, not by accepting library defaults blindly.**
   Choose a `staleTime`/`cacheTime` (or equivalent) appropriate to how often the data
   actually changes — a rarely-changing reference list and a live dashboard metric
   should not share the same cache window. Invalidate the relevant cache key on any
   mutation that changes the same resource, so the UI doesn't show stale data after a
   write.
6. **Handle auth and token refresh at the client layer, once**, not per call site: a
   401 should trigger a single shared refresh-and-retry path, not a copy-pasted check
   in every component.

## Checklist / quality gate
- [ ] The client is typed end-to-end (request params and response shape), generated
      from or checked against a real contract, not guessed from one sample payload.
- [ ] Every consuming component handles loading, error, empty, and success states —
      none silently assume the happy path.
- [ ] Retries are scoped to idempotent requests only, with backoff and a capped
      attempt count; writes are never retried without an idempotency safeguard.
- [ ] Cache invalidation is wired for every mutation that affects a cached read.
- [ ] Auth/token-refresh logic lives in one shared place, not duplicated per call site.
- [ ] No component contains a raw, untyped `fetch`/`axios` call with no error handling.

## References
- [Frontend Developer Roadmap](https://roadmap.sh/frontend) — RESTful APIs

## Composition
Consumes the typed response shapes produced by `convert-js-to-typescript`. Pairs with
`scaffold-react-component-with-tests` when the new client backs a new container
component, and with a backend endpoint-scaffolding skill and an API-contract-design
skill on the producing side of the same contract this client consumes.
