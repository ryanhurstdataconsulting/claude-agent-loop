---
name: runbook-authoring-from-incident
description: Use when tribal on-call knowledge needs to become a written runbook — "we keep hitting this, write it down," a postmortem action item calling for an operational procedure, a new on-call engineer asking "what do I do when this alert fires," or an alert that pages with no linked remediation document. Converts a symptom into a structured symptom-diagnosis-remediation-escalation document and flags which remediation steps are safe to automate versus which require a human judgment call. Triggers include "write a runbook for X," "this alert has no runbook," or a repeated incident pattern surfacing during a postmortem.
---

# runbook-authoring-from-incident

## Overview
Converts operational knowledge that currently lives only in a person's head, a chat
thread, or a postmortem action item into a structured runbook: what the symptom looks
like, how to diagnose it, how to remediate it, and when to escalate. The skill's real
judgment call is separating steps that are safe to script and run unattended from
steps that need a human's situational read — that split is what turns a runbook into
an automation backlog instead of just documentation nobody has time to read at 3 a.m.

## When to use
- A recurring incident pattern surfaces ("we keep hitting this") and the fix currently
  lives only in one person's memory or a chat thread.
- A postmortem action item calls for an operational procedure, not a code change.
- An alert fires with no linked runbook, or on-call escalates because the existing
  runbook is stale or wrong.
- A new on-call rotation member needs a written procedure instead of a hallway
  handoff.
- A chaos experiment or game day surfaces a gap in the existing remediation steps.

## Workflow

**1. Anchor on one symptom per runbook.** A runbook titled "database issues" isn't
usable at 3 a.m.; a runbook titled "checkout-service p99 latency alert firing" is. If
the request bundles multiple unrelated symptoms, split it into separate runbooks and
cross-link them.

**2. Capture the symptom precisely** — the alert name, the dashboard panel, the exact
error signature, and what a human sees that confirms this is the right runbook, not a
neighboring one with a similar symptom.

**3. Build the diagnosis tree as a sequence of checks, each with an expected-versus-
unexpected branch**, not a wall of prose:
```
1. Check <dashboard/metric>. Is X above threshold Y?
   - Yes -> go to step 2 (likely cause: connection-pool exhaustion)
   - No  -> go to step 3 (likely cause: upstream dependency)
```
Order checks from cheapest and fastest to most expensive, and from most likely to
least likely cause, so the median case resolves within the first two steps.

**4. Write remediation as literal, copy-pasteable commands or click-paths**, not a
description of what to do. "Restart the worker pool" is not a step; the actual command
is:
```
kubectl rollout restart deployment/worker-pool -n prod
```
Include the expected result after each command, so the operator knows whether it
worked before moving on.

**5. Classify every remediation step:**
- **Safe to automate** — deterministic, low blast radius, reversible (restart a
  stateless pod, clear a known-safe cache key).
- **Requires human judgment** — carries blast-radius or data-loss risk, depends on
  context the system can't see, or has no clear rollback (fail over a primary
  database, force-delete a stuck resource).
Flag the automatable steps explicitly — they're the seed list for pipeline scripting
or a self-healing job, not just prose to be read and typed by hand every time.

**6. Define the escalation path:** who gets paged next, after how long with no
progress, and what context they're handed (link the runbook, the current
diagnosis-tree position, and what's already been tried — never make the second
responder start from zero).

**7. State the abort condition** — the point at which an operator stops following the
runbook and declares a full incident or escalation instead of continuing to try steps.
A runbook with no stated abort condition invites someone to keep trying remediation
past the point where they should have escalated.

**8. Version and link it.** File the runbook where on-call actually looks during an
incident — a runbook or alert catalog, not a wiki page three clicks deep — and link it
directly from the alert definition so the page and the procedure are never separated.

## Checklist / quality gate
- The runbook covers exactly one symptom, precisely enough to distinguish it from a
  neighboring alert.
- Diagnosis steps are ordered cheapest and fastest, and most-likely-cause, first.
- Every remediation step is a literal command or click-path with an expected result,
  not a description.
- Each remediation step is explicitly classified as safe-to-automate or
  requires-human-judgment.
- The escalation path states who, after how long, and with what context handed
  forward.
- An abort condition is stated — the point at which the runbook stops and a full
  incident is declared.
- The runbook is linked directly from the alert it responds to, not left to be found
  by search.

## References
- Google SRE Book — Eliminating Toil: https://sre.google/sre-book/eliminating-toil/
- Rootly — Runbooks Guide: https://rootly.com/incident-response/runbooks
- SRE School — Operational Runbook Guide: https://sreschool.com/blog/operational-runbook/

## Composition
Most often born as a `postmortem-generator` action item, or as a gap surfaced during a
`chaos-experiment-design` game day. Steps flagged safe-to-automate feed a CI/automation
pipeline; runbooks belong in the same catalog as a service's scaffold and golden-path
documentation, and new services should ship with their first-alert runbooks pre-linked
rather than added after the first page. Every alert designed in
`observability-instrumentation` should link to a runbook before it ships.
