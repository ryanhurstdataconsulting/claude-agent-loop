---
name: scaffold-rest-endpoint-with-tests
description: Use when a new CRUD or resource endpoint is requested on a backend service — "add a POST /orders endpoint," "expose a new resource," "wire up create/read/update/delete for X." Generates the route, controller, and model in one pass alongside request validation, an integration test, and an OpenAPI doc entry, so the endpoint ships tested and documented rather than as bare route-handler code. Also triggers on "the API needs a new resource," a missing OpenAPI entry for an existing route, or a request-validation gap flagged in review.
---

# scaffold-rest-endpoint-with-tests

## Overview
Scaffolds a complete REST endpoint — route, controller/handler, model, request
validation, an integration test, and an OpenAPI spec entry — as a single
coherent unit of work instead of a bare handler function. The one job it owns:
no endpoint ships without a validated contract and a test that proves it.

## When to use
- A new CRUD or resource endpoint is requested ("add a POST /orders endpoint").
- An existing route lacks request/response validation or an OpenAPI entry.
- A resource needs a full set of operations (list, get, create, update, delete)
  scaffolded consistently with the rest of the service.
- A code review flags a route with no integration test or no documented schema.

## Workflow
1. **Confirm the contract before writing code.** Nail down the resource name,
   HTTP verbs, request/response shapes, and status codes. If an OpenAPI spec
   already exists for the service, treat it as the source of truth — write the
   spec fragment first, generate types/models from it, then implement the
   handler. If no spec exists yet, draft one as part of this pass.
2. **Scaffold in dependency order**, each layer compiling/passing lint before
   moving to the next:
   - **Model** — the persistence or domain object, with field types matching
     the spec exactly (including nullability and format constraints).
   - **Request validation** — a schema-based validator (e.g., a Pydantic
     model, a Joi/Zod schema, a JSON Schema in front of the handler) that
     rejects malformed input *before* it reaches business logic. Validate at
     the boundary, not deep inside a service method.
   - **Controller/handler** — thin. It parses the validated request, calls
     the domain/service layer, and maps the result to an HTTP response and
     status code. Business logic does not belong here.
   - **Route registration** — wire the handler into the router with the
     correct verb, path, and any middleware (auth, rate limiting) the
     resource requires.
   - **OpenAPI doc entry** — request/response schemas, all documented status
     codes (200/201/400/401/403/404/409/422/500 as applicable), and example
     payloads.
3. **Pick status codes deliberately, not by habit.**
   - `201 Created` (with a `Location` header) for successful creation, not `200`.
   - `204 No Content` for a successful delete or an update with no body to return.
   - `400` for malformed input the validator rejected; `422` for well-formed
     input that fails a business rule.
   - `404` for a missing resource, `409` for a conflicting state (duplicate
     unique key, version mismatch) — do not collapse the two into one code.
4. **Write the integration test alongside the handler, not after.** Cover:
   - The happy path for each verb.
   - Validation failure (malformed body → 400/422, with the error shape
     asserted, not just the status code).
   - Not-found and conflict paths.
   - Authorization: an unauthenticated or under-privileged caller is rejected
     before any side effect occurs.
   - Idempotency of `PUT`/`DELETE` where the framework's semantics promise it.
5. **Version deliberately.** If the service already versions its API
   (`/v1/...`, an `Accept` header scheme), the new endpoint follows the
   existing convention — do not introduce a second versioning scheme in the
   same service.
6. **Keep the controller free of persistence details.** Route the actual
   database or cache calls through the existing data-access layer; a
   handler that opens its own connection is a sign the scaffold skipped the
   architecture the rest of the service already uses.

## Checklist / quality gate
- [ ] OpenAPI entry exists and matches the implementation exactly (verbs,
      paths, request/response schemas, status codes).
- [ ] Request validation rejects malformed input before business logic runs.
- [ ] Integration test covers happy path, validation failure, not-found,
      conflict, and unauthorized access.
- [ ] Status codes follow the deliberate mapping above, not a single
      catch-all `200`/`500`.
- [ ] The handler is thin: no direct database/cache calls, no business logic
      inlined into the route function.
- [ ] New route follows the service's existing versioning and auth-middleware
      conventions.
- [ ] Test suite passes locally and the endpoint is reachable behind the same
      auth/rate-limit middleware as its siblings.

## References
- [Backend Developer Roadmap — roadmap.sh](https://roadmap.sh/backend)
- [Backend Developer Skills — roadmap.sh](https://roadmap.sh/backend/developer-skills)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)

## Composition
Feeds from a written API contract (pair with an OpenAPI/contract-design skill
when the spec doesn't exist yet). Hands off to `implement-authn-authz` when the
new endpoint needs a login flow or role check beyond an existing middleware
stack, and to `write-database-migration-with-rollback` when the model requires
a schema change. A frontend-side "integrate REST API client" skill is the
natural consumer of the OpenAPI entry this skill produces.
