---
name: openapi-reference-generator
description: Use when an OpenAPI/Swagger spec has changed and the published API reference docs need regenerating, or when a REST API has no reference documentation yet and one needs to be generated from its schema. Triggers include a spec diff in a pull request, a new or changed endpoint/parameter/response schema, an undocumented-parameter complaint, missing response-code coverage, or a request to "regenerate the API docs" / "add docs for the new endpoint." Diffs the spec against the currently published reference, regenerates the affected endpoint pages, and flags anything undocumented or under-specified rather than silently passing it through.
---

# openapi-reference-generator

## Overview
Keeps API reference documentation mechanically in sync with the machine-readable
contract it describes. It owns the diff-detect-regenerate loop: given an
OpenAPI/Swagger spec (new or changed), it produces accurate, complete reference
pages and — just as important — surfaces the gaps the spec itself doesn't cover,
so reference docs stop drifting from the API they document.

## When to use
- An OpenAPI/Swagger spec changes (new endpoint, changed parameter, new response
  schema, deprecation) and the published reference needs to catch up.
- An API has no reference documentation yet and one needs to be generated wholesale
  from its spec.
- A support ticket, code-review comment, or integration bug traces back to a
  parameter or response code that exists in the API but not in the docs.
- A periodic audit needs to confirm the published reference still matches the
  live spec (pairs with `content-staleness-audit` for the recurring version).
- A release introduces breaking changes and the reference needs explicit
  before/after or deprecation callouts, not a silent edit.

## Workflow

**1. Get the spec, not a description of the spec.** Reference generation from a
machine-readable OpenAPI/Swagger document (JSON or YAML) is mechanical and
reliable; reference generation from a prose description of an API is guesswork
and should be flagged as lower-confidence. If only a prose description is
available, generate a best-effort draft but mark it clearly as unverified against
a spec.

**2. Diff against the currently published reference before regenerating
anything.** A full regeneration on every spec change destroys manually-added
context (usage notes, gotchas, deprecation warnings) that lived alongside the
auto-generated fields. Instead:
- Diff the new spec against the previous one (or against what the published docs
  currently describe) to find what actually changed: added/removed endpoints,
  added/removed/renamed parameters, changed types or requiredness, new response
  codes, new error shapes.
- Regenerate only the affected endpoint pages; leave untouched pages alone.
- Preserve hand-written prose (descriptions, examples, gotcha notes) attached to
  fields that didn't change; regenerate only the fields that did.

**3. Structure each endpoint page consistently.** A reference page's value is in
being scannable, not read linearly — use the same structure for every endpoint:
- Method + path, a one-line summary.
- Auth requirements.
- Path/query/header parameters — name, type, required/optional, default,
  constraints, one-line description.
- Request body schema, with a realistic example payload.
- Response schema per status code, with a realistic example for at least the
  success case and the most common error case.
- Rate limits, pagination behavior, and idempotency notes, if applicable.

**4. Flag what the spec doesn't cover — do not silently pass gaps through.**
An OpenAPI spec often under-specifies real behavior. Explicitly flag, rather than
guess past:
- Parameters present in the spec with no description, or a description that is
  just the field name restated.
- Response codes the API can plausibly return (4xx/5xx families) that aren't
  declared in the spec at all — cross-check against error-handling code or
  existing support tickets if available.
- Fields marked optional in the spec but that examples or tests treat as
  effectively required (a common sign the spec is stale, not the docs).
- Ambiguous or conflicting types (a field typed as `string` that is actually
  always a numeric ID, an `array` with no `items` schema).

**5. Call out breaking changes prominently, not just diff them in.** A parameter
that became required, a field that was removed, a response shape that changed —
these need an explicit, visually distinct callout (a "Breaking change in vN"
admonition) in addition to the regenerated page content. Silently updating the
page without flagging the break is how integrators get surprised in production.

**6. Verify generated examples, don't transcribe from the spec's `example` field
blindly.** Spec-authored examples are often stale or invalid. Where a live or
sandbox environment is available, execute the example request and use the real
response; where it isn't, at minimum validate the example against the schema
(correct types, required fields present) before publishing it.

**Common gotchas:**
- Treating the spec as ground truth for behavior when it's actually ground truth
  for the *contract* — real behavior (rate limits, undocumented headers, error
  edge cases) often lives outside the spec and needs a supplementary source.
- Full-file regeneration that clobbers hand-written usage notes — always diff
  and patch, not overwrite.
- Silently documenting a deprecated field as if it were current — check the
  spec's `deprecated: true` flag and surface it as a callout, not a footnote.

## Checklist / quality gate
- [ ] Regeneration was diff-based (changed endpoints only), not a full overwrite
      that discarded hand-written context.
- [ ] Every parameter and response code declared in the spec appears in the
      generated page.
- [ ] Undocumented parameters, missing response-code coverage, and
      spec/behavior mismatches are explicitly flagged, not silently skipped.
- [ ] Breaking changes carry an explicit, visually distinct callout.
- [ ] At least one example per endpoint was executed or schema-validated, not
      copied from the spec unverified.
- [ ] Deprecated fields/endpoints are marked as such, not documented as current.
- [ ] Page structure is consistent across endpoints (same section order, same
      heading levels).
- [ ] A grammar and terminology pass ran before publishing.

## References
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Swagger — API Documentation Best Practices](https://swagger.io/resources/articles/best-practices-in-api-documentation/)
- [Diátaxis — Reference](https://diataxis.fr/reference/) — the quadrant this
  output belongs to
- [Stoplight — API Reference Documentation Guide](https://stoplight.io/api-documentation-guide)

## Composition
- Produces the Reference-quadrant output that `docs-diataxis-authoring` classifies
  and structures the surrounding documentation set around.
- Feeds `quickstart-tutorial-generator`, which pulls endpoint signatures from the
  same spec to scaffold a runnable getting-started example.
- Hands off to `content-staleness-audit` for the recurring "has the published
  reference drifted from the live spec" check, distinct from this skill's
  event-triggered regeneration.
- Hands off to `prose-style-lint` for the final voice/terminology pass before
  publishing.
