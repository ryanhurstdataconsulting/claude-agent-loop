---
name: write-openapi-spec-and-contract-tests
description: Use when publishing a new public or partner-facing API, or changing an existing one, and the change needs a machine-readable contract plus automated proof that provider and consumer agree on it. Triggers include "write the OpenAPI spec for", a Swagger doc that has drifted from actual endpoint behavior, a partner integration break traced to an undocumented field change, or a request to add Pact/consumer-driven contract tests to a service boundary. Produces an OpenAPI-first spec plus a contract-test suite that runs in CI.
---

# write-openapi-spec-and-contract-tests

## Overview
Establishes an OpenAPI document as the single source of truth for an API's
shape, then backs it with contract tests so provider and consumer(s) cannot
silently drift apart. Owns the discipline of spec-first authoring plus the
breaking-vs-non-breaking classification that decides whether a change ships
quietly or needs a version bump.

## When to use
- A new public or partner-facing endpoint or service is being published and no
  machine-readable spec exists yet.
- An existing Swagger/OpenAPI doc has drifted from what the API actually
  returns — a common symptom is a consumer integration breaking on a field
  that "was never documented as removable."
- A service boundary (internal microservice-to-microservice, or
  system-to-partner) needs consumer-driven contract tests so a provider-side
  change fails CI before it fails a consumer in production.
- Planning a change to a field, status code, or response shape and needing to
  know whether it counts as breaking before deciding on a version strategy.

## Workflow
1. **Author the spec before the implementation, not after.** Write the
   OpenAPI (3.x) document first: paths, request/response schemas, status
   codes, and auth scheme. Treat it as the design surface — implementation
   conforms to the spec, not the reverse. If retrofitting a spec onto an
   existing API, generate a draft from the live traffic or existing code
   annotations, then correct it against actual observed behavior rather than
   trusting the generator's guess.
2. **Model schemas precisely, not loosely.** Use `required`, `nullable`,
   `enum`, and format constraints (`date-time`, `uuid`, `email`) rather than
   leaving fields as untyped strings — a loose schema defeats the point of a
   contract. Use `oneOf`/`allOf`/`discriminator` for polymorphic response
   shapes instead of documenting them only in prose.
3. **Classify every field/endpoint change as breaking or non-breaking before
   shipping it.** Non-breaking (safe without a version bump): adding an
   optional field, adding a new endpoint, adding a new enum value a client
   is expected to ignore gracefully, loosening a validation constraint.
   Breaking: removing or renaming a field, tightening a validation constraint,
   changing a field's type or semantics, changing a status code for an
   existing case, or adding a new required field. When in doubt, treat it as
   breaking — the cost of an unnecessary version bump is far lower than the
   cost of a silently broken consumer.
4. **Scaffold consumer-driven contract tests.** For each consumer, generate a
   contract (a Pact file or equivalent) capturing the specific interactions
   that consumer relies on. Run provider-side verification against every
   registered consumer contract in CI — a provider change that would break
   any consumer's contract fails the build before merge, not after deploy.
5. **Wire schema validation into the test suite.** Validate actual API
   responses against the OpenAPI schema in integration tests (not just
   example payloads) so the spec and the implementation cannot silently
   diverge over time.
6. **Publish the spec where consumers can reach it**, and version the spec
   file itself alongside the API version so historical contracts remain
   inspectable.
7. **Hand off breaking changes** to `design-api-versioning-and-deprecation-plan`
   rather than shipping them directly — a breaking change needs a rollout
   plan, not just a spec update.

## Checklist / quality gate
- The OpenAPI spec is the artifact reviewed in the pull request, not a
  by-product generated after the fact.
- Every field has a real type and constraint set — no bare untyped strings
  standing in for structured data.
- Every proposed change has an explicit breaking/non-breaking classification
  with the reasoning stated, not just an assumption.
- Contract tests exist per consumer and run in CI on every provider-side
  change.
- Response schema validation runs against real integration-test traffic, not
  only static examples.
- The spec is published somewhere consumers can discover it, and it is
  version-controlled.

## References
- [OpenAPI Specification](https://www.openapis.org/) — the spec format itself.
- Pact and consumer-driven contract testing — the standard pattern for
  provider/consumer contract verification in a microservices or partner-API
  setting.
- REST API design and versioning best-practice references (breaking-change
  taxonomy, schema constraint modeling) from current API-design guidance.

## Composition
Follows `design-external-integration-with-vendor-quirks` when the API being
specified is itself a client of a third party. Hands breaking changes to
`design-api-versioning-and-deprecation-plan`. Shares its schema-validation
discipline with `build-data-mapping-transform-layer` when the same contract
feeds a transform layer.
