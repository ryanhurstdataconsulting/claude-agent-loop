---
name: scaffold-full-feature-slice
description: Use when a request reads as "add feature X" or "build out Y" spanning the whole stack — a new capability that needs a database migration, an API endpoint, a typed client, a UI component, and end-to-end coverage before it ships. Triggers include a product spec or ticket describing a new entity or workflow with no existing endpoint, a request to "wire up" a new screen to real data, or a task touching a migration file alongside a route handler and a frontend component in the same session. Also load it when a partially built slice compiles at one layer but breaks at the boundary above it — for example, an API returning a shape the client does not expect.
---

# scaffold-full-feature-slice

## Overview
Scaffolds a new feature end-to-end in a fixed layer order — schema, API, typed
client, UI, end-to-end test — so each layer compiles and is verified before the
next one begins. It owns the ordering discipline and the stub-then-fill pattern
that keeps a multi-layer change from breaking silently at a boundary.

## When to use
- A ticket or spec describes a new user-facing capability that does not map to
  a single existing endpoint or component.
- The task requires a new database table or column, a new route, and new UI in
  the same body of work.
- A previous attempt at the feature broke because the frontend assumed a
  response shape the backend never returned, or vice versa.
- The user says "add," "build," or "wire up" a feature, and the answer touches
  more than one layer of the stack.

## Workflow

**Step 0 — Freeze the boundary contract first.** Before writing schema, API, or
UI code, define the shape of the data at the API boundary: a shared type, a
JSON Schema, or an OpenAPI stub. This becomes the single source of truth every
later layer implements against. Do not let any layer start against a contract
that is still moving.

**Step 1 — Schema layer.** Add or alter the persistence model with a reversible
migration (up and down, or the platform's equivalent). Run it against a
scratch or development database, never production. Stub only the columns the
Step 0 contract needs — do not gold-plate the schema for hypothetical future
fields.

**Step 2 — API layer.** Implement the handler against the stub schema,
returning exactly the shape agreed on in Step 0, even if the underlying data
is hardcoded at first. Verify with a direct HTTP call that the response
matches the contract shape exactly, and confirm the existing test suite still
passes.

**Step 3 — Typed client.** Generate or hand-write a typed client for the new
endpoint so a contract mismatch surfaces as a compile error, not a runtime
one. If the platform has an OpenAPI-to-client generator, prefer it over a
hand-maintained type; hand-written types drift silently.

**Step 4 — UI layer.** Build the component or screen against the typed client,
never against a raw, untyped fetch call. Stub the loading, empty, and error
states before wiring live data, so those states are not an afterthought bolted
on at the end.

**Step 5 — End-to-end test.** Add one test that exercises the full path from a
UI action to a persisted, retrievable change. This is a gate, not decoration —
a feature slice is not done until it passes.

```
schema (migration) → API (returns Step 0 shape) → typed client (compiles) →
UI (loading/empty/error + happy path) → e2e test (full path, gates merge)
```

**Order-inversion gotcha.** Never let UI work start against a real,
non-stubbed API before the response shape is frozen — a mid-flight shape
change cascades into every layer built on top of it. If UI work must start in
parallel with backend work, freeze the Step 0 stub first and treat any later
change to it as a breaking change that forces a re-sync across every layer
that already consumed it.

**Partial-slice safety.** If a layer is incomplete when the branch needs to
merge, gate the feature behind a flag rather than shipping a half-wired
slice — a schema change with no consuming API, or an API with no UI, should
never be reachable by an end user before the full slice lands.

## Checklist / quality gate
- [ ] Boundary contract (types or OpenAPI) is defined and shared before any
      layer's implementation starts
- [ ] Migration is reversible and has been run and rolled back at least once
      in a non-production environment
- [ ] API layer returns the exact contract shape, and existing endpoint tests
      still pass
- [ ] Typed client compiles against the current API contract with no
      untyped escape hatches
- [ ] UI handles loading, empty, and error states, not just the happy path
- [ ] One end-to-end test walks the full slice and is wired into CI
- [ ] An incomplete slice is behind a flag, not silently reachable

## References
- [Full Stack Developer Roadmap](https://roadmap.sh/full-stack)
- [8 In-Demand Full Stack Developer Skills](https://roadmap.sh/full-stack/developer-skills)

## Composition
Hands off to `write-unit-tests-with-coverage-target` for per-layer unit
coverage and to a Playwright/Cypress end-to-end authoring skill for the Step 5
test. Pairs with an API-contract-design skill for the Step 0 boundary
definition and with a database-migration-with-rollback skill for the schema
layer. Feeds a CI/CD pipeline-setup skill once the slice is ready to ship
through automation.
