---
name: run-a-design-sprint
description: Use when a team needs to validate a significant product bet in days rather than months — structuring a five-day (or compressed) design sprint agenda, converging on a direction with a decision method, and scoping a testable prototype. Triggers include "design sprint," "sprint week," a request to go from a vague problem to a tested prototype fast, a kickoff for a high-risk or high-ambiguity feature bet, or a need for a storyboard and test plan before any code gets written.
---

# run-a-design-sprint

## Overview
Structures a compressed, time-boxed sprint (canonically five days: Map, Sketch,
Decide, Prototype, Test) that takes a team from a vague, high-risk problem to a
tested prototype and real user reactions — without committing to full production
build-out. The one job this skill owns: turning an ambiguous, high-stakes bet into
a scoped agenda, a converged direction, and a validated (or invalidated) prototype
brief.

## When to use
- A team is about to commit significant engineering time to an idea nobody has
  validated with a real user yet.
- Stakeholders disagree on direction and need a structured way to converge instead
  of a meeting that goes in circles.
- Leadership wants evidence before greenlighting a build, and there is no time for
  a multi-week research cycle.
- The request explicitly names "design sprint," "GV sprint," "sprint week," or asks
  to "de-risk this idea before we build it."
- A new 0-to-1 feature or a high-ambiguity redesign needs a shared, external-facing
  problem framing before anyone opens a design tool.

## Workflow

**1. Frame the challenge (pre-sprint, or Day 1 morning).**
Confirm: the long-term goal, the sprint question ("what do we need to learn to know
if this is worth building?"), and a single decider who breaks ties. Skip the sprint
entirely if there is no real decider — it will stall on Decide day.

**2. Map (Day 1).** Build a simple end-to-end map of the problem: actors, the
critical path, and where the target moment/friction sits. Interview available
experts and capture their input as "How Might We" notes tied to spots on the map.
Pick a target — a specific segment of the map worth solving first — before the day
ends.

**3. Sketch (Day 2).** Individually generate concrete solution concepts, not group
brainstorms. A useful funnel: rapid variations (Crazy 8s) → one refined "solution
sketch" per person, detailed enough that someone unfamiliar with it can understand
it without narration.

**4. Decide (Day 3).** Converge without a live debate consuming the day:
   - **Art Museum** — post every sketch silently; everyone reviews.
   - **Heat Map** — dot-vote in silence on the parts that stand out.
   - **Speed Critique** — brief, timed critique per sketch capturing standout ideas
     and open questions, sketch author stays silent until the end.
   - **Straw poll** — each person casts one vote for their favorite overall.
   - **Supervote** — the decider makes the final call, informed but not bound by
     the straw poll.
   Storyboard the winning concept as a linear sequence of panels — this becomes the
   prototype's shot list.

**5. Prototype (Day 4).** Build only what the test script requires ("fake it") —
hand off to `build-a-prototype-plan` for fidelity and scope decisions. The goal is
a realistic-enough artifact for five users to react to honestly, not a working
product.

**6. Test (Day 5).** Run five one-on-one sessions against the storyboard's flow.
Capture reactions per storyboard panel, not just an overall verdict, so the team
can see exactly where the concept breaks down. Hand off synthesis to research
skills rather than eyeballing it live.

**Compressing the sprint.** A 3-day or 2-day version is common and legitimate for
lower-stakes bets: collapse Map+Sketch into one day, or run Decide and Prototype in
the same day if the storyboard is small. Never compress Test — a sprint without a
real user reaction is not a sprint, it is an internal design review.

## Checklist / quality gate
- A single sprint question and a single decider are named before Day 1 starts.
- The Decide step used a documented convergence method (not an open-ended debate)
  and produced one storyboard, not several competing ones.
- The prototype brief lists exactly which screens/states are real versus faked,
  scoped to the test script.
- At least five test sessions are planned or completed against the storyboard.
- Findings are captured per storyboard panel, with a clear go / iterate / kill
  recommendation tied back to the original sprint question.

## References
- GV Design Sprint — https://www.gv.com/sprint/
- design-sprint.com, breakdown of the Google Ventures process — https://design-sprint.com/google-ventures-design-sprint/

## Composition
Hands off storyboard convergence to `structure-design-critique` when the team needs
a lighter-weight critique instead of a full sprint. Feeds its Day 4 into
`build-a-prototype-plan` for fidelity/scope decisions, and its Day 5 into a research
synthesis skill (affinity-mapping-style clustering) for structured findings. Pairs
with a problem-framing skill (PRD/JTBD-style intake) upstream of Day 1 when the
sprint question itself is still fuzzy.
