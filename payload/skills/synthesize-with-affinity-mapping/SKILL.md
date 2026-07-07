---
name: synthesize-with-affinity-mapping
description: Use when raw qualitative research data — interview transcripts, usability-test notes, open-ended survey verbatims, support-ticket text — needs to become organized themes, named clusters, and a topline findings summary instead of staying a pile of disconnected notes. Triggers include requests to "synthesize these interviews," "run affinity mapping," "cluster these notes into themes," "what patterns are in this feedback," and file/artifact patterns like raw transcripts, sticky-note exports, or a verbatims spreadsheet awaiting analysis.
---

# synthesize-with-affinity-mapping

## Overview
Converts unstructured qualitative data into organized, named themes through
affinity mapping (also called affinity diagramming): extract discrete
observations, cluster them bottom-up by similarity, name each cluster, then
surface the cross-cutting patterns and write a topline summary distinct from
the full findings report. It owns the synthesis step between raw data
collection and a decision-ready insight.

## When to use
- Interview or usability-test notes from multiple sessions need to become
  themes rather than staying session-by-session logs.
- Open-ended survey responses or support-ticket free text need pattern
  extraction at volume.
- A stakeholder asks "what did we learn" after a round of research and needs
  an answer shorter than the raw transcripts.
- Existing findings feel like a list of quotes rather than insights, and need
  restructuring into named, defensible themes.

## Workflow
1. **Extract atomic observations first, in bulk, before clustering.** Pull
   every discrete observation, pain point, or quote out of the raw notes as
   its own item (one idea per item — a note that bundles two observations
   gets split). Do this pass session by session so no single loud participant
   dominates before clustering starts.
2. **Tag each item with its source** (participant ID or session) so later
   claims about prevalence ("4 of 6 participants") stay traceable and
   auditable, not asserted from memory.
3. **Cluster bottom-up, not top-down.** Group items by what they have in
   common with each other — never sort observations into a taxonomy decided
   in advance. Affinity mapping's value is in letting the structure emerge
   from the data; imposing categories first produces confirmation bias, not
   synthesis.
4. **Iterate cluster boundaries at least twice.** A first pass over-splits or
   under-splits almost every time. Re-read the clusters once complete and
   merge near-duplicates, split clusters that secretly contain two distinct
   ideas, and move misplaced items.
5. **Name each cluster as an insight, not a category label.** Prefer "users
   distrust auto-saved drafts" over a bare label like "drafts" — a theme name
   should be a claim someone could disagree with, which is what makes it
   useful for a decision.
6. **Surface cross-cutting patterns across clusters.** Note where the same
   root cause shows up in multiple themes (e.g., a trust issue appearing in
   both onboarding and checkout clusters) — these cross-cutting patterns are
   often the highest-leverage findings because fixing the root cause resolves
   several surface symptoms at once.
7. **State prevalence honestly.** For small qualitative samples, report
   counts ("5 of 7 participants"), not percentages — a percentage implies
   statistical generalizability that a 7-person study does not have.
8. **Write a topline summary separate from the full report.** The topline is
   3-5 sentences or bullets naming the highest-priority themes and their
   business implication — written for a stakeholder who will read only that
   paragraph. The full report, with supporting quotes and cluster detail per
   theme, is a separate section or document.

## Checklist / quality gate
- [ ] Every claimed theme traces back to specific, source-tagged observations
      — no theme asserted from memory or vibe.
- [ ] Clusters were built bottom-up from the data, not sorted into a
      pre-existing taxonomy.
- [ ] Cluster names are insight statements, not bare category labels.
- [ ] Prevalence is stated as counts for small qualitative samples, not as
      percentages implying statistical power the sample does not have.
- [ ] At least one cross-cutting pattern across clusters is named, if one
      exists in the data.
- [ ] A topline summary exists, separate from and shorter than the full
      findings report.

## References
- User Interviews, "Affinity Mapping for UX Research Data Synthesis" — https://www.userinterviews.com/blog/affinity-mapping-ux-research-data-synthesis
- Maze, "Affinity Diagrams" — https://maze.co/blog/affinity-diagrams/

## Composition
Consumes sessions run from `draft-discussion-guide-and-screener`'s guide, and
data from studies scoped by `write-a-research-plan`. Its output — named
themes, a topline summary, and the full findings report — is the natural
input to `maintain-research-repository` for long-term tagging and reuse, and
to a journey-mapping or JTBD-synthesis skill when the themes describe a
process rather than isolated pain points.
