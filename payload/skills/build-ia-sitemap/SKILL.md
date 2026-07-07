---
name: build-ia-sitemap
description: Use when a product needs its navigation or information architecture defined or audited — inventorying content and features, grouping them into a taxonomy informed by card-sort results, producing a sitemap with navigation labels, and flagging orphaned or duplicate paths. Triggers include "build a sitemap," "fix our navigation," "information architecture," a growing product where users can't find features, duplicate or conflicting menu paths, or a request to organize content/features into sections before a redesign.
---

# build-ia-sitemap

## Overview
Inventories a product's content and features, groups them into a defensible
taxonomy, and produces a sitemap with navigation labels and hierarchy depth — while
flagging orphaned pages, duplicate paths, and mislabeled sections. The one job this
skill owns: turning an ungoverned pile of pages/features into a navigable structure
a user can predict their way through.

## When to use
- A product has grown organically and users (or support tickets) report they can't
  find a feature that does exist.
- The same content or function is reachable through two or more inconsistent
  paths, and nobody has audited which is canonical.
- A redesign or new-section launch needs the existing navigation restructured, not
  just a new page bolted onto the old structure.
- Card-sort results exist (from users grouping content cards) and need to become an
  actual sitemap and label set.
- The request names "sitemap," "IA," "information architecture," or "navigation
  audit."

## Workflow

**1. Inventory everything first, before organizing anything.** Enumerate every
existing page, screen, or discrete feature — pull from a route table, a CMS
export, or a manual crawl if nothing else exists. Do not group as you go; a
content inventory done while simultaneously trying to categorize produces a biased,
incomplete list.

**2. Tag each inventory item with its type and audience.** At minimum: is it
content or a functional feature; is it for a specific user role or open to
everyone; how frequently is it used (if usage data exists). This tagging is what
later distinguishes a genuine orphan from a rarely used but intentional page.

**3. Group into a taxonomy — informed by evidence, not committee guess.** If
card-sort data exists, derive the groupings and their labels directly from where
users placed cards and what they called the groups (open card sorts give the
labels; closed card sorts validate labels you already have). Without card-sort
data, group by the user's mental model of the task, not the org chart that built
the feature — a common failure mode is a sitemap that mirrors internal team
boundaries instead of user intent.

**4. Fix hierarchy depth deliberately.** A flatter structure with more items per
level is generally easier to navigate than a deep structure with few items per
level, but breadth without limit becomes its own failure — aim for a hierarchy a
user can predict, checking that no top-level category hides a disproportionate
share of the product's functionality three levels deep.

**5. Assign navigation labels distinct from internal names.** Internal
feature/project names rarely match how users describe the same thing — label each
node in the sitemap with user-facing language, and note the internal name
separately so engineering and content mapping stays traceable.

**6. Flag structural defects explicitly:**
   - **Orphans** — pages/features with no path leading to them from primary
     navigation.
   - **Duplicates** — the same content or function reachable via two inconsistent
     paths, with no canonical one declared.
   - **Mislabeled nodes** — a label that does not match what users call the
     grouped content (a red flag if card-sort data contradicts the current label).
   - **Overloaded nodes** — a single navigation entry hiding a disproportionate
     share of functionality, a likely future navigation bottleneck.

**7. Output the sitemap as a structured hierarchy** (tree or table: level, label,
internal name, audience, flags) rather than prose — it needs to be a reference
artifact, not a narrative.

## Checklist / quality gate
- Every existing page/feature from the inventory appears somewhere in the final
  sitemap, or is explicitly marked deprecated/removed — nothing silently vanishes.
- Groupings trace to either card-sort evidence or a stated user-mental-model
  rationale, not an unstated internal org structure.
- Every navigation label is checked against user-facing language, not just carried
  over from the internal feature name.
- Orphaned paths, duplicate paths, and overloaded nodes are each listed as their
  own flagged category, not buried in general notes.
- Hierarchy depth is stated and justified (why this many levels, why this grouping
  size) rather than left as an unexamined default.

## References
- Standard information-architecture practice (card sorting, taxonomy design); no
  single canonical specification is cited here — cross-check against your card-sort
  tooling's methodology docs (e.g., open vs. closed sort conventions) when
  available.

## Composition
Consumes card-sort output from a UX-research skill when available. Feeds a
navigation redesign into `structure-design-critique` for review, and into
`run-heuristic-evaluation`'s "match between system and real world" / "consistency"
axes when auditing an existing, shipped navigation.
