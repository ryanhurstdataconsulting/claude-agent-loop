---
name: tech-radar-update
description: Use when a periodic (commonly quarterly) technology-radar refresh is due, or when a new tool, library, or platform needs to be classified into Adopt, Trial, Assess, or Hold for an organization's stack. Triggers include "update the tech radar," "what's our official stance on X," multiple teams having silently standardized on different tools for the same job, a new dependency landing in a repository that isn't reflected anywhere, or a leadership request for a stack-wide inventory ahead of an architecture review or a build-vs-buy decision. Produces a ring-classified inventory (Adopt/Trial/Assess/Hold) with a rationale per entry, surveyed from actual dependency manifests and team input rather than drafted from memory.
---

# tech-radar-update

## Overview
Produces a periodic technology-radar snapshot — the organization's own inventory
of languages, frameworks, tools, and platforms, classified into Adopt / Trial /
Assess / Hold, each with a short rationale — by surveying actual repository usage
and team input rather than starting from a blank page or a stale prior version.
This skill owns the survey-and-classify artifact; contested ring placements are
routed to the humans who own the call.

## When to use
- A periodic (commonly quarterly) technology-radar refresh is due.
- A new tool, library, or platform was recently adopted, piloted, or deprecated
  somewhere in the stack and isn't reflected in any current document.
- Leadership wants a stack-wide inventory before an architecture review or a
  `build-vs-buy-memo` decision.
- Multiple teams have silently standardized on different tools for the same job
  and need a consolidated view to reconcile.
- Someone asks "what's our official stance on X" and there is no current source
  of truth to point to.

## Workflow

**1. Survey actual adoption before drafting any rationale.** In order of
reliability: dependency manifests across every repository in scope (for example
`package.json`, `pyproject.toml` or `requirements.txt`, `go.mod`, `Gemfile`,
`pom.xml`/`build.gradle`); CI and infrastructure config (Dockerfiles, Terraform
providers, CI runner images); and direct team input — a short survey or thread
asking what's in active use versus legacy. Do not treat a stale prior radar as
ground truth; adoption drifts every cycle.

**2. Group findings into quadrants.** The ThoughtWorks-style convention is
Techniques, Tools, Platforms, and Languages & Frameworks. Not every organization
needs all four — skip an empty quadrant rather than padding it with weak
entries.

**3. Classify each entry into a ring, using adoption breadth and team confidence
as the primary signal:**
- **Adopt** — in active, broad production use; the organization's default choice
  for this job; low risk to recommend for new work.
- **Trial** — in production on at least one team, worth pursuing further, not
  yet the default; state what still needs to happen before it graduates to
  Adopt.
- **Assess** — worth exploring (a spike, a pilot, a credible external write-up)
  but not yet in production anywhere; no team should read this as a green light
  for new work.
- **Hold** — proceed with caution: deprecated, actively being migrated away
  from, or a poor fit the organization has learned the hard way. State why — a
  Hold entry with no rationale reads as an opinion, not a signal.

**4. Draft a short rationale per entry.** What it's used for, why it sits in that
ring, and what would move it to a different ring next cycle. A bare ring label
with no reasoning defeats the point of the radar — the rationale is the
deliverable, not the placement alone.

**5. Diff against the prior cycle's radar, if one exists.** Call out every entry
that changed rings, every new entry, and every entry retired since the last
cycle. The delta is often more useful to readers than the full snapshot, since
it's what actually changed since they last checked.

**6. Route contested entries to a human.** When a team champions a tool
leadership wants to Hold, or the reverse, flag it rather than silently picking a
ring — the skill classifies from evidence, it does not adjudicate a live
technology dispute.

**Common gotchas:**
- Confusing "a senior engineer likes it" with Trial status — Trial requires
  actual production use by a team, not enthusiasm.
- Letting the radar become a wishlist, where everything interesting lands in
  Assess and never leaves — prune stale Assess entries each cycle.
- Placing an entry in Hold with no stated reason, which invites litigation at
  the next planning meeting instead of settling the question.
- Treating quadrant and ring names as fixed law. The ThoughtWorks four-by-four
  shape is a widely adopted convention, not a spec — confirm the organization's
  own variant before assuming it applies unmodified.

## Checklist / quality gate
- [ ] Every entry is backed by an actual adoption signal (manifest, CI config,
      or direct team confirmation) — not guessed.
- [ ] Every entry has a short rationale, not just a ring label.
- [ ] The ring definitions in use (Adopt/Trial/Assess/Hold, or the
      organization's own variant) are stated explicitly at the top of the
      document.
- [ ] Entries that changed rings, are newly added, or were retired since the
      prior cycle are called out as an explicit delta.
- [ ] Contested ring placements are flagged for human decision rather than
      silently resolved.
- [ ] Empty quadrants are omitted rather than padded with weak entries.

## References
- [ThoughtWorks Technology Radar](https://www.thoughtworks.com/radar) — the
  widely adopted Adopt/Trial/Assess/Hold quadrant-and-ring format this skill
  follows. Treat the exact quadrant set as a convention to confirm against the
  organization's own practice, not a fixed specification.

## Composition
- Feeds `build-vs-buy-memo` and `adr-authoring` — an entry moving from Assess to
  Trial (or a Hold with no in-house replacement) is a common trigger for a
  build-vs-buy evaluation or an architecture decision record.
- Pairs with `well-architected-review` when the survey step needs deeper
  infrastructure and cloud-platform coverage than a dependency-manifest scan
  provides.
- Hands off contested ring placements to the human architecture or leadership
  group that owns the final call.
