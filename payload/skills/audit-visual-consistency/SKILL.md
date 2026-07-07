---
name: audit-visual-consistency
description: Use when a growing product surface needs a check for visual drift from its documented style guide or design tokens — off-palette colors, inconsistent spacing, mismatched corner radii, or divergent shadow/elevation values creeping in across screens or components. Triggers include "visual consistency audit," "style-guide drift," "off-brand colors," a design system with multiple teams contributing, or a request to compare live screens against the source-of-truth tokens.
---

# audit-visual-consistency

## Overview
Compares a set of screens, components, or a live product surface against
its documented style guide or design-token source of truth, and flags
deviations — off-palette colors, spacing that doesn't map to a token,
inconsistent corner radii, mismatched shadows — with severity and the
nearest-compliant token to fix each one.

## When to use
- A product has grown across multiple teams or a long timeline and
  visual drift is suspected but not yet quantified.
- A design system exists but consuming teams have been overriding it with
  one-off values, and the scale of the problem needs measuring before a
  cleanup sprint is scoped.
- A rebrand or token migration needs a "how much still points at the old
  values" baseline before and after.
- A PR review flags a hardcoded color/spacing value and the question is
  whether it's an isolated slip or part of a wider pattern.

## Workflow

### 1. Establish the source of truth
This audit is only as good as its baseline — confirm what "correct" means
before flagging anything:
- A design-token file (see `design-tokens`) is the strongest baseline —
  every color, spacing, radius, and shadow value should trace back to a
  token.
- Absent a token file, a documented style guide (a style-guide doc, a
  Figma library, a `theme.ts`/`tokens.css` file) is the fallback baseline.
- If neither exists, this audit cannot run in "check against a standard"
  mode — pivot instead to a straight inventory: "here are the N distinct
  values in use, cluster them yourself" — and flag the missing source of
  truth as the real finding.

### 2. Inventory actual values in use
Depending on what's available:
- **Live surface**: pull computed styles via browser automation or a CSS
  extraction pass — colors, `padding`/`margin`, `border-radius`,
  `box-shadow`, `font-size` — across the screens or components in scope.
- **Design files**: extract fill colors, spacing between elements, and
  corner-radius values from the design tool's layer inspector or export.
- **Codebase**: grep for hex/`rgb()` literals, raw `px` spacing values, and
  `border-radius` declarations that bypass the token/theme system.

### 3. Diff against the baseline
For each extracted value, check whether it resolves to a defined token or
documented style-guide value:
- **Exact match** — compliant, no finding.
- **Near match** (e.g., `#3B82F2` vs. the token's `#3B82F6`, or `15px` vs.
  a `16px` spacing token) — almost always an accidental slip, not an
  intentional exception; flag with high confidence and the nearest token.
- **No match, but semantically plausible** (a genuinely new spacing need)
  — flag as a "candidate for a new token" rather than an error, and route
  it to `design-tokens` for a taxonomy decision rather than silently
  correcting it.
- **No match, arbitrary** (a color or spacing with no discernible reason)
  — flag as drift, highest-priority fix.

### 4. Score severity
Not every deviation is equal — rank by user-visible impact and blast
radius:
- **High** — brand colors off-palette in a frequently-seen surface, or a
  contrast-relevant color drift that risks an accessibility regression
  (hand off to `accessibility-audit` if so).
- **Medium** — spacing/radius drift visible on close inspection but not
  jarring; inconsistency between otherwise-similar components.
- **Low** — a single isolated instance, low-traffic surface, or a
  difference plausibly intentional (e.g., a marketing page's deliberate
  visual departure from product UI).

### 5. Report with the fix, not just the flag
Every finding names: the location (screen/component/selector), the actual
value found, the nearest-compliant token, and the severity. A report that
says "spacing is inconsistent" without a token to converge on is not
actionable — always resolve to a specific fix.

## Checklist / quality gate
- The baseline (token file or style guide) used for comparison is named
  explicitly in the report — never audit against an implied standard.
- Every finding cites a specific location, not a vague "somewhere in the
  app."
- Every finding proposes the nearest-compliant token or value — not just
  "this is off."
- Findings are severity-ranked, not presented as one undifferentiated
  list.
- Values that don't match any token but look like a legitimate new need
  are routed as "candidate for a new token," not silently corrected or
  silently ignored.
- If no source of truth exists, the report says so plainly instead of
  inventing an implicit standard to audit against.

## References
- UI-kit foundation and style-guide governance practice:
  https://www.setproduct.com/blog/how-to-design-a-ui-kit-foundation

## Composition
Depends on `design-tokens` for its baseline — run that skill first if no
token source of truth exists yet. Hands accessibility-relevant color
drift to `accessibility-audit`. Feeds `generate-component-changelog` when
a cleanup pass results in components moving onto corrected token values.
