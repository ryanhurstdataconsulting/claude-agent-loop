---
name: design-ops-tooling-audit
description: Use when a design organization's tool stack — licenses, plugins, and the design-to-code hand-off chain — needs a health, cost, or redundancy review. Triggers include "design tooling audit," "which Figma seats are unused," "consolidate our design tools," "broken hand-off between Figma and Storybook," or a request to find redundant or unused design/design-ops tooling before a renewal or budget review.
---

# design-ops-tooling-audit

## Overview
Inventories a design organization's tools and licenses per team, flags
redundant or unused tools and broken integration links in the
design-to-code hand-off chain, and recommends consolidation — surfacing
the findings for a human procurement decision rather than making that
call directly.

## When to use
- A license renewal or budget review is coming up and needs an
  evidence-based case for what to keep, cut, or consolidate.
- Multiple teams have accumulated overlapping tools (two different
  handoff tools, three prototyping tools) without a coordinated decision.
- The hand-off chain between design and code has a known or suspected
  break — for example, tokens updated in a design tool never reach the
  documentation site or codebase.
- A new DesignOps function is standing up and needs a baseline inventory
  of what's actually in use before proposing changes.

## Workflow

### 1. Inventory the current stack
Build a table of every design-related tool in use, per team where
relevant:
- Tool name and category (design/prototyping, handoff, documentation,
  token management, user testing, whiteboarding, asset management).
- License count purchased versus active users (seats paid for versus
  seats actually logging in — the single biggest source of waste).
- Owning team/budget line, and renewal date.

### 2. Map the hand-off chain
Trace the actual path a design decision takes from creation to shipped
product, stage by stage (a typical chain: design tool → token
export/sync → documentation site → codebase/build). At each hand-off
point, check:
- Is the sync automated, or manual and prone to going stale?
- When was it last verified to work end-to-end?
- Is there a single point of failure (one person's manual export step)?

Flag any broken or manual-only link as a process risk, not just a tooling
gap — a broken sync between a token source and its documentation site
means the documentation is actively lying to consumers.

### 3. Flag redundancy
Two tools serving materially the same purpose is not automatically a
problem (a transition period, or two teams with genuinely different
needs, can justify it) — but flag it and ask why:
- Same category, low usage on one side → consolidation candidate.
- Same category, both heavily used → investigate whether it's actual need
  divergence or historical accident (a team just never migrated).

### 4. Flag under-utilization
- Seats paid for but inactive over a defined lookback window (a
  reasonable default is 90 days, but use the project's own review cadence
  if one exists).
- Paid tiers/features never actually used (e.g., a token-sync integration
  that's part of the license but was never configured).

### 5. Recommend, don't decide
Produce a ranked list of consolidation/cut candidates with the evidence
(seat utilization, redundancy overlap, cost) behind each, and an estimated
savings or risk-reduction per item. The actual procurement call —
canceling a license, migrating a team off a tool they're attached to —
is a human decision informed by this report, not one this audit makes.

## Checklist / quality gate
- Every tool in the inventory has a category, seat count, and active-usage
  figure — not just a name on a list.
- Every hand-off link in the chain is checked for automation status and
  last-verified date, and broken/manual links are flagged explicitly.
- Redundancy findings state which tools overlap and by how much usage,
  not just "these seem similar."
- Recommendations are ranked by evidence (cost, risk, utilization), and
  each includes the supporting number, not just a bare suggestion.
- The report explicitly defers the final cut/keep/consolidate decision to
  the requester — it presents evidence, it does not unilaterally recommend
  canceling a specific paid contract without that framing.

## References
- DesignOps roles and partnerships framing (informs which stakeholders own
  which parts of the tool chain): https://www.nngroup.com/articles/designops-roles-partnerships/

## Composition
Findings about a broken token-to-documentation sync feed directly into
`design-tokens` and `audit-storybook-documentation` as root-cause context.
Pairs with `draft-contribution-model` when tooling gaps are blocking a
specific pipeline stage (e.g., no shared handoff tool makes the Design →
Build stage unreliable).
