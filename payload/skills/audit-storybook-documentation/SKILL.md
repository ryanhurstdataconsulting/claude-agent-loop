---
name: audit-storybook-documentation
description: Use when a component library's Storybook (or equivalent living style guide such as zeroheight) needs a completeness and consistency check across entries. Triggers include "Storybook audit," "component docs coverage," "missing usage guidelines," "which components lack accessibility notes," or a design system where some components are well-documented and others are bare code with no story.
---

# audit-storybook-documentation

## Overview
Checks every component entry in a Storybook (or equivalent documentation
site) against a fixed completeness checklist — variants, usage rules, a
code snippet, and accessibility notes — and produces a coverage report
that names exactly which components are missing what.

## When to use
- A design system's Storybook has grown organically and documentation
  quality is inconsistent — some components are thorough, others are a
  bare render with no explanation.
- Before a design-system release, to confirm new or changed components
  meet the documentation bar.
- A team onboarding new engineers or designers keeps hitting components
  with no usage guidance and needs the gaps quantified before triaging a
  fix.
- A migration from one documentation tool to another (e.g., Storybook to
  zeroheight, or consolidating multiple Storybook instances) needs a
  before-state inventory.

## Workflow

### 1. Define the completeness checklist
Confirm the project's own bar if one exists; otherwise use this baseline,
adapted per component type (not every component needs every section — a
purely presentational component may not need an interaction-states
section):

1. **Overview** — one or two sentences on what the component is for and
   when to use it (versus a similar component, if ambiguity exists).
2. **Variants** — every visual/behavioral variant represented as a story
   (e.g., primary/secondary/danger for a Button; not just the default).
3. **States** — interactive states covered where applicable: default,
   hover, focus, active, disabled, loading, error.
4. **Usage guidelines** — do/don't guidance, not just a visual render.
5. **Code snippet** — a copy-pasteable usage example with realistic props,
   not a bare `<Component />`.
6. **Props/API reference** — every public prop documented with type,
   default, and description (auto-generated from types/PropTypes counts,
   but confirm it renders correctly and descriptions aren't empty).
7. **Accessibility notes** — keyboard behavior, ARIA roles applied, and
   any consumer responsibility (e.g., "you must supply an accessible
   label via the `label` prop").
8. **Related components** — cross-links to components this one is
   commonly paired with or confused with.

### 2. Walk every component entry
For each component in the library, check off each checklist item present
or absent. Do not infer completeness from the component's apparent
maturity ("this looks important, it's probably documented") — verify
directly against the rendered docs page.

### 3. Score and categorize gaps
- **Missing entirely** — a component exists in code with no Storybook
  story at all. Highest priority; nothing to iterate on yet.
- **Stub** — a story exists (renders the component) but has none of the
  narrative sections (usage, accessibility, etc.). Second priority.
- **Partial** — some sections present, others missing. Report the
  specific missing sections, not just "incomplete."
- **Complete** — all applicable checklist items present.

### 4. Produce the coverage report
One row per component, checklist items as columns, with a rollup: total
components, percent complete, and a ranked list of the highest-traffic or
highest-risk components still missing documentation (a component used
across many products missing accessibility notes outranks a rarely-used
one missing a related-components link).

## Checklist / quality gate
- Every component in the library appears in the report — none silently
  skipped because it "looked fine."
- Every gap names the specific missing section(s), not a blanket
  "incomplete."
- The report distinguishes missing-entirely, stub, and partial states.
- A rollup percentage and a prioritized fix list accompany the raw table
  — a report that's just a wall of checkmarks doesn't tell anyone what to
  do next.
- Accessibility-notes gaps are flagged with the same or higher severity as
  missing usage guidelines, not treated as optional.

## References
- Storybook documentation examples and pattern library:
  https://www.supernova.io/blog/top-storybook-documentation-examples-and-the-lessons-you-can-learn
- Design-system documentation best practices:
  https://www.magicpatterns.com/blog/design-system-documentation

## Composition
Feeds `draft-contribution-model`'s Document stage exit criteria. Hands
accessibility-notes gaps to `accessibility-audit` for the underlying
content. Pairs with `generate-component-changelog` — a release note for a
new component should not ship until this audit confirms its docs entry is
complete.
