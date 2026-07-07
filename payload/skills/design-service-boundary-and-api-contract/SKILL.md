---
name: design-service-boundary-and-api-contract
description: Use when a new microservice or bounded context is being proposed, when an existing service is being split or merged, or when two systems need a boundary drawn between them — sync REST/RPC call, async event, or shared database (the wrong call to make). Triggers include "should this be its own service," "where should this logic live," "let's split X out of the monolith," a growing God-service, a request to define the contract between two teams' systems, or a review comment asking "why does service A reach into service B's tables?" Produces a bounded-context definition, a sync-vs-async decision, and a versioned API/event contract skeleton.
---

# design-service-boundary-and-api-contract

## Overview
Draws the line between two pieces of a system and defines how they talk across it.
This skill owns two coupled decisions that are usually made together and badly when
made separately: *where the boundary goes* (bounded-context and ownership) and *how
the two sides communicate across it* (sync request/response, async event, or shared
data — the anti-pattern). It hands back a boundary definition plus a versioned
contract skeleton, not a final architecture sign-off.

## When to use
- A new microservice, module, or bounded context is being proposed and it is not
  obvious what belongs on which side of the line.
- An existing service has grown multiple unrelated responsibilities ("God service")
  and needs to be split.
- Two teams' systems need to exchange data and nobody has written down the contract.
- A code review flags one service reaching directly into another's database tables
  or internal models — a boundary violation, not a communication-pattern choice.
- A request explicitly asks to define, review, or version an API or event contract
  between two systems.

## Workflow

**1. Find the bounded context, not the org chart.** Use domain-driven design's core
   test: group behavior by the business capability it serves and the language its
   users actually use, not by which team happens to own the code today. Two strong
   signals a boundary is in the right place:
   - Data that changes together stays together — if updating one field almost always
     requires updating a field that lives "across" a proposed boundary, the boundary
     is probably drawn wrong.
   - The two sides use different vocabulary for adjacent concepts (a "customer" in
     billing vs. a "user" in auth) — that vocabulary shift often *is* the boundary.
   A boundary that requires the two sides to share a database, a mutable in-process
   object, or a synchronous transaction is not really a boundary yet — it is one
   service in two files.

**2. Decide sync vs. async before designing the payload shape.** Use this decision
   tree:
   - **Needs an answer before the caller can proceed** (validate, authorize, fetch a
     value that gates the next step) → synchronous request/response (REST/RPC/gRPC).
   - **The caller doesn't need to wait, and other consumers might care about the same
     event** → asynchronous event (message queue, event bus, webhook).
   - **The two sides need the same data at different times but neither needs to react
     immediately** → async event with a materialized read model on the consumer side,
     not a shared table.
   - **A synchronous call chain crosses more than two or three service hops** — flag
     it; this is a common source of cascading-timeout failures and usually means an
     event-driven redesign or a boundary that's drawn too thin.
   Never let "it's simpler to just query their database directly" win — a shared
   database is the single most common way a "service boundary" becomes fake. It
   couples deploy schedules, schema changes, and failure domains that the boundary
   was supposed to separate.

**3. Draft the contract skeleton**, matched to the sync/async decision:
   - **Sync (REST):** an OpenAPI stub — resource paths, request/response schemas,
     status codes, and auth requirements. Version from day one (see step 4).
   - **Sync (RPC/gRPC):** a `.proto`-style message and service definition with
     explicit field numbers and a note on backward-compatible field-addition rules.
   - **Async (event):** an event schema (name, version, payload, a stable event ID
     for idempotent consumption) plus the delivery guarantee the producer commits to
     (at-least-once is the common default — consumers must be idempotent).

**4. Set the versioning and backward-compatibility rule up front**, not after the
   first breaking change is needed:
   - Additive changes (new optional field, new endpoint) do not require a version
     bump; breaking changes (removed/renamed field, changed semantics, tightened
     validation) do.
   - Pick one strategy and state it explicitly: URL path version (`/v2/…`), header
     version, or payload version field for events — mixing strategies across a
     system's contracts is a recurring source of client confusion.
   - Define the deprecation window for the prior version before it's needed, not
     when the first sunset notice has to go out under pressure.

**5. Name the failure mode across the boundary.** For a sync call: what does the
   caller do on timeout, 5xx, or partial failure — retry, circuit-break, degrade?
   For an async event: what happens on consumer-side processing failure — dead-letter
   queue, replay, alert? A boundary design without a stated failure behavior is
   incomplete; the failure path is where boundaries are actually tested in production.

**6. Flag it as a draft, not an approval.** This is a high-stakes, hard-to-reverse
   call — the skill scaffolds the checklist and the contract skeleton; a human
   technical owner signs off on the boundary before teams start building against it.

**Common gotchas:**
- Drawing the boundary around the current team structure instead of the domain —
  produces a boundary that has to be redrawn the next time teams reorg.
- Choosing sync because it's easier to reason about today, without naming what
  happens when the callee is slow or down.
- Skipping the versioning decision until the first breaking change is already
  urgent, which forces a rushed, undocumented choice under pressure.
- A "shared database" boundary presented as a service split — it is not one.

## Checklist / quality gate
- [ ] The boundary is stated in domain/business-capability terms, not team-ownership
      terms.
- [ ] Data that changes together lives together — no field pair straddling the
      boundary that must always update in lockstep.
- [ ] The sync-vs-async choice is explicit, with the reasoning from step 2 stated,
      not assumed.
- [ ] No shared database or shared mutable state crosses the boundary.
- [ ] A contract skeleton exists (OpenAPI stub, RPC definition, or event schema) with
      explicit types, not prose description alone.
- [ ] A versioning strategy is named and consistent with the rest of the system's
      contracts.
- [ ] The failure behavior across the boundary (timeout, retry, dead-letter) is
      stated, not left implicit.
- [ ] The output is flagged as a draft pending human architectural sign-off.

## References
- [Backend Developer Roadmap — Domain-Driven Design](https://roadmap.sh/backend)
- [staffeng.com — Staff Engineer Archetypes](https://staffeng.com/guides/staff-archetypes/)

## Composition
- Often produces the decision an `adr-authoring` record should capture — draft the
  boundary here, record the accepted rationale there.
- Hands off to `write-openapi-spec-and-contract-tests` (sync REST contracts) or
  `implement-webhook-consumer-with-idempotency` (async event contracts) for
  implementation-level detail once the boundary and contract shape are settled.
- Feeds `plan-zero-downtime-migration` when the boundary change involves splitting
  an existing service or its data store, not building a new one from scratch.
- Pairs with `run-architecture-review-checklist` when the boundary is one part of a
  larger pre-launch system review.
