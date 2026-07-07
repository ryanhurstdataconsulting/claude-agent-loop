---
name: maintain-research-repository
description: Use when a research organization's past studies, findings, and artifacts need to become searchable and reusable instead of trapped in decks and scattered docs — defining a tagging taxonomy, backfilling and tagging past studies, and answering "what do we already know about X" before commissioning new research. Triggers include requests to "set up a research repository," "tag our past studies," "what have we already learned about onboarding," or "audit our research archive for gaps," and file/artifact patterns like an untagged folder of research decks, a spreadsheet of past study links, or a repeated request that duplicates a prior study.
---

# maintain-research-repository

## Overview
Builds and operates the searchable memory of a research practice: a tagging
taxonomy (topic, method, product area, date, participant segment), a
backfill pass that tags existing studies against it, and a query workflow
that answers "what do we already know about X" before a new study gets
commissioned. It owns ResearchOps continuity — turning one-off studies into
a compounding institutional asset.

## When to use
- Past research lives as scattered decks, docs, or recordings with no shared
  tagging or search path.
- A team is about to commission a study and needs to check whether the
  question has already been answered by prior research.
- A new researcher or stakeholder needs to get oriented on "everything we
  know" about a product area without reading every past report.
- An existing repository's tags have drifted (inconsistent naming,
  duplicate topics under different labels) and need reconciling.

## Workflow
1. **Define the taxonomy before tagging anything.** A minimal, durable
   taxonomy needs at least four facets:
   - **Topic/theme** — what the finding is about (e.g., onboarding, pricing
     perception, navigation).
   - **Method** — how it was learned (interview, usability test, survey,
     diary study, field study).
   - **Product area** — which part of the product or feature set it touches.
   - **Date and study/report link** — when it was learned and where the
     full detail lives.
   Add participant-segment or persona as a fifth facet if the organization
   already has segments defined; do not invent new segments just to populate
   this field.
2. **Keep tags controlled, not free-text.** A fixed, small vocabulary per
   facet (a pick-list, not open text) is what makes "what do we know about
   checkout" a reliable query instead of a guess at every synonym someone
   might have typed.
3. **Backfill in reverse-chronological order.** Tag the most recent studies
   first — they are the most likely to be queried and the easiest to recall
   accurately; older studies can be backfilled opportunistically or
   deprioritized if the backlog is large.
4. **Extract a topline finding per study during backfill**, not just the
   tags. A repository of tagged links without a one-line summary per entry
   still forces someone to open every result to see if it is relevant —
   the summary is what makes search results scannable.
5. **Flag conflicting or superseded findings explicitly.** When two tagged
   studies disagree (e.g., an old study says users prefer email
   notifications, a new one says they do not), do not silently keep both —
   mark the older one as superseded and note the more recent finding, so a
   future query does not surface a false pattern.
6. **Build the "what do we already know" query as a first-class workflow,**
   not an afterthought: given a topic and product area, return the tagged
   studies that match, their topline findings, and a note on how current
   each finding is (a two-year-old finding about a rebuilt feature needs an
   explicit staleness flag).
7. **Audit for coverage gaps on a cadence.** Cross the topic and
   product-area facets to find cells with zero tagged studies — these are
   the areas most likely to need new research, and the gap map is a
   direct input to future research prioritization.
8. **Keep the repository's home stable and discoverable.** A repository that
   moves tools or locations every few months loses the trust that makes
   people check it before commissioning duplicate work — treat platform
   choice as a one-time decision, not a recurring one.

## Checklist / quality gate
- [ ] The taxonomy uses controlled facets (topic, method, product area, date)
      with a fixed vocabulary per facet, not free text.
- [ ] Every tagged entry has a one-line topline finding, not just a link and
      tags.
- [ ] Superseded or conflicting findings are marked as such, not left to
      silently coexist.
- [ ] A "what do we already know about X" query workflow exists and has been
      tested against at least one real question.
- [ ] A coverage-gap check (topic × product area) has been run at least once
      to surface under-researched areas.

## References
- NN/g, "ResearchOps 101" — https://www.nngroup.com/articles/research-ops-101/
- Dovetail, "What Is ResearchOps" — https://dovetail.com/research/research-ops/

## Composition
Ingests the output of `synthesize-with-affinity-mapping` (named themes and
topline summaries are exactly what gets tagged and stored) and of
`design-a-survey`-driven studies. Consulting the repository is the
recommended first step before running `write-a-research-plan` on a new
study, to avoid re-researching an already-answered question. Overlaps with
design-system documentation operations — the same tagging and
findability discipline applies to both.
