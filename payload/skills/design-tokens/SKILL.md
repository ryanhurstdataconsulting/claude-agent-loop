---
name: design-tokens
description: Use when a brand or style spec (colors, type scale, spacing, radii) needs to become a structured, tool-portable design-token file, or when an existing token set needs its taxonomy organized into core/semantic/component tiers. Triggers include "design tokens," "DTCG," "Style Dictionary," "token taxonomy," "$value/$type," a hard-coded hex value that should be a token, or a request to make a style guide consumable by both Figma and code.
---

# design-tokens

## Overview
Turns a style specification into a structured, DTCG-spec-compliant token
file, organized into the standard three-tier taxonomy (core → semantic →
component), with a naming convention and a deprecation path for legacy
hard-coded values. Owns both authoring new tokens and organizing an
existing flat token list into that taxonomy.

## When to use
- A brand kit (colors, type scale, spacing, radii, shadows) needs to become
  a portable JSON token file consumable by design tools and code.
- An existing token set is a flat, ungoverned list and needs to be
  reorganized into core/semantic/component tiers.
- A codebase has hard-coded values (`#3B82F6`, `16px`) that should reference
  tokens instead, and needs a migration/deprecation plan.
- A team needs a naming convention so token names are self-documenting
  across platforms (web, iOS, Android) via a build tool such as Style
  Dictionary.

## Workflow

### 1. Establish the three-tier taxonomy
This is the load-bearing decision — get it right before generating any
JSON:

1. **Core (a.k.a. global/primitive) tokens** — raw values with no semantic
   meaning: `blue-500: #3B82F6`, `space-4: 16px`. Named by what they *are*.
2. **Semantic (a.k.a. alias) tokens** — reference core tokens by role:
   `color-action-primary: {blue-500}`, `space-inset-md: {space-4}`. Named by
   what they *mean*. This is the tier that should change when a brand
   refreshes — semantic names stay stable while their core references swap.
3. **Component tokens** — reference semantic tokens for a specific
   component: `button-primary-background: {color-action-primary}`. Named by
   *where they're used*.

Never let a component token reference a core token directly — that skips
the semantic layer that makes rebranding and dark-mode theming possible
without touching every component.

### 2. Elicit or extract values
- From a brand spec: pull colors, a base type size and scale ratio,
  spacing unit, radii, and shadow values.
- From an existing codebase: grep for hard-coded hex values, `px` values in
  spacing/margin/padding, and `border-radius` — these become migration
  candidates, not necessarily new tokens (many will collapse onto existing
  core values once compared).

### 3. Emit DTCG-compliant JSON
Use the W3C Design Tokens Community Group format — `$value` and `$type` are
the load-bearing keys; groups nest as plain objects:

```json
{
  "color": {
    "blue": {
      "500": { "$value": "#3B82F6", "$type": "color" }
    },
    "action": {
      "primary": { "$value": "{color.blue.500}", "$type": "color" }
    }
  },
  "space": {
    "4": { "$value": "16px", "$type": "dimension" }
  }
}
```

Reference other tokens with `{group.path.to.token}` syntax rather than
duplicating a literal value — a token file where every value is a literal
has defeated the point of tokens.

### 4. Validate before handoff
- Every semantic and component token resolves to a real core token (no
  broken references).
- No two core tokens hold the same value under different names (collapse
  duplicates — this is the most common source of drift).
- Naming convention is consistent and documented (a `category-property-
  variant-state` pattern, or whatever convention the project already uses
  — state it explicitly rather than leaving it implicit).
- A deprecation policy exists for any legacy hard-coded value being
  replaced: mark it deprecated, point to its replacement token, and set a
  removal target rather than deleting it outright in the same change.

### 5. Hand off for consumption
Note the intended build path (for example, Style Dictionary transforming
the DTCG source into platform-specific outputs — CSS custom properties,
iOS `.swift`, Android `.xml`) so the file lands in the format downstream
tooling expects, but do not assume a specific build tool is present —
confirm or default to plain DTCG JSON as the source of truth.

## Checklist / quality gate
- Every token has both `$value` and `$type` set.
- Three tiers are present and correctly layered: core tokens hold literals,
  semantic tokens reference core, component tokens reference semantic.
- No component token references a core token directly.
- No duplicate core values under different names.
- Naming convention is documented, not just consistent by accident.
- Legacy/hard-coded values being replaced have an explicit deprecation
  note, not a silent deletion.

## References
- W3C Design Tokens Community Group specification (DTCG format):
  https://www.designtokens.org/tr/drafts/format/
- Style Dictionary's DTCG guide: https://styledictionary.com/info/dtcg/
- Token-taxonomy and UI-kit foundation practice:
  https://www.setproduct.com/blog/how-to-design-a-ui-kit-foundation

## Composition
Feeds `build-a-type-scale` (the type scale's output sizes become tokens
here) and `accessibility-audit` (contrast failures often resolve by fixing
a core color token rather than a one-off value). Pairs with
`audit-visual-consistency`, which checks whether a live surface actually
uses these tokens instead of drifting back to hard-coded values, and with
`generate-component-changelog` when a token change is breaking and needs to
be communicated to consuming teams.
