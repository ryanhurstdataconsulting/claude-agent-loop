---
name: run-architecture-review-checklist
description: Use before a new system, service, or major feature launches, or when a design needs a structured pre-launch review — triggers include "design review," "is this ready to ship," "architecture review board," "pre-launch checklist," a request to assess on-call readiness, or a reviewer asking whether scalability/cost/security/observability have been considered. Produces a non-functional-requirements checklist walkthrough (scalability, reliability, cost, security, observability, on-call readiness) with a risk score per dimension and a named list of open gaps, not a go/no-go verdict.
---

# run-architecture-review-checklist

## Overview
Runs a structured review of a system or feature design against the non-functional
requirements that don't show up in a functional spec but decide whether the thing
survives production: scalability, reliability, cost, security, observability, and
on-call readiness. This skill owns the *checklist walkthrough and risk scoring* — it
surfaces gaps and a risk profile for a human reviewer to weigh, not a launch
approval.

## When to use
- A new system, service, or major feature is heading toward a launch or a design
  review meeting.
- Someone asks explicitly for an architecture review, a design review, or a
  pre-launch readiness check.
- A design doc is complete on the functional side but hasn't been checked against
  non-functional requirements (this is the most common gap this skill catches).
- A postmortem action item calls for "review the design before we build the next
  one like this."
- A reviewer's comment reads as "have we thought about X at scale / under attack /
  when it breaks?" — a sign the review hasn't happened yet.

## Workflow

**1. Confirm scope before scoring anything.** A review of a new greenfield service
   covers different ground than a review of one feature being added to an existing
   system. Establish: what's actually new here, and what's inherited from an
   already-reviewed platform? Don't re-litigate settled platform-level decisions
   inside a feature-level review.

**2. Walk each dimension and score it.** Use a simple three-level risk score per
   dimension — **Low / Medium / High** — with the reasoning stated, not just the
   label. A "Low" with no reasoning is as useless as no review at all.

   - **Scalability** — What's the expected load today, and at 10x? Where's the first
     bottleneck (a single database instance, a synchronous fan-out call, an
     unindexed query)? Is scaling horizontal or does it require a redesign?
   - **Reliability** — What's the blast radius if this component fails? Is there a
     single point of failure? What's the retry/backoff/circuit-breaker story for
     its dependencies? Does a downstream outage degrade gracefully or cascade?
   - **Cost** — Does the design have an unbounded cost driver (per-request external
     API calls, unthrottled storage growth, an always-on high-tier resource sized
     for peak instead of typical load)? Is there a cost ceiling or alert?
   - **Security** — Does it cross a trust boundary (new external input, new
     third-party integration, new PII touchpoint)? Is authn/authz enforced at the
     boundary, not just assumed from an upstream caller? Any new secret or credential
     to manage?
   - **Observability** — Can an on-call engineer tell *why* this failed from logs,
     metrics, and traces alone, without reading the source at 3 a.m.? Are there
     dashboards and alerts defined, or only "we'll add them later"?
   - **On-call readiness** — Is there a runbook for the top 2–3 likely failure modes?
     Who gets paged, and do they have the access/context to act? Is there a rollback
     path that doesn't require the original author?

**3. Weight severity by the design's actual risk profile**, not a flat checklist —
   a low-traffic internal tool doesn't need the same scalability rigor as a
   customer-facing payment path, but *no* design skips the security and
   observability dimensions entirely. Call out explicitly which dimensions were
   scoped down and why, so a reviewer can push back if the scoping is wrong.

**4. Produce a gap list, not a pass/fail verdict.** For every dimension scored
   Medium or High, name the specific gap and a concrete next step — "add a rate
   limiter in front of the third-party call" is useful; "improve reliability" is not.
   Group gaps as **blocking** (must close before launch) vs. **follow-up** (tracked,
   not blocking) only when the requester or an existing team policy defines what
   "blocking" means for this launch — otherwise present the gap list ungated and let
   a human make the launch call.

**5. Never issue the go/no-go yourself.** This skill's output is a risk profile and
   a gap list for a human reviewer or review board to weigh against business
   context (deadline pressure, actual blast radius, who's on call). State this
   explicitly in the output.

**Common gotchas:**
- Scoring every dimension "Low" because the design doc didn't mention a problem —
  absence of a stated risk is not evidence of low risk; flag it as unassessed
  instead of assuming it away.
- Treating observability as an afterthought item instead of a first-class dimension
  — it's usually the one most silently skipped, and the one most acutely missed at
  2 a.m. during an incident.
- Conflating "we have a design doc" with "we have a review" — the review is the
  structured walk against these specific dimensions, not a read-through.

## Checklist / quality gate
- [ ] Review scope is stated explicitly (greenfield system vs. one feature on an
      existing platform).
- [ ] All six dimensions (scalability, reliability, cost, security, observability,
      on-call readiness) are addressed — none silently skipped without a stated
      reason.
- [ ] Each dimension has a Low/Medium/High score with the reasoning written out, not
      just the label.
- [ ] Any dimension scoped down from full rigor states why, so a reviewer can
      challenge the scoping.
- [ ] Every Medium/High-scored dimension has a named, concrete gap and next step —
      not a vague "improve X."
- [ ] The output is presented as a risk profile and gap list for human review, with
      no agent-issued go/no-go.

## References
- [staffeng.com — Staff Engineer Archetypes (Architect archetype)](https://staffeng.com/guides/staff-archetypes/)
- [Azure Well-Architected Framework — Maintain an ADR](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)

## Composition
- Draws on `design-service-boundary-and-api-contract` output when the review
  covers a new service boundary, and on `plan-zero-downtime-migration` output when
  the review covers a migration in flight.
- Overlaps with a general security-review checklist for the security dimension —
  defer to a dedicated security-review skill for deep threat-modeling rather than
  duplicating it here; this skill's security dimension stays at the design-review
  altitude.
- Findings worth preserving long-term should be captured with `adr-authoring` if
  the review surfaces a decision, not just a gap to fix.
