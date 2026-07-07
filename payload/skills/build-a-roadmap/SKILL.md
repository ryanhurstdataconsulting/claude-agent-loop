---
name: build-a-roadmap
description: Use when a prioritized backlog and a set of strategic themes need to become a shareable roadmap artifact — a timeline, a now/next/later board, or a stakeholder-facing sequencing narrative. Triggers include "build a roadmap," "put this on a timeline," "what's the now/next/later view," or a leadership request to see how a ranked backlog turns into a communicated plan across a quarter or a year.
---

# build-a-roadmap

## Overview
Converts a prioritized list of initiatives into a shareable roadmap — a
timeline or now/next/later board with a narrative explaining the sequencing.
The one job it owns: structuring and communicating a credible sequence of
bets; it does not set the strategic themes or make the prioritization call
that produced the ranked list in the first place.

## When to use
- A prioritized backlog (from `prioritize-with-rice` or another ranking
  exercise) needs to become a communicable plan for leadership or
  cross-functional stakeholders.
- A quarterly or annual planning cycle needs a roadmap artifact to present.
- An existing roadmap has drifted from reality (shipped items still shown as
  future, no items reflect a recent strategy shift) and needs a refresh.
- A team needs to separate firm commitments from exploratory bets before a
  stakeholder review, so expectations aren't set on speculative work.

## Workflow
1. **Confirm the ranked input exists.** A roadmap is a sequencing artifact,
   not a prioritization one — if the backlog isn't ranked yet, that's a
   prerequisite step (see Composition), not something to improvise inline.
2. **Choose the format that fits the audience:**
   - **Now / Next / Later** — best for audiences who need direction without
     false precision on dates; low-maintenance, resists becoming stale.
   - **Timeline (quarter-by-quarter or month-by-month)** — best when
     stakeholders need to plan around specific dates (a launch,
     board meeting, or dependent team's own roadmap).
   - **Theme-based board** — groups initiatives under strategic themes
     rather than dates, useful when the sequencing itself is still fluid but
     the priorities are clear.
3. **Separate commitments from bets, explicitly.** Mark each item as either
   a hard commitment (a date or quarter the team is accountable to) or an
   exploratory bet (direction is set, timing is not). Presenting a bet as a
   commitment is the single most common roadmap failure — it erodes trust
   the first time the date slips.
4. **Write the sequencing narrative.** For each theme or time horizon,
   explain *why* this is next — the tradeoff being made, the dependency
   being cleared, or the risk being retired. A roadmap without a narrative
   is a list; the narrative is what makes it defensible to a skeptical
   stakeholder.
5. **Version and date the artifact.** Roadmaps go stale fast. Include a
   "last updated" date and note what changed since the prior version so
   readers don't have to guess whether they're looking at the current plan.

## Checklist / quality gate
- [ ] Every item is a ranked, chosen initiative — not a first pass at
      candidates still being scored.
- [ ] Commitments and exploratory bets are visually and textually
      distinguishable, not lumped together.
- [ ] Each theme or time horizon has a one- or two-sentence "why now"
      rationale, not just a list of item names.
- [ ] The artifact is dated and states what changed from the prior version.
- [ ] Out-of-roadmap items (explicitly deprioritized, not just omitted) are
      noted somewhere if a stakeholder is likely to ask about them.

## References
- GitLab product management competency framework — https://handbook.gitlab.com/handbook/product/product-management/product-cdf-competencies/
- Product Compass, PM competence map — https://www.productcompass.pm/p/your-pm-competence-map-skills-assessment

## Composition
- Downstream of `prioritize-with-rice` — consumes a ranked backlog as its
  primary input.
- Pairs with `draft-okrs` when roadmap themes should map onto quarterly key
  results, and with `write-a-prd` when a roadmap item needs to be scoped
  into a requirements document before execution.
