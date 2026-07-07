---
name: write-jtbd-statements
description: Use when a feature idea, customer quote, or support ticket needs to be re-grounded in the underlying customer job rather than a surface-level feature request — converting raw input into Jobs-to-Be-Done statements (situation, motivation, desired outcome) and mapping job steps to locate friction. Triggers include "what job is this actually solving," a feature request that starts with a proposed solution instead of a problem, a pile of customer quotes or interview notes that need reframing, or a PRD whose problem statement reads like a feature list.
---

# write-jtbd-statements

## Overview
Converts raw customer input — quotes, feature requests, interview notes, support
tickets — into structured Jobs-to-Be-Done (JTBD) statements that describe the
underlying job the customer is "hiring" the product to do, independent of any
particular solution. The one job this skill owns: re-grounding a solution-shaped
request in the problem it is actually trying to solve.

## When to use
- A feature request arrives already shaped as a solution ("add a button that…")
  and the team suspects the real need is broader or different.
- Customer interview notes or support tickets need to be turned into a defensible
  problem statement before a PRD gets written.
- A PRD's "problem statement" section reads like a list of proposed features
  instead of a description of user need.
- The team wants to check whether two seemingly different feature requests are
  actually the same underlying job in disguise.
- A journey map needs a job to organize itself around (see `map-user-journey`).

## Workflow

**1. Collect the raw input.** Customer quotes, support tickets, sales-call notes,
or a feature request as originally phrased. Do not paraphrase yet — keep the
original language, since word choice often hints at the real motivation.

**2. Strip the proposed solution to find the underlying job.** For each input, ask
"what is this person actually trying to accomplish, of which the requested feature
is just one possible means?" A request for "an export-to-CSV button" might really
be "get this data into a tool I already trust for reporting" — a job a CSV export
solves, but so might several other solutions.

**3. Write the statement in the canonical three-part structure:**
   - **Situation** — the circumstance triggering the need ("When I'm reviewing
     last week's numbers before a Monday stand-up…").
   - **Motivation** — the underlying driver ("…I want to compare them against
     targets without switching tools…").
   - **Desired outcome** — the functional or emotional result they are actually
     after ("…so I can walk into the meeting with a confident recommendation.").
   Full form: "When \<situation\>, I want to \<motivation\>, so I can \<outcome\>."

**4. Distinguish the job from the solution, explicitly.** Keep a two-column note:
the raw request on one side, the extracted job statement on the other. This makes
it visible when two different feature requests collapse into the same job — a
strong signal that a single, better solution could replace both.

**5. Map job steps onto a sequence.** Break the job into the ordered steps a
customer moves through to accomplish it (not the product's steps — the customer's).
For each step, note where friction, workaround, or abandonment shows up in the raw
input. This step is the natural hand-off point to `map-user-journey` when the team
wants stages/emotions/touchpoints layered on top.

**6. Flag statements that cannot be grounded.** If the raw input does not contain
enough signal to write a defensible situation/motivation/outcome, say so rather
than inventing one — a fabricated JTBD statement is worse than an admitted gap,
because it launders a guess as validated insight.

## Checklist / quality gate
- Every JTBD statement follows the situation/motivation/outcome structure, not a
  restated feature request.
- Each statement traces back to a specific raw input (quote, ticket, note) — no
  statement is invented without a source.
- The original feature request and the extracted job are shown side by side so a
  reviewer can check the extraction was not a leap.
- Job steps are ordered from the customer's point of view, not the product's
  internal workflow.
- Any statement with insufficient source signal is flagged as unvalidated rather
  than presented with false confidence.

## References
- Strategyn's JTBD framework — https://strategyn.com/jobs-to-be-done/
- ProductPlan, Jobs-to-Be-Done Framework glossary — https://www.productplan.com/glossary/jobs-to-be-done-framework

## Composition
Feeds `map-user-journey` (job steps become journey stages) and a PRD-writing skill
(the job statement becomes the problem-statement section). Pairs with an
affinity-mapping/synthesis skill when the raw input is large enough to need
clustering before job extraction. Upstream of `run-a-design-sprint`'s framing step
when the sprint question itself needs grounding in a real job first.
