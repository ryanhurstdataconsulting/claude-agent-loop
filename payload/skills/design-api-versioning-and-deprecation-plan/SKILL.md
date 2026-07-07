---
name: design-api-versioning-and-deprecation-plan
description: Use when a breaking change is needed on an API that already has consumers, or when planning how a public/partner API will version and sunset old behavior over time. Triggers include "we need to change this field but partners depend on it", a request to add a `v2` endpoint, a decision between header-based and URL-path versioning, or a need to draft a deprecation notice and sunset timeline for an endpoint being retired. Produces a versioning-strategy decision, a deprecation-notice and sunset-header workflow, and a consumer migration guide.
---

# design-api-versioning-and-deprecation-plan

## Overview
Turns a breaking API change into a managed rollout instead of a surprise: picks
a versioning strategy consistent with the API's existing convention, defines how
consumers are warned before something is removed, and produces the migration
guide that lets them move off the old behavior on their own schedule. Owns the
decision of *how* a breaking change ships, once
`write-openapi-spec-and-contract-tests` has established *that* it is breaking.

## When to use
- A breaking change (field removal, semantic change, status-code change) is
  needed on an API that already has active consumers.
- A new major version of an API is being planned and the team has not yet
  settled on a versioning scheme.
- An existing endpoint or field needs to be formally deprecated and eventually
  removed, and consumers need advance notice.
- A partner integration keeps breaking on undocumented changes, signaling that
  no versioning or deprecation discipline exists yet.

## Workflow
1. **Confirm the change is actually breaking** (hand off from
   `write-openapi-spec-and-contract-tests` if that classification has not
   already happened). Do not invoke a full versioning process for a
   non-breaking, purely additive change.
2. **Pick or confirm the versioning strategy** — consistency with the API's
   existing convention outweighs any strategy's theoretical merits:
   - **URL-path versioning** (`/v1/…`, `/v2/…`) — most explicit and cache-
     friendly; the default choice for a new API with no existing convention.
   - **Header-based versioning** (a custom `Accept` media type or a version
     header) — keeps URLs stable across versions; fits APIs where clients
     already negotiate representations.
   - **Query-parameter versioning** — simplest to add retroactively but
     easiest for a consumer to omit by accident; weakest of the three for
     enforcement.
   Whichever is chosen, require the version to be present rather than
   silently defaulting to "latest" — a silent default is how a consumer gets
   broken by a change it never opted into.
3. **Design the deprecation-notice mechanism before deprecating anything.**
   Standard building blocks: a `Deprecation` response header on the outgoing
   version, a `Sunset` header carrying the retirement date, and a `Link`
   header pointing at the migration guide. Log every request that still hits
   a deprecated version/field so the sunset decision is based on real usage
   data, not a guess.
4. **Set the sunset timeline based on observed consumer traffic, not a fixed
   default.** A version with heavy active traffic needs a longer runway and
   direct outreach to known consumers; a version with near-zero traffic can
   sunset faster. Communicate the date in absolute terms (a calendar date),
   never a vague "a future release."
5. **Write the consumer migration guide.** Field-by-field or endpoint-by-
   endpoint mapping from old to new, worked before/after request and response
   examples, and a note on any behavioral difference beyond the shape (a
   changed default, a changed error condition).
6. **Plan the removal step**, not just the deprecation. A deprecation that
   never actually gets removed accumulates indefinitely and defeats the
   purpose — schedule the removal, confirm traffic has dropped to the
   expected floor (internal test/monitoring traffic only), and only then
   retire the old version.
7. **Never silently break an existing version.** If a security or correctness
   fix must land on a deprecated version, ship it there deliberately and
   communicate it — do not let "it's deprecated anyway" become an excuse to
   skip the same rigor.

## Checklist / quality gate
- The chosen versioning strategy matches the API's existing convention, or
  the decision to diverge is documented with a reason.
- Every consumer is required to specify a version — no silent "latest"
  default.
- Deprecated versions/fields carry `Deprecation` and `Sunset` headers (or the
  equivalent for the transport in use), and usage is logged.
- The sunset date is a specific calendar date, communicated in advance, and
  based on observed traffic rather than guesswork.
- A consumer migration guide exists with worked before/after examples.
- A removal step is actually scheduled — deprecation is not treated as the
  finish line.

## References
- REST API versioning and deprecation best-practice guidance from current
  API-design references (URL-path vs. header-based versioning trade-offs,
  `Deprecation`/`Sunset` header conventions).
- RFC 8594 (`Sunset` HTTP header field) as the standards basis for
  machine-readable deprecation signaling.

## Composition
Consumes the breaking-change classification from
`write-openapi-spec-and-contract-tests`. Often follows
`design-external-integration-with-vendor-quirks` when the versioning decision
concerns an outward-facing API rather than an inbound vendor integration.
Hands the migration guide to documentation-authoring work once drafted.
