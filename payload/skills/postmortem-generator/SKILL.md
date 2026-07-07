---
name: postmortem-generator
description: Use when an incident, outage, or bad release has been resolved and a blameless postmortem needs to be written from a raw timeline, alert history, deploy log, and chat or on-call transcript — including "write the postmortem," "we owe a postmortem for that outage," "draft the incident writeup," or a severity or error-budget policy marking a postmortem as overdue. Also covers turning a manager's raw incident notes into a structured document for a security incident or a failed-release root-cause analysis, since both share the same shape as a production outage. Produces a populated blameless-postmortem document — impact, timeline, root cause, detection, response, and owned action items — and flags blame-coded language for rewrite before publication.
---

# postmortem-generator

## Overview
Turns a raw incident record — alert timestamps, deploy history, a chat transcript,
on-call notes — into a single structured, blameless postmortem: what broke, how long
it lasted, why it happened, and what changes prevent recurrence. This skill owns the
postmortem artifact end to end, from qualifying whether one is even required through
timeline reconstruction, blameless-language enforcement, and owned action-item
extraction. It applies equally to production outages, security incidents, and
failed-release root-cause writeups — the shape is the same regardless of trigger.

## When to use
- An incident is resolved and "write the postmortem" or "draft the incident writeup"
  is requested.
- A severity or error-budget policy marks a postmortem as overdue — for example, every
  SEV-1 requires one within a fixed number of business days, or an error-budget
  exhaustion event triggers one automatically.
- A security incident needs a writeup — the postmortem shape (impact, timeline, root
  cause, action items) applies directly; only the audience and sensitivity handling
  differ.
- A bad release needs a root-cause analysis — the same template applies, with a
  deployment as the fault instead of an infrastructure failure.
- A raw timeline, a chat thread, and scattered notes need to become a single
  structured, reviewable document.

## Workflow

**1. Confirm the postmortem bar.** Not every incident warrants a full writeup — check
the org's severity policy (commonly: any SEV-1/SEV-2, any customer-visible outage, any
event that consumed a meaningful share of an error budget). If the incident falls below
the bar, say so and offer a short recap instead of forcing the full template.

**2. Gather every raw signal before drafting anything.** In order of reliability:
alert-firing and resolution timestamps, deploy and change logs, dashboard/metric
snapshots, the incident chat or on-call transcript, ticket history. Do not reconstruct
a timeline from memory or a single participant's account when logs exist — timestamps
are ground truth; a participant's recollection is corroborating detail, not the source.

**3. Reconstruct the timeline as one chronological, UTC-timestamped table**, labeling
each entry by phase — Detection, Diagnosis, Mitigation, Resolution. Merging disparate
sources into a single correct sequence (a note in chat at 14:09 and an alert that fired
at 14:07 belong in the same ordered table, not two disconnected narratives) is the
highest-value part of this task.

**4. Quantify impact before writing the narrative:** user-facing symptoms; duration
(detection to resolution, and separately, start-of-impact to resolution if they
differ); the percentage of users, requests, or regions affected; and, if an SLO exists,
the error-budget burn consumed (hand this number to `slo-error-budget-definition`'s
policy if it should trigger a freeze).

**5. Frame the root cause as a system or process gap**, using a Five Whys chain or a
contributing-factors tree, and never let the chain terminate at a named individual or
"human error." Human error is a symptom, not a cause — the real question is what let
that action reach production unguarded. Not "the on-call engineer deployed a bad
config," but "the deploy pipeline had no schema validation for that config field, so a
malformed value reached production undetected."

**6. Run a blameless-language pass on the full draft** before it goes further:

| Blame-coded | Blameless rewrite |
|---|---|
| "X forgot to update the config" | "the runbook step to update the config wasn't automated or checked at deploy time" |
| "Y broke production" | "the change introduced a regression that existing tests didn't catch" |
| "the on-call engineer should have caught this" | "the alert that would have caught this fired forty minutes after impact began" |
| "human error" | name the missing guardrail instead |

**7. Extract action items, each with an owner, a due date, and a category** —
`prevent-recurrence`, `detect-faster`, or `reduce-impact`. An action item with no owner
is not done; flag it as blocking before the postmortem is marked Complete. If an action
item reveals a missing or incomplete operational procedure, hand it to
`runbook-authoring-from-incident` rather than letting it dead-end as a checklist line.

**8. Populate the template below, then route the draft for peer or team review**
before it's marked Complete — a postmortem that skips review is a private document, not
a blameless one.

```markdown
# Postmortem: <incident title>

**Status:** Draft | In Review | Complete
**Date of incident:** YYYY-MM-DD
**Authors:**
**Severity:** SEV-1 | SEV-2 | SEV-3
**Duration:** Xh Ym (detection to resolution)

## Summary
One paragraph: what broke, for how long, and who or what was affected.

## Impact
- User-facing symptoms
- Scope (percentage of users, requests, or regions)
- Error-budget / SLO impact, if applicable

## Timeline (UTC)
| Time | Event | Phase |
|---|---|---|
| 14:02 | Deploy of v2.3.1 to production | — |
| 14:07 | Error-rate alert fires (fast-burn) | Detection |
| 14:12 | On-call acknowledges, begins triage | Diagnosis |
| 14:31 | Rollback initiated | Mitigation |
| 14:39 | Error rate returns to baseline | Resolution |

## Root cause
Five Whys chain or contributing-factors list, framed at the system/process level.

## Detection
How the incident was found (alert, customer report, internal QA) and, if detection
was slow, why.

## Response
What worked in the response, and what slowed it down.

## Action items
| Action | Owner | Due date | Category |
|---|---|---|---|
| Add config-schema validation to the deploy pipeline | @owner | YYYY-MM-DD | prevent-recurrence |

## Lessons learned
What went well, what went poorly, and where the team got lucky.
```

## Checklist / quality gate
- The incident meets the org's postmortem-required severity bar, or is explicitly
  marked voluntary.
- The timeline is chronological, UTC-timestamped, and sourced from logs, alerts,
  deploys, and chat — not reconstructed from memory alone.
- Impact is quantified: duration, scope, and error-budget burn where applicable.
- The root cause names a system or process gap; no sentence terminates at a named
  individual or "human error."
- A blameless-language pass has run over the full draft, not only the root-cause
  section.
- Every action item has an owner, a due date, and a category.
- Any runbook gap the incident surfaced is handed off, not left as an orphaned
  checklist line.
- The draft is routed for peer or team review before being marked Complete.

## References
- Google SRE Book — Postmortem Culture: https://sre.google/sre-book/postmortem-culture/
- Google SRE Workbook — Postmortem Practices: https://sre.google/workbook/postmortem-culture/
- Google SRE Resources — Incident Management Guide: https://sre.google/resources/practices-and-processes/incident-management-guide/
- Rootly — Incident Response Lifecycle: https://rootly.com/incident-response/lifecycle-process

## Composition
Consumes timeline data from `observability-instrumentation` (alert history, traces,
dashboards) and, when the trigger was error-budget exhaustion, closes the loop back to
`slo-error-budget-definition`'s policy. Action items that reveal a missing or stale
operational procedure hand off to `runbook-authoring-from-incident`; action items that
reveal a systemic risk worth tracking longer-term belong in a RAID or risk log. A
falsified `chaos-experiment-design` hypothesis is written up the same way a real
incident is. Postmortem summaries roll up into a leadership-facing status report.
