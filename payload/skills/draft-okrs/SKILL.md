---
name: draft-okrs
description: Use when a product or team needs quarterly or annual objectives and key results drafted from a strategy statement — turning a goal like "grow enterprise adoption" into measurable OKRs. Triggers include "draft OKRs for...," "what should our key results be," a planning-cycle request to turn a strategy into objectives, or a review of existing OKRs that reads as vague or unmeasurable ("improve engagement," "delight customers").
---

# draft-okrs

## Overview
Translates a strategy statement into one to three objectives, each with a
small set of measurable key results, and checks the draft against SMART
criteria. The one job it owns: structuring goals into a measurable OKR
format and flagging vanity metrics — it does not supply the underlying
business judgment about which strategy or metric actually matters, which
needs context an agent can't fully carry.

## When to use
- A team or product area has a strategy statement or direction but no
  quarterly/annual objectives yet.
- Existing OKRs read as vague, unmeasurable, or output-focused ("ship
  feature X") rather than outcome-focused ("increase retention by Y").
- A planning cycle needs a first draft of OKRs to bring into a leadership
  or team review.
- A mid-cycle check wants to confirm existing key results still trace back
  to a real business outcome rather than a vanity metric.

## Workflow
1. **Start from the strategy statement, not a feature list.** An objective
   answers "what are we trying to achieve," not "what are we going to
   build." If the input is a list of features or projects, work backward to
   the outcome those projects are meant to produce before drafting the
   objective.
2. **Draft one to three objectives.** More than three per team dilutes
   focus and signals the strategy itself hasn't been narrowed enough. Each
   objective should be:
   - **Qualitative and inspirational** — a direction, not a number
     ("become the default choice for mid-market teams," not "hit $2M ARR").
   - **Time-bound** to the planning period (quarter or year).
   - **Owned** by a single team or clearly cross-functional, not ambiguous.
3. **Draft two to four key results per objective.** Each key result should
   be:
   - **Measurable** — a number, a percentage, or a binary
     milestone, not a description of effort.
   - **Outcome-focused, not output-focused** — "reduce checkout
     abandonment from 40% to 30%," not "ship the new checkout flow."
     Shipping a feature is an output; the metric it's supposed to move is
     the outcome.
   - **Independently ownable** — a team should be able to move the number
     without depending on a result it doesn't control.
4. **Run the SMART check.** Specific, Measurable, Achievable, Relevant,
   Time-bound. A key result that fails "Measurable" (no clear number) or
   "Relevant" (doesn't obviously ladder up to the objective) gets rewritten
   or cut, not kept for completeness.
5. **Flag vanity metrics explicitly.** A key result that can go up without
   the business actually improving — raw signups with no activation gate,
   page views with no engagement follow-through — gets called out by name
   in the draft, with a suggested outcome-linked alternative, rather than
   silently included.
6. **Leave the metric-selection judgment visible, not resolved.** Where
   more than one plausible key result exists for an objective, present the
   options with tradeoffs rather than picking one unilaterally — metric
   selection is a business call that needs a human owner.

## Checklist / quality gate
- [ ] No more than three objectives for a single team or planning period.
- [ ] Every key result has a number, percentage, or binary milestone — no
      output-only phrasing ("launch X," "build Y") standing in for an
      outcome.
- [ ] Every key result passes the SMART check, or was rewritten/cut when it
      didn't.
- [ ] Any vanity-metric risk is called out explicitly with a suggested
      outcome-linked alternative.
- [ ] Each key result plausibly ladders up to its parent objective — no
      orphaned metrics included for volume.

## References
- No single canonical OKR specification was identified — the literature is
  broad and fragmented across practitioners. Treat the SMART-criteria check
  and the outcome-vs-output distinction in the workflow above as the quality
  bar in place of one canonical source.

## Composition
- Pairs with `build-a-roadmap` — roadmap themes should be traceable to an
  objective, and key results give the roadmap its success metrics.
- Pairs with `write-a-prd` — a PRD's success-metrics section should trace
  back to a key result rather than inventing a parallel metric.
- Consumes output from `run-competitive-analysis` when a competitive gap
  becomes the basis for an objective.
