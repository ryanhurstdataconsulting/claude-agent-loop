---
name: add-accessibility-audit-fixes
description: Use when a WCAG/a11y compliance request comes in, an automated accessibility test (axe-core, Lighthouse a11y, pa11y) fails, or a screen-reader/keyboard-only bug report is filed. Triages the scan output by severity, applies the correct ARIA or semantic-HTML pattern for the failing rule, and verifies the fix with a keyboard-navigation and screen-reader pass. Triggers include "make this accessible", an axe-core violation in CI, a failed WCAG audit, or a bug report describing a keyboard trap, missing focus indicator, or unlabeled control.
---

# add-accessibility-audit-fixes

## Overview
Triages and fixes accessibility violations from an automated scan or a manual report,
using the correct semantic-HTML or ARIA pattern for each rule, and verifies the fix by
actually operating the page with a keyboard and a screen reader — not just re-running
the scanner. Owns the fix-and-verify loop for a known violation set, not visual design
or full usability testing with assistive-technology users.

## When to use
- An axe-core, Lighthouse, or pa11y scan fails in CI or a local run.
- A WCAG compliance audit (2.1 or 2.2, Level AA is the common bar) is requested ahead
  of a release or a legal/compliance deadline.
- A bug report describes a keyboard trap, an unreachable control, a missing or
  incorrect focus indicator, an unlabeled form field, or a screen-reader
  mispronunciation/silence.
- A new component (see `scaffold-react-component-with-tests`) needs a deeper a11y pass
  once it is wired into a real page with real content.

## Workflow
1. **Run the automated scan first** (axe-core via `@axe-core/react`,
   `@axe-core/playwright`, or the browser extension) and triage by impact: `critical`
   and `serious` block a release; `moderate` and `minor` are tracked but not
   necessarily blocking. Automated scanners catch roughly a third of WCAG failures —
   treat a clean scan as a floor, not proof of compliance.
2. **Map each violation to the correct fix pattern**, don't just silence the rule:
   - **Missing accessible name** (button/link/input with no discernible text) → add
     visible text, `aria-label`, or `aria-labelledby` — prefer visible text first.
   - **Non-semantic interactive element** (`<div onClick>`, `<span>` acting as a
     button) → replace with the native element (`<button>`, `<a href>`) so keyboard
     operability and role come for free; only add `role`/`tabindex`/key handlers by
     hand when the native element genuinely cannot be used.
   - **Color-contrast failure** → check against WCAG AA thresholds (4.5:1 normal text,
     3:1 large text/UI components) and adjust the token, not just the one instance —
     a contrast failure is usually systemic to a color pair, not a one-off.
   - **Missing form label** → associate with `<label for>`/`id` or wrap the input;
     placeholder text is not a substitute for a label.
   - **Focus not visible or focus order wrong** → never remove a focus outline without
     replacing it with an equally visible custom one; fix DOM/tab order rather than
     patching with a high `tabindex`.
   - **Missing landmark/heading structure** → add `<main>`, `<nav>`, one `<h1>` per
     page, and a logical, non-skipping heading hierarchy.
   - **Dynamic content not announced** → wrap live-updating regions (toasts,
     validation errors, loading states) in an appropriate `aria-live` region
     (`polite` for most cases, `assertive` only for urgent interrupts).
3. **Verify by operating the page, not by re-running the scanner alone:**
   - Tab through the entire interactive surface using only the keyboard — every
     control must be reachable, operable (Enter/Space/arrow keys as appropriate), and
     show a visible focus indicator at every step, with no trap.
   - Spot-check with a screen reader (VoiceOver on macOS, NVDA on Windows, or a
     browser extension) on at least the changed region — confirm names, roles, and
     states are announced correctly.
4. **Re-run the automated scan** to confirm the flagged violations are cleared and no
   new ones were introduced, then close the loop with the manual verification above —
   automated-clean plus manually-operable is the actual bar, not either alone.

## Checklist / quality gate
- [ ] Every `critical`/`serious` automated-scan violation is resolved with the correct
      semantic or ARIA pattern, not a suppression.
- [ ] Every interactive control is reachable and operable by keyboard alone, with a
      visible focus indicator.
- [ ] Color-contrast fixes were applied at the token level where the failure is
      systemic, not patched per instance.
- [ ] A screen-reader spot check was performed on the changed region and controls
      announce correctly.
- [ ] The automated scan was re-run after the fix and shows no regressions.

## References
- [Frontend Developer Roadmap](https://roadmap.sh/frontend)

## Composition
Pairs with `scaffold-react-component-with-tests` (new components should carry the
accessibility checklist from the start) and `migrate-component-to-design-system`
(confirm a migration doesn't regress semantics). Hands its fix list to a QA/accessibility
test-audit skill for ongoing regression coverage once the initial fixes land.
