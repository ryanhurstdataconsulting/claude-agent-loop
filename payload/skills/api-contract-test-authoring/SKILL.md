---
name: api-contract-test-authoring
description: Use when a REST or GraphQL service needs automated proof that its actual behavior matches its published contract — schema-driven test generation from an OpenAPI/Swagger or GraphQL SDL document, negative and edge-case coverage (malformed payloads, auth failures, rate limits), and an auth-flow test scaffold (token issuance, refresh, expiry). Triggers include "add API/contract tests," a Swagger doc suspected of drifting from real endpoint behavior, a partner integration break traced to an undocumented field or status-code change, or a request to verify a service's responses against its own schema in CI.
---

# api-contract-test-authoring

## Overview
Generates and runs black-box tests that verify a REST or GraphQL API's
real behavior against its documented contract — turning an OpenAPI/Swagger
spec or GraphQL SDL into an executable test suite rather than trusting the
document to stay accurate on its own. Owns schema-driven positive-case
generation, negative and edge-case coverage, and auth-lifecycle testing;
hands the contract's authorship and the provider/consumer Pact workflow to
a spec-writing skill rather than duplicating it.

## When to use
- A service has an OpenAPI/Swagger spec or GraphQL SDL and needs a test
  suite that fails when the implementation drifts from it.
- A partner or downstream consumer integration broke on an undocumented
  field removal, type change, or status-code change — the gap needs to
  become a regression test, not just a hotfix.
- A new or changed endpoint needs negative-path coverage: malformed
  payloads, missing required fields, wrong content-types, expired or
  missing auth tokens, and rate-limit behavior.
- An auth flow (token issuance, refresh, expiry, revocation) has no
  automated coverage beyond the happy path.

## Workflow
1. **Confirm the spec is the source of truth before generating from it.** If
   no machine-readable spec exists yet, or the existing one is known to have
   drifted, that is an authoring gap — hand it to a spec-authoring skill
   first. Generating tests from a stale spec just automates the wrong
   answer.
2. **Generate positive-path tests from the schema.** For each operation,
   assert status code, response shape, and field types/constraints
   (`required`, `enum`, `format`) against real responses — not just against
   static example payloads bundled in the spec. Property-based /
   schema-fuzzing tools (for example, generating requests directly from an
   OpenAPI document) catch shape violations a hand-written happy-path test
   would miss.
3. **Add negative and edge-case coverage per operation:**
   - Missing or malformed required fields, wrong types, boundary values
     (empty string, zero, negative, max-length-plus-one).
   - Wrong or missing `Content-Type` / `Accept` headers.
   - Unauthorized (missing token), unauthenticated (invalid token), and
     forbidden (valid token, wrong scope/role) cases — assert the correct
     4xx code, not just "not 200."
   - Rate-limit behavior where the API documents one: assert the limit is
     enforced and the `429` (or equivalent) response carries the documented
     retry guidance.
4. **Scaffold the auth-lifecycle test set explicitly**, since it is the
   highest-blast-radius gap when missing: token issuance on valid
   credentials, rejection on invalid credentials, refresh-token exchange,
   behavior on an expired access token, and behavior after explicit
   revocation/logout.
5. **Add consumer-side contract assertions where a Pact (or equivalent
   consumer-driven contract) file already exists**, verifying the consumer's
   expectations against live provider responses. Provider-side Pact
   verification and contract authorship belong to the spec-writing skill
   this one hands off to — don't re-author the contract here, verify
   against it.
6. **Version-gate the suite.** Tag tests by API version/endpoint deprecation
   status so a sunset endpoint's failing tests are an expected signal, not
   noise to silence.
7. **Wire into CI to run on every change to the service or its spec**, so a
   provider-side drift fails the build rather than reaching a consumer in
   production.

## Checklist / quality gate
- Every documented operation has at least one positive-path assertion tied
  to the schema, not a hard-coded example value.
- Every operation with required fields or auth has negative-path coverage
  for the missing/malformed/unauthorized cases.
- Auth-lifecycle tests exist and cover issuance, refresh, expiry, and
  revocation — not just "login succeeds."
- Response validation runs against live/integration traffic, not only
  static fixtures baked into the spec.
- The suite runs in CI on every change to the service or its published
  contract, and a failure blocks merge.

## References
- [OpenAPI Specification](https://www.openapis.org/) — the schema format
  most REST contract tests generate from.
- [Pact documentation](https://docs.pact.io/) — consumer-driven contract
  testing pattern for provider/consumer verification.
- [roadmap.sh — QA Engineer](https://roadmap.sh/qa) — API and contract
  testing as a core QA/SDET competency alongside functional and
  integration testing.

## Composition
Downstream of a spec-authoring skill that establishes the OpenAPI/GraphQL
contract and owns provider-side Pact verification — this skill consumes
that contract rather than authoring it, and adds the negative-path,
edge-case, and auth-lifecycle depth a spec-first workflow typically leaves
thin. Sits below `e2e-test-suite-authoring` in the test pyramid: prefer a
contract test here over a full browser E2E test whenever the check is about
API shape and behavior rather than user-visible UI flow. Feeds
`flaky-test-triage` when a contract test destabilizes, and
`load-performance-test-authoring` when a contract-tested endpoint needs
capacity evidence before launch.
