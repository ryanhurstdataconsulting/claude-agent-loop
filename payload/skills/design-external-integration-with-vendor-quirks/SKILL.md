---
name: design-external-integration-with-vendor-quirks
description: Use when integrating with a new third-party API, SaaS platform, or partner system — before writing the client code. Triggers include "integrate with <vendor>", a new API key or OAuth app being provisioned, a sandbox-vs-production environment split, or symptoms like undocumented rate limits, inconsistent pagination styles, or an error-code catalog that does not match the published docs. Produces a vendor-quirk reference doc and a sandbox/production checklist that outlive the first integration and pay off on every later change.
---

# design-external-integration-with-vendor-quirks

## Overview
Front-loads the discovery work for a new external integration — auth flow, rate
limits, pagination style, error semantics, environment topology — into a durable
reference doc instead of relearning it by trial and error during implementation
and again during the next incident. Owns turning vendor documentation (which is
often incomplete or wrong) plus live probing into a single source of truth the
team can trust.

## When to use
- A new third-party API, SaaS platform, or partner system needs to be integrated,
  and no internal reference doc for it exists yet.
- An existing integration keeps surprising the team — undocumented rate limits,
  silent pagination truncation, error codes that do not match the published
  spec, or a sandbox that behaves differently from production.
- Onboarding a new engineer onto an integration and there is no single doc that
  captures "what we learned the hard way" about the vendor.
- Planning work that touches a vendor SDK or webhook feed and the auth model
  (API key vs. OAuth2 vs. mutual TLS) is not yet confirmed.

## Workflow
1. **Identify the environment topology first.** Does the vendor offer a sandbox
   or test mode distinct from production? Confirm: separate base URL, separate
   credentials, whether test-mode data is isolated or mixed with production
   records, and whether webhooks fire identically in both. Many vendors quietly
   diverge sandbox and production behavior (different rate limits, missing
   fields, or delayed webhook delivery in sandbox) — do not assume parity.
2. **Resolve the auth flow and document it precisely.** API key in header vs.
   query string, OAuth2 (which grant type — client credentials, authorization
   code, refresh-token rotation), or signed-request (HMAC) schemes are common.
   Record token lifetime, refresh mechanics, and what happens on expiry
   (401 vs. a vendor-specific error body). Treat password- or secret-hashing
   conventions on the wire (for example, an unsalted MD5 hash instead of a
   modern password hash) as a deliberate vendor choice to document, not a bug
   to silently "fix" client-side.
3. **Map rate limits and back-off behavior.** Per-key, per-IP, or per-endpoint?
   Fixed window or token bucket? Does the vendor return `Retry-After`, or does
   the limit have to be reverse-engineered from a 429 body or an
   undocumented header? Record the actual observed ceiling, not just the
   published one — published limits are frequently stale.
4. **Catalog pagination style.** Offset/limit, cursor-based, or a
   `next`-link/HATEOAS pattern? Confirm the page-size ceiling and whether it is
   silently capped below what is documented. Note whether sort order is stable
   across pages (a mutating sort key causes skipped or duplicated records).
5. **Build the error-code catalog empirically.** Do not trust the docs alone —
   trigger the common failure modes (bad auth, missing required field, resource
   not found, rate-limited, validation failure) and record the exact HTTP
   status, response body shape, and any vendor-specific error code. Note where
   the vendor returns `200 OK` with an error embedded in the body — a common
   and dangerous quirk that breaks naive status-code-only error handling.
6. **Write the reference doc.** One doc per vendor, covering: base URLs per
   environment, auth flow with a worked example, rate limits with observed
   ceilings, pagination style, the error-code catalog, and a short "gotchas"
   section for anything that contradicts the published docs.
7. **Write the sandbox-vs-production checklist.** What changes when cutting
   over: credentials, base URL, webhook target URL, and any feature-flag or
   vendor-side "go live" step (some vendors require a manual review before
   production traffic is allowed).

## Checklist / quality gate
- Auth flow is documented with a worked example, including token refresh and
  expiry behavior.
- Rate limits are recorded from live observation, not just the vendor's
  published number.
- Pagination style, page-size ceiling, and sort-stability behavior are
  documented.
- The error-code catalog includes at least the common failure modes, and notes
  any case where a non-2xx failure is disguised as a 200 response.
- The sandbox-vs-production checklist lists every value that changes on
  cutover and any vendor-side activation step.
- The doc is dated and marked for re-verification if the integration goes
  quiet for an extended period — vendor APIs drift.

## References
- API Integration Engineer role and competency references (auth protocols,
  vendor documentation practice, sandbox/production separation) — general
  industry job-description and integration-practice literature.
- Stripe-style API design conventions for rate-limit headers and idempotent
  request handling, widely adopted as a de facto standard among REST API
  vendors.

## Composition
Feeds `write-openapi-spec-and-contract-tests` once the vendor's contract is
understood well enough to write consumer-side contract tests against it. Hands
off to `implement-webhook-consumer-with-idempotency` when the integration
includes inbound webhooks. Pairs with `idempotency-and-retry-design` for the
retry/back-off policy implied by the rate-limit and error-catalog findings.
