---
name: structure-design-critique
description: Use when a design (screen, flow, component, or full feature) needs structured peer or stakeholder feedback before it ships, or when a pile of raw design comments needs to be turned into a clear, prioritized summary. Triggers include "run a design critique," "get feedback on this design," a design review meeting with mixed or contradictory comments, a request to separate "I don't like it" opinions from real usability defects, or a Figma/design-file comment thread that needs synthesis before a decision is made.
---

# structure-design-critique

## Overview
Turns unstructured design feedback — a review meeting, a pile of comments, or a raw
gut reaction — into a rubric-scored, prioritized critique that separates genuine
usability or consistency defects from subjective taste preferences. The one job
this skill owns: converting noisy feedback into a decision-ready summary the design
owner can act on.

## When to use
- A design is about to ship and needs a structured review pass, not an informal
  "looks good to me" thumbs-up.
- A review meeting produced a wall of comments and nobody has synthesized them yet.
- Stakeholders disagree and the disagreement needs to be sorted into "this breaks a
  usability principle" versus "this is a preference."
- A design system or component library needs a consistency-focused review before a
  new component is accepted.
- The request mentions "critique," "design review," "feedback synthesis," or "heat
  map" in a design context.

## Workflow

**1. Confirm the goal before critiquing anything.** A critique without a stated
goal turns into taste debate. Establish: what job is this design supposed to do,
for whom, and what does success look like? If no goal is stated, ask before
proceeding — critiquing against an unstated goal produces feedback nobody can act
on.

**2. Apply a critique rubric, not a vibe check.** Score or tag every piece of
feedback against fixed axes:
   - **Goal alignment** — does this design element serve the stated goal?
   - **Usability** — does it violate a known heuristic (pair with
     `run-heuristic-evaluation` for a deeper pass)?
   - **Visual consistency** — does it match the established style guide or
     design-token set?
   - **Accessibility** — contrast, focus order, labeling.

**3. Collect feedback in silence first, discuss second.** Borrow the "Art Museum /
Heat Map" pattern: gather every comment independently before group discussion
starts, so early or loud voices do not anchor everyone else. If comments already
exist (a comment thread, a meeting transcript), skip straight to clustering.

**4. Cluster into a heat map.** Group raw comments by the screen or component
region they target. Regions with the most independent comments are the genuine hot
spots — surface those first regardless of comment length or seniority of the
commenter.

**5. Separate defect from preference — this is the core deliverable.** For each
clustered comment, tag it as one of:
   - **Defect** — measurably breaks a usability heuristic, an accessibility
     criterion, or a stated goal. Actionable, not optional.
   - **Consistency gap** — deviates from the documented style guide/tokens.
     Actionable, low ambiguity.
   - **Preference** — a stylistic opinion with no objective failure behind it.
     Log it, but do not block on it; route unresolved preference disagreements to
     the design owner or decider, not a re-vote.

**6. Produce a prioritized summary**, ordered defect → consistency gap →
preference, each with the region it applies to and a suggested next step (fix,
discuss, or defer).

## Checklist / quality gate
- Every comment in the summary is tagged as defect, consistency gap, or preference
  — none are left as an unclassified "someone didn't like it."
- The summary is ordered by severity/actionability, not by the order comments were
  received.
- Defects cite the specific heuristic, accessibility criterion, or stated goal they
  violate — not just "this is confusing."
- Preference items are logged but explicitly marked non-blocking, with an owner
  named for final call if the disagreement persists.
- The design owner receives a heat-map view (which regions drew the most
  independent comments) alongside the prioritized list.

## References
- Google Ventures' critique method (Art Museum, Heat Map, Speed Critique) — https://design-sprint.com/google-ventures-design-sprint/

## Composition
Pairs with `run-heuristic-evaluation` for the usability axis of the rubric, and
with an accessibility-audit skill for the accessibility axis. Feeds into
`run-a-design-sprint`'s Decide step when critique happens mid-sprint. Upstream of a
design-system component-review workflow when the critique target is a shared
component rather than a one-off screen.
