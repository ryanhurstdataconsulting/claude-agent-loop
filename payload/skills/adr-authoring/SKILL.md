---
name: adr-authoring
description: Use when a significant, hard-to-reverse technical or architectural choice is being made — a new framework or dependency, a build-vs-buy call, a platform migration, a data-store swap, a service split, or a schema change with no easy rollback. Triggers include phrases like "we need to decide between X and Y," "document why we chose," "record this decision," a PR description that reads like a rationale essay, or a reviewer asking "why not just use Z instead?" Produces a numbered Architecture Decision Record (ADR) — Title, Status, Context, Decision, Consequences, Alternatives Considered — filed into the repository's decision log and linked to any record it supersedes.
---

# adr-authoring

## Overview
Turns a decision brief or discussion thread into a single, well-formed Architecture
Decision Record: a short, durable document that captures what was decided, why, and
what it costs — so the next person who wonders "why is it built this way?" finds an
answer instead of re-litigating the choice. This skill owns the ADR artifact end to
end, from the "is this even ADR-worthy" test through drafting, numbering, and linking
superseding records.

## When to use
- A new dependency, framework, or platform is being adopted and reversing the choice
  later would be expensive (rewrite cost, data migration, vendor lock-in).
- A build-vs-buy call is being made for a capability (in-house service vs. a paid
  vendor or managed offering).
- A service boundary is being drawn, merged, or split, or a sync-vs-async
  communication pattern is being locked in between two systems.
- A data store, schema shape, or storage engine is chosen or replaced.
- A reviewer, teammate, or the requester explicitly asks to "record," "document," or
  "write up" a decision, or asks "why did we do it this way?" about existing code.
- A prior ADR needs revisiting — the situation changed and the old decision should be
  superseded rather than silently ignored.

## Workflow

**1. Apply the "architecturally significant" test before drafting anything.**
Not every choice needs an ADR — that turns the log into noise nobody reads. Draft one
only if at least one of these is true:
- Reversing it later requires a migration, rewrite, or contract renegotiation, not
  just a config flag flip.
- It affects more than one team, service, or long-lived system boundary.
- It trades off a non-functional requirement (cost, latency, security posture,
  compliance, vendor lock-in) against another.
- Someone already asked "why did we do it this way?" — a sign the rationale isn't
  self-evident from the code.

If none apply, say so and skip the ADR — recommend a code comment or a lighter-weight
note instead.

**2. Gather the decision context before writing.** Pull in, in order of preference:
   - An existing discussion thread, design doc, or spec the decision emerged from.
   - The options that were actually considered (not a straw man) and why each
     alternative was set aside.
   - The non-functional constraints that shaped the choice — budget, team size,
     existing skill set, compliance requirements, deadline pressure.
   If the requester hasn't supplied alternatives considered, ask for at least one —
   an ADR with a single option and no comparison reads as a decision made after the
   fact to justify itself, not a rationale.

**3. Number and file it.** ADRs are numbered sequentially and never renumbered or
   deleted once accepted — even a reversed decision stays in the log as
   `Superseded`, with a link forward to the record that replaced it. Locate the
   existing decision log directory (commonly `docs/adr/` or `docs/decisions/`); if
   none exists, propose creating one rather than dropping a single ADR into an
   unrelated location.

**4. Draft in the standard template** (Nygard form — the most widely adopted ADR
   shape):

```markdown
# ADR-NNNN: <short, decision-stated-as-a-title>

## Status
Proposed | Accepted | Rejected | Deprecated | Superseded by ADR-MMMM

## Context
What forces are at play — technical, business, team, timeline? State the problem
neutrally; do not pre-load it with the answer.

## Decision
The choice, stated as an active sentence: "We will use X."

## Consequences
What becomes easier, what becomes harder, and what new risks or follow-up work
this creates. Include the costs honestly — an ADR that lists only upside reads as
marketing, not a decision record.

## Alternatives Considered
- **Option A** — why it was set aside
- **Option B** — why it was set aside
```

**5. Set Status honestly.** Draft as `Proposed` until a human owner accepts it — the
   agent drafts, it does not self-approve a significant technical decision. Only flip
   to `Accepted` when the requester confirms it, or leave that step to them explicitly.

**6. Link supersession both ways.** When a new ADR replaces an old one, set the old
   record's status to `Superseded by ADR-MMMM` and the new record's front matter (or a
   note in Context) to `Supersedes ADR-NNNN`. Never delete or silently edit an accepted
   ADR to reflect a later change — write a new one.

**Common gotchas:**
- Writing the ADR after the code is already merged, with the alternatives section
  reverse-engineered to make the shipped choice look inevitable. Ask what was really
  considered, even if that means listing options nobody liked.
- Treating "Consequences" as a marketing section. A consequence like "adds an
  operational dependency on a third-party SLA" belongs there just as much as the win.
- Skipping the significance test and generating an ADR for every minor library bump —
  this erodes the log's signal-to-noise fast.

## Checklist / quality gate
- [ ] The decision passes the "architecturally significant" test (see step 1) — or
      the response explains why an ADR is not warranted.
- [ ] Title states the decision, not just the topic ("Use PostgreSQL for the events
      store," not "Database Choice").
- [ ] Context is neutral — it explains the forces at play, not just the conclusion.
- [ ] Alternatives Considered lists at least one real option with a reason it was
      set aside; a single-option ADR is flagged back to the requester.
- [ ] Consequences names at least one real cost or risk, not only benefits.
- [ ] Status is `Proposed` unless a human has explicitly confirmed acceptance.
- [ ] The ADR is numbered sequentially and filed in the repository's existing
      decision-log location (or a newly proposed one, called out explicitly).
- [ ] If this record replaces a prior one, both records' Status fields cross-link.

## References
- [Architectural Decision Records — adr.github.io](https://adr.github.io/)
- [Martin Fowler — Architecture Decision Record](https://martinfowler.com/bliki/ArchitectureDecisionRecord.html)
- [Cognitect — Documenting Architecture Decisions (Michael Nygard, 2011)](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [AWS Prescriptive Guidance — ADR process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html)

## Composition
- Feeds from `write-a-prd` or a design-review thread when the decision originates
  in a product or architecture spec.
- Pairs with `design-service-boundary-and-api-contract` (a boundary decision is a
  common ADR trigger) and `plan-zero-downtime-migration` (a migration plan usually
  cites an ADR as its rationale).
- Hands off to `run-architecture-review-checklist` when the decision is part of a
  larger pre-launch design review, not a standalone call.
- A `build-vs-buy-memo` is often the input a build-vs-buy ADR is drafted from.
