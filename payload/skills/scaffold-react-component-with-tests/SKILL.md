---
name: scaffold-react-component-with-tests
description: Use when a new UI component, page, or view is requested in a React (or similar component-framework) codebase. Generates the component plus a colocated unit/RTL test, a story for the component-explorer tool in use, and an accessibility-attribute checklist, wired to the project's existing design tokens instead of hardcoded styles or colors. Triggers include "add a component", "build a new page", "create a <Widget>", a missing test file next to a new component, or a PR that introduces a component with no story or test.
---

# scaffold-react-component-with-tests

## Overview
Generates a new UI component as a complete, verifiable unit: the component itself, a
colocated test, a story, and prop/type definitions — in one pass, so nothing ships
untested or undocumented. Owns the "new component" moment, not ongoing component
maintenance.

## When to use
- A new component, page, or view is requested and no scaffold exists yet.
- A PR introduces a component file with no matching test or story file.
- A design hands off a component spec (Figma frame, spec doc) that needs a first
  implementation pass.
- Refactoring one large component into smaller ones, each needing its own scaffold.

## Workflow
1. **Confirm the shape before generating.** Resolve: functional vs. class (default
   functional with hooks unless the codebase is class-based), the props interface,
   whether it is presentational (no data fetching) or a container (owns fetching/state).
   A presentational component that reaches for `fetch`/`useQuery` directly is a smell —
   push data-fetching to a parent or a hook.
2. **Locate conventions before inventing them.** Grep the codebase for an existing
   component of similar shape (a list item, a form field, a modal) and match its file
   layout, naming, and import style exactly. Consistency with neighbors beats an
   agent's own preference every time.
3. **Generate in this order, verifying each layer compiles/lints before the next:**
   - Component file with a typed props interface (TypeScript unless the codebase is
     plain JS — see `convert-js-to-typescript` if it's mid-migration).
   - Style layer using existing design tokens (CSS variables, a theme object, or a
     styled-components/Tailwind config already in the repo) — never a hardcoded hex
     color, pixel value, or font stack that bypasses the token system.
   - Story file (Storybook, Ladle, or whatever the repo already runs) with at minimum
     a default state and one variant per meaningfully different prop combination
     (loading, empty, error, populated).
   - Unit/RTL test: render, query by accessible role/label (not by CSS class or
     `data-testid` unless no accessible query exists), assert the rendered output and
     any interaction behavior (click, keyboard, form submit).
4. **Attach an accessibility-attribute checklist inline**, not as an afterthought:
   semantic element choice (`<button>` not `<div onClick>`), `aria-label`/`aria-labelledby`
   where the visible text doesn't fully describe purpose, focus order, and a keyboard
   path for every mouse interaction. Hand off to `add-accessibility-audit-fixes` for a
   full axe-core pass once the component is wired into a real page.
5. **Wire, don't duplicate.** If a near-identical component already exists, prefer
   extending it with a prop over forking a new file — flag the duplication risk to the
   requester rather than silently choosing.

## Checklist / quality gate
- [ ] Component uses existing design tokens/theme — zero hardcoded colors, spacing, or
      typography values.
- [ ] Props are fully typed (or JSDoc-typed in a plain-JS repo) with no implicit `any`.
- [ ] A story exists covering default, loading/empty/error (if applicable), and at
      least one prop variant.
- [ ] A test exists that queries by accessible role/label and covers the primary
      interaction, and it passes.
- [ ] Every interactive element is reachable and operable by keyboard alone.
- [ ] Lint and type-check pass with no new suppressions introduced.

## References
- [Frontend Developer Roadmap](https://roadmap.sh/frontend)
- [12 In-Demand Front End Developer Skills — roadmap.sh](https://roadmap.sh/frontend/developer-skills)

## Composition
Feeds into `migrate-component-to-design-system` when scaffolding a replacement for a
legacy component. Hands off to `add-accessibility-audit-fixes` for a deeper a11y pass
once the component lands on a real page. Pairs with a generic unit-test-coverage skill
for the test-authoring conventions (arrange-act-assert, mocking boundaries) and with
`integrate-rest-api-client` when the component is a container that needs live data.
