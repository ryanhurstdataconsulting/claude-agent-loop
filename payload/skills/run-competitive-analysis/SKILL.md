---
name: run-competitive-analysis
description: Use when a positioning decision or a build-vs-buy call needs a market or competitor teardown — a feature comparison matrix, a pricing comparison, or a gap analysis against named competitors. Triggers include "how do we compare to...," "run a competitive analysis on...," "what are competitors doing for...," or a request to support a build-vs-buy or build-vs-differentiate recommendation with market evidence.
---

# run-competitive-analysis

## Overview
Produces a structured teardown of named competitors — a feature matrix, gap
analysis, and a build-vs-differentiate recommendation — to support a
positioning or build-vs-buy decision. The one job it owns: organizing public
signals about competitors into a comparable, decision-ready format; it does
not make the final strategic call, which needs judgment about
market context an agent can't fully supply.

## When to use
- A positioning decision needs evidence: "are we behind, ahead, or
  differentiated on X compared to competitors A, B, and C?"
- A build-vs-buy or build-vs-partner decision needs a market scan to inform
  the recommendation.
- A stakeholder asks for a feature comparison matrix ahead of a planning or
  board discussion.
- An existing competitive analysis is stale (competitors shipped new
  features, pricing changed) and needs a refresh.

## Workflow
1. **Define the comparison axes before gathering anything.** Typical axes:
   feature coverage, pricing/packaging, target segment, positioning
   message, and any axis specific to the decision at hand (e.g.,
   integration depth, platform support). Fixing the axes first prevents the
   analysis from sprawling into an unstructured feature dump.
2. **Name the competitor set explicitly and scope it.** Direct competitors
   (same product, same buyer) belong in the core comparison; adjacent or
   aspirational competitors belong in a separate "watch list" so the core
   matrix stays apples-to-apples.
3. **Gather public signals per competitor, per axis.** Pricing pages,
   product documentation, release notes, review sites, and public case
   studies are fair game. Attribute each data point to its source and date —
   competitive intelligence ages quickly, and an unsourced claim in a
   leadership deck is a liability.
4. **Build the feature matrix.** Rows are features/capabilities, columns are
   competitors (plus the home product), cells are a supported /
   partial / unsupported marker with a one-line note. Resist collapsing
   "partial" into a binary — the nuance is usually the useful part.
5. **Run the gap analysis.** From the matrix, separate findings into three
   buckets: (a) table-stakes gaps — features every competitor has that the
   home product lacks, (b) differentiation opportunities — where the home
   product already leads or could lead cheaply, and (c) noise — features
   present in the matrix but not actually decision-relevant.
6. **Draft the recommendation, flagged for review.** State a
   build-vs-differentiate-vs-ignore recommendation per gap, but mark the
   recommendation section as a draft for human judgment — the data
   gathering and matrix construction are agent-executable; the strategic
   interpretation of what to do about a gap is not.

## Checklist / quality gate
- [ ] Comparison axes were defined before data gathering started, not
      reverse-engineered after the fact.
- [ ] Every data point in the matrix is sourced and dated.
- [ ] "Partial" support is distinguished from full support and from no
      support — no false binaries.
- [ ] Gaps are separated into table-stakes, differentiation opportunity, and
      noise — not left as an undifferentiated list.
- [ ] The recommendation section is explicitly flagged as a draft requiring
      human strategic review before it's presented as a decision.

## References
- No single canonical framework was identified for this skill; informed by
  general competitive-analysis practice as described in product-management
  literature (e.g., Product School's competitive-analysis guidance and
  general PM-requirements writing). Treat sourcing rigor in the workflow
  above — not a named framework — as the quality bar.

## Composition
- Feeds `build-a-roadmap` and `draft-okrs` when a competitive gap becomes a
  roadmap theme or a key result.
- Pairs with `write-a-prd` when a specific gap gets scoped into a feature
  requirements document.
