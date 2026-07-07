---
name: sprint-plan-from-spec
description: Use when an approved spec, PRD, or roadmap item needs to be decomposed into a sprint plan and a ticket set — parsing scope into tickets, flagging estimates for human confirmation, sequencing dependencies, and scaffolding a burndown. Triggers include "break this spec into tickets," "what's the sprint plan for this," a freshly approved design doc with no ticket breakdown yet, a roadmap item moving from "planned" to "in progress," or a request to re-sequence a backlog around a newly discovered dependency.
---

# sprint-plan-from-spec

## Overview
Decomposes an approved spec into a concrete, sequenced sprint plan: a ticket set
with acceptance criteria, dependency ordering, t-shirt-size estimate flags for
human confirmation, and a scaffolded burndown. Owns the mechanical translation
from "here is what we agreed to build" to "here is the ordered, ticketed work" —
it does not own the estimation judgment itself.

## When to use
- A spec, PRD, or design doc has just been approved and needs to become tickets
  before a sprint or program can start executing against it.
- A roadmap item is moving from "planned" to "in progress" and the team needs a
  concrete backlog, not just a one-line roadmap entry.
- An existing ticket set needs re-sequencing because a new dependency or
  constraint was discovered mid-sprint.
- A stakeholder asks "what's actually in this sprint and in what order" and the
  answer currently lives only in someone's head.

## Workflow

1. **Confirm the spec is actually approved and stable** before decomposing it.
   Decomposing a still-changing draft produces tickets that will be re-cut within
   days — a wasted pass. If the spec has open questions or unresolved sections,
   flag those explicitly and either exclude that scope from this pass or mark the
   resulting tickets `blocked: spec-gap`.
2. **Parse the spec into discrete units of work.** Good decomposition units are
   independently shippable or independently testable — "implement the auth
   middleware" is a unit; "backend work" is not. Prefer units that map to a
   single acceptance criterion or a single user-facing behavior over units that
   map to a technical layer, since layer-only tickets ("all the database work")
   hide integration risk until the end.
3. **Draft each ticket with a fixed shape**: title, description, acceptance
   criteria (testable, not vague — "returns 404 for an unknown ID" not "handles
   errors well"), and a t-shirt-size estimate (S/M/L/XL) or a story-point value
   if the team uses points.
4. **Flag every estimate as a draft needing human confirmation.** The agent can
   propose a size based on scope-word signals (number of components touched,
   presence of a migration, cross-team dependency, "TBD" language in the spec
   suggesting hidden scope) — but estimation is a team judgment call, not a
   mechanical output. Never present an estimate with unearned confidence; label
   the whole size column `(draft — confirm at planning)`.
5. **Sequence by dependency, not by convenience.** Build the ticket-level
   dependency order from the spec's own described sequence (e.g., "the API
   endpoint must exist before the client can integrate against it") and from any
   shared-resource constraints (two tickets touching the same migration file
   cannot run fully in parallel without a merge plan). Where the sequence is
   genuinely flexible, say so rather than imposing an arbitrary order.
6. **Surface cross-team or cross-workstream dependencies separately** from
   in-team sequencing — these carry higher schedule risk and belong on the
   program's dependency view, not buried in a single team's backlog order. Hand
   off to `map-dependencies` when a spec touches more than one team.
7. **Scaffold the burndown** from the estimate column once confirmed: total
   points/sizes, a target sprint length, and a naive linear burndown line as a
   starting reference — explicitly label it as a planning aid, not a
   forecast, since it has no velocity history behind it yet on a new
   initiative.
8. **Do not silently invent scope.** If the spec is ambiguous about what a
   feature should do in an edge case, ticket the ambiguity itself as a
   spike or a "needs decision" item rather than picking a behavior and
   shipping a ticket that encodes an assumption no one signed off on.

## Checklist / quality gate
- [ ] Every ticket traces back to a specific section or requirement in the
      source spec — no invented scope.
- [ ] Every ticket has testable acceptance criteria, not a vague description.
- [ ] Every estimate is explicitly labeled as a draft pending team confirmation.
- [ ] Dependency order is derived from the spec's described sequence and shared-
      resource constraints, with genuinely flexible ordering called out as such.
- [ ] Cross-team dependencies are flagged separately and handed to
      `map-dependencies` rather than folded into a single team's sequence.
- [ ] Spec ambiguities become their own "needs decision" tickets instead of
      being silently resolved by assumption.
- [ ] The burndown scaffold is labeled a planning aid, not a forecast, when no
      velocity history exists yet.

## References
- General agile/Scrum ticket-decomposition practice — no single canonical
  specification; the workflow above reflects standard sprint-planning practice
  as applied across engineering-management and technical-program-management
  guidance.

## Composition
Consumes the output of a PRD/spec-authoring skill as its primary input and hands
sequenced, estimated tickets downstream to sprint execution and tracking.
Hands cross-team dependencies to `map-dependencies` rather than encoding them as
in-team ticket order. Pairs with `run-raci-assignment` at the same kickoff moment
— once tickets exist, each needs an Accountable owner. Feeds `raid-log-maintainer`
when decomposition surfaces a new risk or open dependency, and feeds
`status-report` once the plan is underway and needs a recurring narrative.
