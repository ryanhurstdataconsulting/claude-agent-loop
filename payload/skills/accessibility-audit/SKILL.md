---
name: accessibility-audit
description: Use when a screen, component, or flow needs a WCAG accessibility pass before it ships — color-contrast ratios, keyboard navigation, focus order, and ARIA semantics. Triggers include "accessibility audit," "a11y check," "WCAG AA," "contrast ratio," "is this keyboard-accessible," a failing axe-core or Lighthouse accessibility score, a design handoff with color pairs to verify, or a component library that needs a pass/fail table per success criterion before release.
---

# accessibility-audit

## Overview
Runs a two-lane WCAG audit against a screen, component, or live interface:
a deterministic color-contrast check and a keyboard/focus/ARIA interaction
check. Produces one pass/fail table per WCAG success criterion with concrete
fixes, not a vague "improve accessibility" note.

## When to use
- A design spec or live UI needs a contrast pass before it ships (text on
  background, icon on background, UI-component borders).
- A flow needs a check for tab order, focus visibility, and screen-reader
  labeling before release.
- A component library needs a baseline accessibility gate added to CI.
- Someone reports "this isn't accessible" and the underlying success
  criterion needs to be identified, not just guessed at.
- A Lighthouse, axe-core, or similar automated scan flagged violations that
  need triage into fix-now versus false-positive.

## Workflow

### 1. Scope the audit
Confirm target: a static design spec (colors/type from a file or token set)
versus a live, interactive surface (needs a DOM or browser-automation pass
for focus/ARIA). Confirm the conformance target — WCAG 2.1 AA is the default
unless the requester states 2.2 or AAA.

### 2. Contrast lane (deterministic, always runs first — cheapest signal)
For every foreground/background pair in scope:
1. Extract the two colors (from design tokens, computed CSS, or a screenshot
   sample).
2. Compute the relative-luminance contrast ratio per the WCAG formula.
3. Apply the threshold by content type:
   - Normal text: **4.5:1** minimum (AA).
   - Large text (18pt+/24px+, or 14pt+/18.66px+ bold): **3:1** minimum.
   - UI components and graphical objects (borders, icons, focus indicators):
     **3:1** minimum against adjacent colors.
   - AAA tier (only if requested): 7:1 normal text, 4.5:1 large text.
4. For each failure, propose the nearest-compliant adjustment — darken or
   lighten in the same hue family before suggesting an unrelated color, so
   the fix stays on-brand.
5. Do not flag decorative or disabled-state elements — WCAG contrast
   requirements exempt inactive UI and pure decoration; note the exemption
   rather than silently skipping so the report stays auditable.

### 3. Interaction lane (keyboard, focus, ARIA)
Walk the flow against these checks, in this order — each layer assumes the
previous one passes, so fix top-down:
1. **Keyboard reachability** — every interactive element reachable via `Tab`
   / `Shift+Tab` alone, no mouse-only affordances.
2. **Focus order** — tab order follows visual/reading order (usually DOM
   order; flag any `tabindex` value greater than 0, which breaks natural
   order and is almost always a defect).
3. **Focus visibility** — a visible focus indicator on every focusable
   element, meeting the 3:1 non-text contrast rule against its background.
4. **Name, role, value** — every control exposes an accessible name (label,
   `aria-label`, or `aria-labelledby`), a correct role (native HTML element
   preferred over an ARIA role bolted onto a `div`), and, for stateful
   controls, a current value/state (`aria-expanded`, `aria-checked`, etc.).
5. **Error identification and instructions** — form errors announced to
   assistive tech (`aria-live`, `aria-describedby`) and not conveyed by
   color alone.
6. **No keyboard traps** — a user can tab into and back out of every widget
   (custom modals and menus are the usual offenders).

For a live surface, drive it with browser automation (or an axe-core /
Lighthouse pass) to pull the actual DOM and computed styles rather than
inferring from a screenshot.

### 4. Score and report
Produce one row per WCAG success criterion touched, in this shape:

| Criterion | Result | Location | Fix |
|---|---|---|---|
| 1.4.3 Contrast (Minimum) | Fail (3.8:1) | Primary button label | Darken text to `#1a1a2e` → 4.6:1 |
| 2.4.7 Focus Visible | Pass | — | — |
| 4.1.2 Name, Role, Value | Fail | Icon-only close button | Add `aria-label="Close dialog"` |

Separate **must-fix** (AA failures) from **should-fix** (AAA-tier or best
practice beyond the stated target) so the report doesn't block a ship on
non-blocking items.

## Checklist / quality gate
- Every foreground/background pair in scope has a computed ratio, not an
  eyeballed judgment.
- Every failure names the specific success criterion (for example, "1.4.3"
  or "2.4.7"), not a vague "contrast issue."
- Every failure includes a concrete fix (a hex value, an ARIA attribute, a
  `tabindex` correction) — not just "improve this."
- Decorative/disabled elements are noted as exempt, not silently dropped.
- The report distinguishes must-fix (stated conformance target) from
  should-fix (stretch/AAA) findings.
- For a live-surface audit, findings are traceable to a specific selector
  or component instance, not just "somewhere on this page."

## References
- WCAG 2.1/2.2 success criteria quick reference (official, filterable by
  level and category): https://www.w3.org/WAI/WCAG21/quickref/
- WebAIM Contrast Checker methodology and formula:
  https://webaim.org/resources/contrastchecker/
- Nielsen Norman Group / axe-core-style automated-audit practice (for the
  live-DOM interaction lane) — pair with an axe-core or Lighthouse
  accessibility run when the surface is live.

## Composition
Feeds `design-tokens` (a recurring contrast failure often means a token's
color value needs correcting at the source, not just the one instance) and
`audit-visual-consistency` (contrast drift is one flavor of visual drift).
Hands off to whatever CI/test-authoring skill the project uses for frontend
work when the fix needs a regression test added, not just a one-time patch.
