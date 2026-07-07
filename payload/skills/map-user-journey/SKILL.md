---
name: map-user-journey
description: Use when a team needs to see a user's end-to-end path across touchpoints to find friction or gaps — building a journey map (stages, actions, thoughts/feelings, pain points, opportunities) from research notes or Jobs-to-Be-Done statements, optionally laned against a service-blueprint view. Triggers include "map the user journey," "customer journey map," a request to see where users drop off or struggle across a multi-step flow, or a need to connect isolated pain points into one end-to-end narrative.
---

# map-user-journey

## Overview
Builds a structured journey map — stages, actions, thoughts/feelings, pain points,
and opportunities — from research notes, support tickets, or Jobs-to-Be-Done
statements, so a team can see a user's end-to-end experience in one artifact
instead of scattered anecdotes. The one job this skill owns: turning fragmented
observations into a single ordered narrative that shows where friction actually
lives.

## When to use
- Isolated complaints or pain points exist but nobody has connected them into one
  end-to-end path yet.
- A team needs to prioritize which part of a multi-step flow to fix first and
  wants to see the whole flow before choosing.
- A JTBD statement's job steps (from `write-jtbd-statements`) need to be laned out
  with the emotional and experiential detail a journey map adds.
- A cross-functional handoff point is suspected of causing drop-off (e.g., between
  sales and onboarding) and needs to be made visible.
- The request names "journey map," "customer journey," or "service blueprint."

## Workflow

**1. Fix the scope: whose journey, and starting/ending where.** A journey map
without a bounded start and end sprawls indefinitely. Anchor it to one persona (or
segment) and one job — pull the job from `write-jtbd-statements` output when
available, since a journey map without an underlying job tends to collapse into an
unstructured feature-usage timeline.

**2. Establish stages from the job steps.** If a JTBD breakdown exists, its ordered
job steps become the journey's stages directly. If not, derive stages from the raw
research notes by grouping actions into a small number (typically five to eight)
of major phases a user moves through — not every micro-action gets its own stage.

**3. Populate each stage across a consistent set of lanes:**
   - **Actions** — what the user actually does at this stage (observable, not
     inferred).
   - **Thoughts / feelings** — what the user is thinking or feeling, sourced from
     direct quotes where available, not invented.
   - **Touchpoints** — the specific channel, screen, or interaction the user
     engages with.
   - **Pain points** — where the stage breaks down, stalls, or frustrates.
   - **Opportunities** — a candidate fix or improvement, kept separate from the
     pain point it addresses so the two are not conflated.

**4. Source every entry, and mark anything unsourced.** Each lane entry should
trace back to a specific piece of research (a quote, a ticket, an observed
session). Where the team is inferring rather than citing evidence, label it
explicitly as an assumption — an unmarked assumption presented as a finding is the
most common failure mode of journey mapping.

**5. Lane against a service-blueprint view when the friction is likely
organizational.** If pain points cluster at hand-off points between teams or
systems (not just user-facing steps), add a "backstage" lane showing which internal
team or system owns that stage — this surfaces friction caused by internal
hand-offs rather than the interface itself.

**6. Call out the highest-friction stage explicitly.** A journey map that lists
pain points without ranking them is an inventory, not an analysis. Close with a
one-paragraph read: which one or two stages cause the most drop-off or frustration,
and why, based on the evidence gathered.

## Checklist / quality gate
- The journey has a named persona/segment and a named job, not a generic "the
  user."
- Every stage is populated across all five lanes (actions, thoughts/feelings,
  touchpoints, pain points, opportunities) — no stage is left thin because data was
  unavailable without saying so.
- Every entry is sourced or explicitly marked as an assumption.
- Pain points and opportunities are kept as separate entries, not merged into one
  vague note.
- The map closes with a ranked read on the highest-friction stage(s), not just a
  flat list.

## References
- Digital Leadership, the JTBD-to-UX/journey-mapping relationship — https://digitalleadership.com/glossary/jobs-to-be-done-ux/
- This Is Service Design Doing, service-blueprint method — https://www.thisisservicedesigndoing.com/methods/generating-jobs-to-be-done

## Composition
Consumes job steps from `write-jtbd-statements` and raw clustered findings from an
affinity-mapping/synthesis skill. Feeds prioritized friction points into
`run-a-design-sprint`'s Map step or directly into a PRD's problem statement. Pairs
with `run-heuristic-evaluation` when a pain point needs a deeper usability-specific
diagnosis.
