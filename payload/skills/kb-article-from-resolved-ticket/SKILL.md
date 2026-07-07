---
name: kb-article-from-resolved-ticket
description: Use when a non-trivial support ticket has been resolved and the resolution pattern is likely to recur for other customers. Triggers include a support agent closing a ticket that took real diagnostic work, a request to "write this up for the knowledge base," a known-issue search that came up empty for a symptom that just got resolved, or a pattern of similar tickets arriving with no existing article to cite. Generalizes the specific fix into a symptom/cause/resolution/prevention knowledge-base article, checks for near-duplicate existing articles before creating a new one, and writes it in how-to voice.
---

# kb-article-from-resolved-ticket

## Overview
Turns a resolved support ticket into reusable knowledge-base content instead
of a one-off fix that only the original agent remembers. It owns one job:
generalize a specific resolution into a symptom/cause/resolution/prevention
article that the next occurrence of the same problem can be matched against
and resolved without a human repeating the original diagnostic work.

## When to use
- A ticket that required real diagnostic effort (not a one-line answer)
  just resolved, and the same symptom is plausible for other customers.
- A `known-issue-matcher` search came up empty for a ticket that then got
  resolved — that gap is the direct trigger for a new article.
- Several tickets have arrived with the same or a closely related symptom
  and no existing article covers it.
- An existing article is being revised because a ticket surfaced a better or
  more current resolution than what is currently published.

## Workflow

1. **Decide whether the resolution actually generalizes before writing
   anything.** A fix that only applied because of one customer's specific
   data, a one-off hardware fault, or an account-specific configuration
   error is not knowledge-base material — documenting it wastes a reader's
   time and adds noise to search results. Proceed only if another customer
   hitting the same symptom would benefit from the same resolution.
2. **Search for a near-duplicate article before creating a new one.** If a
   close match exists, update or extend that article instead of publishing
   a second, competing one — a fragmented knowledge base is as bad as an
   empty one, because it splits search relevance across near-identical
   entries.
3. **Strip customer-specific detail while generalizing the symptom.** Remove
   customer names, account IDs, and specific data values from the write-up;
   describe the symptom the way any customer hitting it would describe it
   (the error text they would actually see, not an internal ticket
   description).
4. **Structure the article in four parts:**
   - **Symptom** — what the user sees: the exact error text or observable
     behavior, plus the conditions under which it appears.
   - **Cause** — the underlying root cause, explained enough that a reader
     understands *why* the fix works, not just that it does.
   - **Resolution** — numbered, imperative steps in how-to voice. State the
     goal up front, then the steps; skip background theory here (link to an
     explanation-style article instead if deeper context matters).
   - **Prevention or workaround** — how to avoid hitting this again, or a
     workaround if the underlying bug is not yet fixed.
5. **Write in how-to voice, not narrative.** This content is the Diátaxis
   how-to quadrant: assumes a reader with the goal already in mind, states
   steps for a competent reader to execute, and covers realistic variations
   — it is not a tutorial and does not teach from first principles. Where an
   organization already runs a documentation-classification skill, hand off
   to it for the voice and quadrant-purity check; otherwise apply these
   how-to conventions directly.
6. **Tag the article using the same product-area taxonomy** used for ticket
   triage, so it stays discoverable through the same categorization scheme
   the rest of the support workflow uses.
7. **Link back to the source ticket(s) for internal traceability, but keep
   customer-identifying information out of the published article** — the
   internal record and the public-facing article are not the same document.
8. **Flag workaround-only articles distinctly.** If the resolution is a
   workaround for a bug that is not yet fixed, mark the article as
   `temporary` / `workaround`, link it to the tracked bug report, and revisit
   it once the underlying bug ships a real fix — a stale workaround article
   left unmarked misleads readers into thinking it is the permanent
   solution.
9. **Feed the finished article back into the known-issue search corpus** so
   the next ticket with this symptom gets a high-confidence match instead of
   repeating the diagnostic work from scratch.

## Checklist / quality gate
- [ ] The resolution was confirmed to generalize beyond the originating
      account before an article was drafted.
- [ ] A near-duplicate search ran first; an existing article was updated
      instead of a competing one being created, if a match existed.
- [ ] Customer-identifying detail is stripped from the published article.
- [ ] The article follows the symptom/cause/resolution/prevention structure
      in how-to voice.
- [ ] The article is tagged using the shared product-area taxonomy.
- [ ] Workaround-only articles are explicitly marked and linked to their
      tracked bug report.
- [ ] The article links back to the source ticket(s) internally without
      exposing that link publicly.
- [ ] Article prose passes a grammar check before it publishes.

## References
- Jam.dev — [The Rise of Technical Support Engineers](https://jam.dev/blog/the-rise-of-technical-support-engineers/) — knowledge-base-driven first-tier deflection statistic.
- [Diátaxis — How-to guides](https://diataxis.fr/how-to-guides/) — the documentation quadrant this article type maps to.

## Composition
Triggered directly by a `known-issue-matcher` no-match result on a ticket
that subsequently resolves — that gap is the clearest signal an article is
missing. Shares its structure and quadrant discipline with a general
documentation-classification skill covering tutorials, how-to guides,
reference, and explanation content; use that skill's voice and
quadrant-purity check when an organization has one. Links to
`bug-report-escalation-writer` output when the article documents a
workaround for a still-open bug, and feeds back into `known-issue-matcher`'s
search corpus once published.
