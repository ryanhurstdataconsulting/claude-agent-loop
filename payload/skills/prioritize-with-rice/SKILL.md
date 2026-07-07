---
name: prioritize-with-rice
description: Use when a backlog of candidate features, initiatives, or bugs needs a defensible ranked order and someone asks for a "priority score," "RICE score," or "what should we build first." Triggers include a spreadsheet or list of competing ideas with no agreed sequence, a stakeholder request to justify why one item beats another, or language like "score this backlog," "rank these initiatives," or "which of these is worth doing."
---

# prioritize-with-rice

## Overview
Scores and ranks a backlog of candidate initiatives using the RICE framework
(Reach × Impact × Confidence ÷ Effort) so a list of competing ideas becomes a
defensible, ordered sequence. The one job it owns: producing a transparent,
recalculable ranking from structured inputs — not deciding the underlying
estimates themselves, which still require human judgment about the market and
the product.

## When to use
- A backlog of features, initiatives, or bug-fix candidates needs a ranked
  order and the current order is either absent or unexplained.
- A stakeholder is pushing back on a priority call and wants to see the
  reasoning, not just the conclusion.
- Multiple teams are competing for the same engineering capacity and need a
  shared, apples-to-apples comparison.
- An existing prioritization pass feels stale (new items added, old
  estimates outdated) and needs a refresh.

## Workflow
1. **Elicit the four inputs per backlog item.** For each item, get or
   estimate:
   - **Reach** — how many users/customers it affects in a defined time
     window (e.g., "per quarter"). Use a real number or a per-quarter
     estimate, not a vague "a lot."
   - **Impact** — the effect per user, usually on a discrete scale (e.g.,
     3 = massive, 2 = high, 1 = medium, 0.5 = low, 0.25 = minimal).
   - **Confidence** — how sure the estimate is, as a percentage (100% = high
     confidence, 80% = medium, 50% = low). Low confidence should pull an
     item down even if the raw score looks good.
   - **Effort** — person-time to ship, in a consistent unit (person-months
     or person-weeks) across every item — comparing weeks against months
     silently distorts the ranking.
2. **Compute the score.** `RICE = (Reach × Impact × Confidence) ÷ Effort`.
   Keep the inputs visible next to the score — the number alone invites
   disputes; the visible math resolves them.
3. **Rank and annotate.** Sort descending by score, but do not treat the
   ranking as gospel:
   - Flag **dependencies** — an item that unblocks three others may deserve
     a bump regardless of its raw score.
   - Flag **table-stakes exceptions** — compliance requirements, a
     contractual commitment, or a security fix can outrank its score; call
     these out explicitly rather than silently reordering.
   - Flag items with **low confidence and high score** as needing more
     validation before committing engineering time.
4. **Produce a ranked table** with columns for Reach, Impact, Confidence,
   Effort, Score, and a Notes column for overrides and dependencies. Keep the
   raw inputs in the deliverable, not just the final rank — that is what
   makes the exercise defensible under later scrutiny.
5. **Re-run, don't re-litigate, when estimates change.** RICE is meant to be
   cheap to recompute — when a new item is added or an estimate changes,
   update the table rather than reopening the whole discussion.

## Checklist / quality gate
- [ ] Every item has all four inputs (Reach, Impact, Confidence, Effort) — no
      blank cells silently defaulted.
- [ ] Effort is in a consistent unit across every item in the table.
- [ ] Dependencies and table-stakes exceptions are called out in a Notes
      column, not silently folded into the score.
- [ ] The raw inputs are shown alongside the computed score so the ranking
      is auditable, not just asserted.
- [ ] Low-confidence, high-score items are flagged for further validation
      rather than treated as ready to build.

## References
- Intercom, "RICE: Simple prioritization for product managers" — https://www.intercom.com/blog/rice-simple-prioritization-for-product-managers/
- ProductPlan, RICE scoring model glossary — https://www.productplan.com/glossary/rice-scoring-model

## Composition
- Consumes items from `write-a-prd` (a scoped feature) or a raw backlog;
  produces the ranked input that `build-a-roadmap` sequences into a timeline.
- Pairs with dependency-mapping work when Effort or sequencing depends on a
  cross-team critical path.
