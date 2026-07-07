---
name: status-report
description: Use when a recurring status update is due to any audience — a team standup summary, a program-level stakeholder report built from a RAID log and sprint burndown, or an executive/board update summarizing delivery health, risk, and engineering metrics like DORA (deployment frequency, lead time, change-failure rate, mean time to recovery). Triggers include "write the status update," "what's our red/amber/green," a recurring leadership sync, a DORA or cycle-time reporting request, or a request to compress program data into a one-page narrative.
---

# status-report

## Overview
Compiles delivery data — RAID-log deltas, sprint/ticket velocity, deployment and
incident metrics — into a structured status narrative at one of three altitudes:
team, program, or executive. One reporting pipeline, three audiences; the raw
inputs and red/amber/green discipline stay the same, only the altitude of detail
and the framing change.

## When to use
- A recurring team, program, or leadership status update is due and currently
  gets assembled by hand each cycle.
- A DORA/cycle-time report is needed for engineering-health reporting (deployment
  frequency, lead time for changes, change-failure rate, mean time to recovery).
- A board or executive update needs to compress a quarter's worth of delivery,
  risk, and incident data into a one-page narrative.
- A RAID log and a sprint burndown both exist and need to become a single
  coherent status narrative rather than two separate documents.

## Workflow

1. **Pick the altitude before drafting anything** — this determines vocabulary,
   length, and what gets left out:
   - **Team altitude** — sprint/ticket-level detail, blockers by name, individual
     workstream status. Audience already has full context; be specific, not
     narrative-heavy. A red/amber/green per workstream plus a blocker list is
     often enough.
   - **Program altitude** — cross-team view. Sourced from the RAID log's diff
     summary (see `raid-log-maintainer`) plus ticket velocity/burndown. Audience
     needs "is the program on track and what's the top risk," not every ticket.
     One red/amber/green per major workstream, a short top-risks excerpt, and
     any newly escalated or newly stale RAID items.
   - **Executive altitude** — org-health view. Compresses OKR/roadmap status,
     DORA data, an incident summary, and (if in scope) hiring-pipeline data into
     a one-page narrative with an explicit "so what" framing — what does
     leadership need to *decide or notice*, not just what happened. Cut detail
     aggressively; a board reader has seconds, not minutes.
2. **Never invent a status color.** Red/amber/green (or on-track/at-risk/
   off-track) must derive from a defined rule the team already uses (e.g., "red
   if any critical-path item is more than one week late," or "amber if an
   Accountable owner is unresolved") — if no such rule exists yet, surface that
   gap rather than picking a color by feel.
3. **When DORA metrics are in scope, pull from the data source, don't estimate:**
   - **Deployment frequency** — how often the team ships to production.
   - **Lead time for changes** — commit to production-deploy elapsed time.
   - **Change-failure rate** — percentage of deploys causing a production
     failure.
   - **Mean time to recovery (MTTR)** — time from failure detection to
     restoration.
   Benchmark against the published DORA performance tiers (Elite/High/Medium/
   Low) only when the underlying data is real and recent — do not benchmark
   against a partial or stale extract without flagging it as such.
4. **Always include the DORA misuse caveat when these metrics leave the
   engineering-management altitude.** DORA metrics are team/system-level
   health indicators, not individual-performance metrics — an executive-facing
   report that could plausibly be read as ranking individuals or teams against
   each other needs an explicit line stating that these numbers are not for
   evaluating people.
5. **Pull the RAID excerpt, not the whole log**, at program and executive
   altitude — top risks by severity, anything newly escalated, anything stale
   past its SLA. The full log stays a working artifact; the report is a curated
   excerpt of it.
6. **Draft in the audience's expected format.** Some organizations expect prose
   narrative (a structured written memo, no slides); others expect a
   slide-style bulleted summary. Match the existing convention rather than
   defaulting to one house style — ask if it is not already established.
7. **Flag missing source data rather than papering over it.** If DORA data,
   RAID deltas, or burndown numbers are unavailable for this cycle, say so in
   the report ("MTTR data unavailable this cycle — pipeline instrumentation
   gap") rather than omitting the section silently or reusing last cycle's
   number.
8. **Keep a stable template cycle over cycle.** A report whose structure shifts
   every cycle is harder for a recurring audience to scan; changes to the
   template itself should be deliberate and called out, not incidental.

## Checklist / quality gate
- [ ] Altitude (team/program/exec) is explicit and the content matches it — no
      ticket-level detail leaking into an executive one-pager, no vague
      "everything's fine" summary at team level where specifics are expected.
- [ ] Every red/amber/green status traces to a stated rule, not a feel-based
      call.
- [ ] DORA figures (if included) are pulled from real data, not estimated, and
      benchmarked only when the extract is current.
- [ ] The individual-evaluation caveat is present on any DORA/cycle-time content
      reaching an executive or cross-team audience.
- [ ] The RAID content is a curated excerpt (top risks, newly escalated, newly
      stale), not the full log pasted in.
- [ ] Any missing source data is flagged explicitly, not silently omitted or
      backfilled with a stale number.
- [ ] Report prose passes a grammar check before it ships — a status report is
      client- and leadership-facing text.

## References
- DORA — [DORA's Software Delivery Performance Metrics](https://dora.dev/guides/dora-metrics/)
- Engineering Manager Tools — [DORA Metrics for Engineering Teams](https://www.em-tools.io/frameworks/dora-metrics)
- The Digital Project Manager — [RAID Logs](https://thedigitalprojectmanager.com/project-management/raid-log/)
- ProjectManager.com — [What Is a RAID Log and Why Should I Use One?](https://www.projectmanager.com/blog/raid-log-use-one)
- Amazon TPM interview-prep guide on narrative-writing culture — [How We Hire: TPM Interview Prep](https://amazon.jobs/content/en/how-we-hire/tpm-interview-prep)
- Bowdoin Group — [CTO vs. VP Engineering vs. Chief Architect](https://www.bowdoingroup.com/blog/cto-vp-engineering-chief-architect-differences/)

## Composition
Consumes `raid-log-maintainer`'s diff summary as its primary risk/issue input at
program and executive altitude, and `sprint-plan-from-spec`'s burndown scaffold
for velocity data. Program-altitude output often draws on `map-dependencies` for
critical-path framing. Executive-altitude output pairs with `incident-postmortem`
content when a reporting period includes a notable incident, and with
`adr-authoring` when a portfolio-level decision needs a one-line mention. Route
generated prose through a grammar/style-lint pass before it ships externally.
