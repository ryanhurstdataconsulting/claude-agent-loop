---
name: capacity-planning-forecast
description: Use when a scaling review, a known load event (launch, seasonal peak, migration), or a "will this hold up" question needs a data-backed answer instead of a guess. Analyzes historical utilization trends, calculates remaining headroom against a service's SLO, translates load-test or chaos-experiment results into a capacity model, and flags under-provisioned single points of failure before they become an outage. Triggers include "do we have enough capacity for X," "plan for peak-season traffic," "when do we need to scale this," or a saturation signal trending toward its limit with no forecast behind it.
---

# capacity-planning-forecast

## Overview
Turns historical utilization data and load-test results into a forward-looking
capacity model: how much headroom exists today, when it runs out at current growth
rates, and what breaks first if growth or a known load event outpaces provisioning.
The mechanical trend analysis is fully agent-tractable; translating a forecast into a
concrete provisioning decision — spend more now, accept the risk, or re-architect — is
a business-context call this skill surfaces rather than makes.

## When to use
- A scaling or launch review needs a "will this hold up" answer ahead of a known load
  event: a product launch, a seasonal peak, a migration.
- A saturation signal (queue depth, connection-pool usage, disk usage) is trending
  toward its limit and nobody has projected when it hits.
- Load-test or chaos-experiment results exist and need translating into a
  provisioning recommendation instead of sitting as a one-off report.
- A cost-optimization review needs the reliability side of the tradeoff stated
  explicitly, so a capacity cut doesn't silently eat into the reliability margin.
- An architecture review needs single points of failure flagged before they're
  load-bearing.

## Workflow

**1. Establish the resource baseline.** Pull historical utilization for every resource
that can saturate: compute, memory, connection pools, queue depth, disk, third-party
API rate limits, database IOPS. Use golden-signal saturation data from
`observability-instrumentation` as the primary source — a forecast built on ad-hoc,
hand-pulled numbers goes stale immediately.

**2. Fit a trend, and state its assumptions out loud.** A simple linear or
seasonal-adjusted trend on three to six months of history is usually sufficient, and
more honest than a complex model dressed up as precise. State explicitly what growth
pattern is assumed — steady linear growth, a step change from a known upcoming launch,
a seasonal spike — rather than presenting one number as certain.

**3. Calculate headroom against the service's actual limit, not an arbitrary round
number:** the SLO-implied capacity ceiling (the load level at which latency or
error-rate SLIs would breach) and the hard infrastructure limit (autoscaling-group
maximum, database connection limit, third-party rate limit) — whichever of the two
binds first.

**4. Translate a known load event's expected traffic multiplier into required
headroom directly.** For example: "3x normal peak traffic requires headroom to 3x
current p99 saturation on the connection pool, which today sits at 60% utilization at
normal peak — so the pool needs to grow before the event, independent of the growth
trend." Don't let a slow-growth trend forecast mask a step-change event sitting right
on top of it.

**5. Pull in load-test or chaos-experiment results where they exist**, rather than
extrapolating from production traffic alone — production trends show organic growth,
while a load test or a `chaos-experiment-design` fault-injection run is the only way
to know what happens past the traffic level production has actually reached.

**6. Flag single points of failure explicitly.** A resource with no forecasted
headroom problem can still be under-provisioned in a different sense: a single
instance, a single availability zone, or a single un-pooled connection that becomes
the ceiling for the entire system regardless of how much headroom every other resource
has. State these separately from the trend-based forecast — they're provisioning
gaps, not trend results.

**7. Present the forecast with an explicit decision point, not just a chart:** the
date or load level at which the resource breaches its headroom threshold at current
trend, and the lead time needed to provision more of it. Autoscaling responds in
minutes; a new database read replica or an infrastructure procurement cycle can take
weeks. The forecast is only actionable once it's compared against that lead time.

**8. Leave the provisioning decision to the reviewer.** State the tradeoff plainly —
the cost of scaling now versus the risk of running the forecast out — without silently
picking one; that's the business-context judgment call this skill surfaces, not
resolves.

## Checklist / quality gate
- The utilization baseline is pulled from real observability data, not hand-estimated
  numbers.
- Trend assumptions — linear, seasonal, step-change — are stated explicitly, not
  implied by a single chart.
- Headroom is calculated against both the SLO-implied ceiling and the hard
  infrastructure limit, whichever binds first.
- A known load event's traffic multiplier is translated into required headroom
  directly, not left to the background trend to catch.
- Load-test or chaos-experiment data is used where available instead of relying on
  production-trend extrapolation alone.
- Single points of failure are flagged separately from the trend-based forecast.
- The forecast states a breach date or load level and compares it against the actual
  provisioning lead time.
- The final scale-now-versus-accept-risk call is left to a human reviewer, not made
  silently by the forecast.

## References
- Google SRE Book — table of contents (capacity planning is treated as a core SRE
  responsibility throughout): https://sre.google/sre-book/table-of-contents/
- Google SRE Workbook — table of contents: https://sre.google/workbook/table-of-contents/

## Composition
Consumes saturation-trend data from `observability-instrumentation` and evaluates
headroom against `slo-error-budget-definition`'s target. Load-test and
fault-injection input comes from `chaos-experiment-design`; the cost side of the same
tradeoff belongs to a separate cloud-cost-optimization review outside this skill's
scope. A forecast that reveals an imminent breach with a long provisioning lead time
is exactly the kind of finding that belongs in a leadership-facing status report.
