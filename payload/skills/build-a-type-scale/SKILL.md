---
name: build-a-type-scale
description: Use when a product needs a consistent typographic scale defined or audited — sizes, weights, and line-heights mapped to semantic roles like display, heading, body, and caption. Triggers include "type scale," "typographic scale," "modular scale," "font-size ramp," inconsistent heading sizes across screens, or a request to check line-height and readability against accessibility norms.
---

# build-a-type-scale

## Overview
Derives a modular typographic scale from a base size and ratio, maps each
step to a semantic role, and checks the result against readability and
accessibility norms. Also audits an existing, organically-grown set of font
sizes for consolidation back onto a defined scale.

## When to use
- A product has no defined type scale and headings/body text sizes have
  been picked ad hoc per screen.
- A brand spec gives a base font size and needs the full scale (display
  down to caption) derived from it.
- An existing codebase has too many distinct font-size values in use (a
  common smell: 15+ distinct sizes where 6–8 would cover every real need)
  and needs consolidation.
- Line-height or letter-spacing needs a check against readability
  guidance before a type system ships.

## Workflow

### 1. Pick the base size and ratio
- **Base size** — almost always 16px (1rem) for body text; this is the
  browser default and keeps `rem`-based scaling predictable. Deviate only
  with an explicit reason (a data-dense dashboard product sometimes bases
  at 14px).
- **Ratio** — a modular scale multiplies the base by a fixed ratio per
  step. Common choices, smallest steps to largest jumps:
  - **1.125 (Major Second)** — subtle, good for dense UI with many text
    levels.
  - **1.25 (Major Third)** — a common, balanced default for product UI.
  - **1.333 (Perfect Fourth)** — more dramatic contrast, suits
    marketing/editorial surfaces.
  - **1.5 (Perfect Fifth) / 1.618 (Golden Ratio)** — large jumps, best for
    a small number of display/heading roles, not a dense scale.
  Fewer, larger jumps read as more "designed"; more, smaller steps give
  finer control but risk sizes becoming indistinguishable at a glance.

### 2. Generate the scale
Multiply outward from the base in both directions (up for headings, down
for captions/labels):

```
step -1 (caption):  base / ratio        e.g. 16 / 1.25 = 12.8 → 13px
step  0 (body):      base               e.g. 16px
step  1 (h4/small):   base × ratio       e.g. 16 × 1.25 = 20px
step  2 (h3):         base × ratio²      e.g. 25px
step  3 (h2):         base × ratio³      e.g. 31px
step  4 (h1):         base × ratio⁴      e.g. 39px
step  5 (display):    base × ratio⁵      e.g. 49px
```
Round to clean pixel values a design tool can render crisply (avoid
sub-pixel fractions in the shipped tokens; keep the exact math available
for regenerating the scale later if the ratio or base changes).

### 3. Map steps to semantic roles
Never ship raw step numbers to consumers — map each to a role so the scale
reads as intent, not arithmetic: `display`, `h1`–`h4` (or `heading-xl`
through `heading-sm`), `body-lg`, `body`, `body-sm`, `caption`, `label`.
Some roles may intentionally share a size (e.g., `h4` and `body-lg`) —
that's fine; the role name still carries distinct semantic and styling
intent (weight, letter-spacing) even at an equal size.

### 4. Set line-height per role, not globally
A single global line-height is a common mistake — larger text needs
*tighter* relative line-height, smaller text needs *looser*:
- Display/large headings: 1.1–1.2×.
- Body headings (h3–h4): 1.25–1.35×.
- Body text: 1.5× minimum for sustained reading (WCAG 1.4.8 recommends
  1.5× line spacing for body text as a best practice for readability).
- Captions/labels: 1.3–1.4× (short strings tolerate tighter spacing).

### 5. Check against accessibility norms
- Body text should not go below **16px equivalent** (1rem) for primary
  reading content — smaller is acceptable for secondary/caption text but
  should be a deliberate exception, not the default.
- Users must be able to resize text up to 200% without loss of content or
  function (WCAG 1.4.4) — verify the scale is built in relative units
  (`rem`/`em`), not fixed `px`, so browser zoom and OS text-size settings
  work.
- Line length at body size should sit roughly in the 45–75-character range
  per line for readability — flag layouts that let body text run wider
  unconstrained.

### 6. Audit mode (existing scale)
When auditing rather than authoring fresh:
1. Inventory every distinct font-size value in use across the surface.
2. Cluster near-duplicates (14px vs 15px vs 16px used for the same
   apparent role) and propose which one becomes canonical.
3. Map each surviving value onto a semantic role.
4. Produce a before/after count ("23 distinct sizes → 8 roles") and a
   migration list of which screens/components need updating.

## Checklist / quality gate
- Every scale step maps to a named semantic role — no raw numeric steps
  shipped to consumers.
- Line-height is set per role, not one flat value across all sizes.
- Body text line-height is at least 1.5× and uses relative units.
- No role sits below a 16px-equivalent for primary reading text without an
  explicit, noted exception.
- The scale is expressed in `rem`/`em` (or the project's equivalent
  relative unit), not hardcoded `px`, so it supports user text resizing.
- An audit run produces a concrete before/after count and a migration
  list, not just "this is inconsistent."

## References
- Modular-scale typography practice is well established across the design
  community; no single canonical specification governs it — this workflow
  follows common product-design practice (base + ratio → semantic roles).
- WCAG success criteria for text spacing (1.4.8) and resize-text (1.4.4)
  inform the line-height and unit guidance above — see the
  `accessibility-audit` skill's WCAG references for the full checklist.

## Composition
Feeds `design-tokens` — the derived scale's sizes, weights, and
line-heights become the typography token tier. Pairs with
`accessibility-audit` for the resize/contrast checks and with
`audit-visual-consistency` when auditing an existing, drifted set of font
sizes across a live product surface.
