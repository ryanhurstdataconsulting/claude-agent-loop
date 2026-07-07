---
name: build-a-prototype-plan
description: Use when a design needs a prototype scoped for usability testing — deciding what fidelity level is needed, which screens and states must be real versus faked, and where scope creep threatens the test timeline. Triggers include "what should we prototype," "how real does this need to be," a prototype-day plan inside a design sprint, a usability test that needs a testable artifact first, or a build discussion drifting from a testable mock toward a fully working feature.
---

# build-a-prototype-plan

## Overview
Scopes a prototype to exactly what a usability test script requires — no more, no
less — by fixing a fidelity level up front and listing the specific screens and
states needed to cover the script. The one job this skill owns: preventing a
prototype from either under-shooting (too rough to get honest reactions) or
over-shooting (a near-production build that blows the test timeline).

## When to use
- A test is scheduled and the team has not yet decided what, specifically, needs
  to be built to support it.
- A prototype effort is expanding past its original scope ("while we're at it,
  let's also build…") and threatens the test date.
- A design sprint's Prototype day needs a concrete build list instead of an open-
  ended "let's fake it."
- Stakeholders disagree on whether a click-through mock or a coded prototype is
  needed for the question being tested.
- The request names "prototype plan," "fidelity," or asks "what needs to be real
  for this test."

## Workflow

**1. Start from the test script, not the design.** Pull (or write) the usability
test script first — the tasks a participant will attempt. The prototype's scope is
derived entirely from what the script asks a participant to do; anything the
script never touches does not need to exist.

**2. Choose a fidelity level and hold the line on it.**
   - **Paper / low-fidelity** — sketches or static frames, walked through by a
     facilitator. Fastest, best for testing flow and concept comprehension before
     any visual design exists. Cannot test fine interaction detail or first
     impressions of polish.
   - **Click-through / mid-fidelity** — linked static screens (e.g., Figma
     prototype) simulating navigation without real logic. Good default for most
     concept and flow validation; the most common choice for a sprint-week test.
   - **Coded / high-fidelity** — a working front end, possibly with faked or
     stubbed data. Needed only when the thing being tested is interaction
     mechanics, performance feel, or real-data edge cases that a click-through
     cannot simulate.
   Match fidelity to the sprint question: testing whether the concept makes sense
   rarely justifies coded fidelity; testing a novel gesture or transition usually
   does.

**3. List every screen and state the script requires**, and only those:
   - Enumerate each task in the script.
   - For each task, list the exact screens/states a participant will see,
     including error states and empty states *only if the script exercises them*.
   - Mark each as "real" (fully built at the chosen fidelity) or "faked" (a
     Wizard-of-Oz stand-in, a hardcoded value, a screenshot standing in for a
     dynamic view).

**4. Flag scope creep against the timeline explicitly.** Any screen, state, or
polish pass not traceable to a script task is out of scope for this round — log it
as a backlog item, not a prototype requirement. If a stakeholder insists on adding
scope, force the trade-off into the open: "adding X pushes the test date by
\<estimate\>, or we drop \<Y\> to hold the date."

**5. Confirm data realism matches the test's goal.** Faked data still needs to be
plausible enough not to break immersion — lorem-ipsum content undermines
first-impression and comprehension tests even in a low-fidelity prototype.

## Checklist / quality gate
- Every screen/state in the plan traces back to a specific task in the test
  script — nothing is included "just in case."
- The fidelity level is stated once, explicitly, and applied consistently (no
  silent drift from click-through toward coded mid-build).
- Each screen/state is marked real or faked, with a note on how the fake is
  achieved (hardcoded value, screenshot, Wizard-of-Oz).
- Any requested addition beyond the script's needs is logged as a scope-creep flag
  with its cost to the timeline, not silently absorbed.
- The plan names a build owner and a date, matched against the scheduled test
  date.

## References
- GV Design Sprint, prototype-day practice — https://www.gv.com/sprint/

## Composition
Consumes the test script from a research-plan skill (`write-a-research-plan`) and
feeds the finished prototype into that same test. Runs as the Prototype-day step
inside `run-a-design-sprint`. Downstream of `structure-design-critique` when the
critique determined which direction is worth prototyping.
