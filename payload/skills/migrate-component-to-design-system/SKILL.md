---
name: migrate-component-to-design-system
description: Use when a legacy, ad hoc, or hardcoded-style component needs to move onto a shared design-system or design-token library. Maps old props, class names, and inline styles onto the new token/component API, runs a visual-regression check, and retires the old styles behind a feature flag rather than a hard cutover. Triggers include "migrate this to the design system", a design-tokens rollout, a deprecated component-library warning, or a component still using hex colors/pixel values after tokens were introduced elsewhere in the codebase.
---

# migrate-component-to-design-system

## Overview
Moves one component at a time from bespoke markup/styling onto a shared design-system
or token library, without a visual regression and without breaking every consumer at
once. Owns the migration mechanics — mapping, verification, staged rollout — not the
design-system's own token or component decisions.

## When to use
- A component still uses hardcoded hex colors, pixel spacing, or a bespoke class
  instead of the design-system's tokens or primitives.
- A design-system version bump deprecates a prop, class, or component the codebase
  still relies on.
- A rebrand or token-taxonomy change requires touching every consumer of an old style.
- A newly scaffolded component (see `scaffold-react-component-with-tests`) was built
  before a design-system existed and now needs to be retrofitted.

## Workflow
1. **Inventory before touching code.** List every prop, class name, and inline style
   the legacy component exposes, and find the design-system's nearest equivalent for
   each (a token, a primitive component, a utility class). Flag any legacy capability
   with *no* design-system equivalent — that is a design decision, not something to
   silently drop or approximate.
2. **Build a mapping table** (old → new) before editing: `color: #1a2b3c` →
   `var(--color-brand-primary)`, `<LegacyButton size="big">` → `<Button size="lg">`,
   and so on. Keep this table in the PR description — it is the reviewer's fastest
   path to confidence.
3. **Migrate behind a flag, not a hard swap.** Wrap the new implementation behind a
   feature flag, environment check, or a parallel component name (`ButtonV2`) so the
   old and new versions can run side by side until every call site is verified. A
   flag day-one avoids an all-or-nothing PR that is too risky to review.
4. **Run a visual-regression check before merging.** Prefer an existing
   screenshot-diff tool in the repo (Chromatic, Percy, Playwright's
   `toHaveScreenshot`) over eyeballing. Capture the component in every state exercised
   by its story file (see `scaffold-react-component-with-tests`) and diff old vs. new.
   Treat any unexplained pixel diff as a bug, not noise to suppress.
5. **Migrate call sites incrementally**, one consumer or one route at a time, each as
   its own commit — never a single sweeping find-and-replace across the whole
   codebase in one shot, since that makes a regression impossible to bisect.
6. **Deprecate, then delete.** Once every call site is migrated and verified in
   production for a full release cycle, mark the legacy component `@deprecated`,
   then remove it in a follow-up change — do not delete it in the same PR that
   introduces the replacement.

## Checklist / quality gate
- [ ] A full old-prop-to-new-token mapping table exists and is included in the PR.
- [ ] Every legacy capability with no direct design-system equivalent is flagged and
      explicitly resolved (approximated, dropped with sign-off, or the design system
      is extended) — not silently dropped.
- [ ] The new component sits behind a flag or a parallel name until fully verified.
- [ ] A visual-regression diff was run against every state in the story file, with
      zero unexplained diffs.
- [ ] Call sites were migrated incrementally, each in its own commit.
- [ ] The legacy component is marked deprecated, not deleted, until every consumer
      is confirmed migrated.

## References
- [Frontend Developer Roadmap](https://roadmap.sh/frontend)

## Composition
Downstream of `scaffold-react-component-with-tests` (the replacement component should
be scaffolded with its own story and test first). Pairs with an end-to-end or
visual-regression test-authoring skill for the screenshot-diff step, and with an
accessibility-audit skill to confirm the migration didn't regress semantics or
keyboard behavior along the way.
