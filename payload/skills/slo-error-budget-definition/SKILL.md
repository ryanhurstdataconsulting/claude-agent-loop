---
name: slo-error-budget-definition
description: Use when a service needs Service Level Indicators (SLIs) and a Service Level Objective (SLO) defined or reviewed — a launch review is missing a reliability target, an on-call rotation is getting paged on noise instead of real symptoms, or a rolling error budget needs to be tied to a release-freeze policy. Triggers include "define our SLOs," "what should our availability target be," "we get paged too much," "set up burn-rate alerts," or a service shipping to production with no measurable reliability target at all. Produces candidate SLIs tied to user-facing critical paths, a justified SLO target, the resulting error budget, multi-window burn-rate alert thresholds, and a written error-budget policy.
---

# slo-error-budget-definition

## Overview
Derives Service Level Indicators from a service's actual user-facing critical paths,
sets a justified Service Level Objective, computes the resulting error budget, designs
burn-rate alerts that page on real danger instead of noise, and drafts the policy tying
budget exhaustion to concrete consequences. The math from SLI to error budget to
burn-rate threshold is fully mechanical once the SLI is chosen; SLI and target selection
are judgment calls this skill surfaces for human sign-off rather than finalizing alone.

## When to use
- A service is shipping, or already in production, with no measurable reliability
  target at all.
- A launch or architecture review needs an SLO and none exists.
- An on-call rotation reports pager fatigue — too many alerts that never became real
  incidents, or a real incident that no alert caught.
- A team wants to justify a reliability investment, a release-freeze policy, or a
  build-vs-buy tradeoff against a concrete budget number instead of a vague sense of
  "we should be more reliable."
- An existing SLO or alert threshold hasn't been revisited since the service's traffic
  or architecture changed materially.

## Workflow

**1. Map user journeys to candidate SLI types.** Identify the critical user journeys the
service supports (load a page, submit a payment, return a search result). For each,
pick an SLI type: availability (successful responses over total valid requests), latency
(fraction of requests faster than a threshold), quality/correctness (fraction of
responses without a data-integrity defect), freshness (data age), or durability (data
not lost). Prefer request-driven SLIs sourced from real traffic over synthetic
black-box probes — a probe misses what actual users experience.

**2. Write the SLI as a precise ratio, not a description.** Good events over valid
events, with the exclusions stated:
```
SLI = (requests with latency < 300ms AND status < 500) / (all requests excluding client-side 4xx)
```
Exclude events outside the service's control (client errors, canceled requests) from
the denominator — otherwise the SLO punishes the service for a caller's bug.

**3. Set the target, and justify it — never round to a number out of habit.** Anchor on:
what users have already tolerated (historical performance), what the service's tier
demands (a payment path warrants a tighter target than an internal admin tool), and the
cost curve (each additional nine costs disproportionately more than the last — moving
from a 99.9% target to a 99.99% target typically demands an order of magnitude more
reliability engineering for a fraction of the perceived benefit). If an external SLA
exists for the same journey, the internal SLO must be strictly tighter than it, so the
team gets a warning before a contractual breach, not simultaneous with one. Flag the
choice for a human sanity check before it's treated as final.

**4. Compute the error budget and its window.** `error_budget = 1 − SLO_target`, over a
rolling window — 28 days is the common default; align it to the release cadence if the
org runs on a different cycle. A 99.9% target over a 28-day window allows roughly forty
minutes of full-downtime-equivalent budget.

**5. Design multi-window, multi-burn-rate alerts — never page on a raw SLO breach.**
Burn rate is `(1 − SLI_observed) / (1 − SLO_target)`; a burn rate of 1 exhausts the
entire budget exactly at the window's end. Pair a short window with a long window so a
fast, severe burn pages immediately while a slow, sustained burn still gets caught
without flooding the pager:

| Condition | Burn rate | Long window | Short window | Response |
|---|---|---|---|---|
| 2% of budget in 1 hour | 14.4x | 1 hour | 5 minutes | page immediately |
| 5% of budget in 6 hours | 6x | 6 hours | 30 minutes | page |
| 10% of budget in 3 days | 1x | 3 days | 6 hours | ticket, business hours |

These canonical multipliers assume a 30-day budget window; scale them by
`30 / window_days` if the org's rolling window (for example, 28 days) differs, so the
long-window percentage still maps to the stated burn rate.

The short window lets a fast-recovering blip auto-resolve instead of staying paged; the
long window keeps a single bad minute from triggering a page on its own.

**6. Draft the error-budget policy with concrete, enforceable consequences.** State
what happens when the budget hits zero — feature rollouts freeze, only reliability and
rollback work ships, a postmortem is mandatory regardless of severity — and who owns
lifting the freeze, and on what evidence (budget trending back above zero, or a written
leadership override).

**7. Bake the default forward.** If the org has a service-scaffold or golden-path flow,
note that new services should inherit a starter SLO at creation time instead of
shipping with none.

## Checklist / quality gate
- Every SLI ties to a real user-facing critical path, not an internal metric nobody
  outside the team cares about.
- The SLI is written as an explicit good-over-valid ratio with exclusions stated.
- The target is justified against historical performance, service tier, or cost curve —
  not a bare round number.
- The internal SLO is strictly tighter than any external SLA covering the same journey.
- The error-budget window is stated explicitly (for example, a rolling 28 days).
- Burn-rate alerts use at least two windows to balance page speed against noise.
- The error-budget policy states concrete, enforceable consequences of exhaustion.
- SLI and target selection are flagged for human sign-off before being treated as final.

## References
- Google SRE Workbook — Implementing SLOs: https://sre.google/workbook/implementing-slos/
- Google SRE Workbook — Alerting on SLOs: https://sre.google/workbook/alerting-on-slos/
- Google SRE Book — Embracing Risk: https://sre.google/sre-book/embracing-risk/
- Google SRE Workbook — Error Budget Policy: https://sre.google/workbook/error-budget-policy/

## Composition
Feeds `capacity-planning-forecast` (headroom is measured against this SLO) and consumes
golden-signal data from `observability-instrumentation`, which also carries the
alerting layer that fires the burn-rate pages. A budget-exhaustion event should trigger
`postmortem-generator` per the policy drafted in step 6, and blast-radius limits for
`chaos-experiment-design` should reference remaining budget rather than an arbitrary
percentage. A new service's starter SLO belongs wired into its scaffold template so it
ships defined, not bolted on after launch.
