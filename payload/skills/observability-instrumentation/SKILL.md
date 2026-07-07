---
name: observability-instrumentation
description: Use when a service is missing monitoring, tracing, or alerting coverage — "add monitoring to this service," "we have no visibility into X," "set up dashboards and alerts," a golden-signal gap surfaces in an architecture or postmortem review, or an alert exists but pages on every noisy blip instead of on genuine symptoms. Scaffolds OpenTelemetry-based metrics and traces, checks golden-signal coverage (latency, traffic, errors, saturation), generates dashboard-as-code, and designs symptom-based alert rules that avoid pager fatigue. Triggers include "instrument this service," "why can't we see what's happening in production," or "this alert is too noisy."
---

# observability-instrumentation

## Overview
Builds the golden-signal observability layer for a service: what to measure, how to
instrument it with OpenTelemetry, how to turn that into dashboards-as-code, and how to
alert on it without training the on-call rotation to ignore pages. This skill owns the
coverage-and-alerting layer above raw instrumentation; for the code-level logging and
trace-propagation work itself, hand off to a structured-logging-and-tracing skill —
this skill decides what needs to exist and whether the alerting on top of it can be
trusted.

## When to use
- A service ships with no dashboards, or dashboards exist but don't cover all four
  golden signals.
- "We have no visibility into X" surfaces during an incident review or an architecture
  review.
- An alert is known to be noisy (frequent false pages) or known to be silent (it
  missed a real incident).
- A new service, or a new critical dependency, is being added and needs baseline
  coverage before launch.
- A team is migrating between metrics or tracing backends and needs the
  instrumentation re-verified, not just re-pointed.

## Workflow

**1. Check golden-signal coverage first, before touching any code.** For each
critical path, confirm all four signals exist and are queryable:
- **Latency** — how long requests take, split by success versus failure, so a
  fast-failing request doesn't silently pull down success-latency percentiles.
- **Traffic** — request volume or throughput.
- **Errors** — the rate of failed requests, with the status codes or exceptions that
  count defined precisely.
- **Saturation** — how full the service is relative to its limits: queue depth,
  connection-pool usage, CPU or memory headroom.
Note any gap explicitly — a missing saturation signal is the most common gap, and the
one most likely to turn a slow degradation into a surprise outage.

**2. Instrument with OpenTelemetry as the default, vendor-neutral layer:** a metrics
SDK for the four golden signals, a tracing SDK with context propagation across service
boundaries, and consistent resource attributes (service name, version, environment) on
every signal so cross-service correlation actually works.
```python
from opentelemetry import metrics
meter = metrics.get_meter("checkout-service")
request_latency = meter.create_histogram(
    "http.server.request.duration",
    unit="ms",
    description="Request latency by route and status class",
)
```
Prefer semantic-convention attribute names (`http.route`, `http.response.status_code`)
over ad-hoc ones — that's what lets dashboards and alerts generalize across services
instead of being hand-built per service.

**3. Generate dashboards as code, not clicked together in a UI.** A dashboard
definition belongs in version control next to the service it monitors, reviewed the
same way a code change is, and reproducible if the backend is ever swapped. At
minimum, one panel per golden signal, plus a panel showing the signal against its SLO
threshold where one exists.

**4. Design alerts on symptoms, not causes.** A symptom-based alert ("checkout latency
p99 exceeds 800ms") tells on-call something a user is actually experiencing; a
cause-based alert ("CPU exceeds 80%") often pages for something that never became
user-visible. Prefer symptom-based alerts as the paging tier, and demote cause-based
signals to dashboards or low-urgency tickets unless a cause reliably predicts user
impact before it happens.

**5. Tune alert thresholds against historical noise, not intuition.** If historical
data is available, set the threshold at a level that would have caught real past
incidents while firing rarely otherwise — a threshold that would have paged forty
times last quarter for one real incident is a threshold that trains people to ignore
the pager. Where an SLO exists, prefer burn-rate alerting over a static threshold.

**6. Link every alert to a runbook before it ships.** An alert with no linked
remediation procedure hands the responder a blank page at 3 a.m. — flag any alert
without one.

**7. Verify end to end before calling instrumentation done.** Trigger a synthetic
error or load event in a non-production environment and confirm the metric moves, the
trace appears with correct context propagation, the dashboard panel updates, and — if
the change was meant to fire an alert — the alert actually fires and resolves.

## Checklist / quality gate
- All four golden signals — latency, traffic, errors, saturation — are covered for
  every critical path, with gaps explicitly noted rather than silently skipped.
- Instrumentation uses OpenTelemetry semantic conventions, not ad-hoc metric or
  attribute names.
- Dashboards are defined as code, version-controlled, and reviewed like any other
  change.
- Paging alerts are symptom-based; cause-based signals are demoted to dashboards
  unless proven predictive.
- Alert thresholds are validated against historical incident data where available,
  not set by intuition alone.
- Every paging alert links to a runbook.
- Instrumentation is verified end to end with a synthetic trigger, not assumed to work
  because the code compiles.

## References
- OpenTelemetry Documentation: https://opentelemetry.io/docs/
- Google SRE Book — Monitoring Distributed Systems: https://sre.google/sre-book/monitoring-distributed-systems/
- Google SRE Workbook — Alerting on SLOs: https://sre.google/workbook/alerting-on-slos/

## Composition
Golden signals produced here become candidate SLIs for
`slo-error-budget-definition` and the utilization-trend input to
`capacity-planning-forecast`. Code-level logging and trace-propagation work is owned
by a separate structured-logging-and-tracing skill that this skill's dashboard-and-alert
layer sits on top of. Every new alert should link to a
`runbook-authoring-from-incident` procedure, and a `chaos-experiment-design` game day
is the way to verify the alerting actually fires under a real fault rather than only
in a synthetic test.
