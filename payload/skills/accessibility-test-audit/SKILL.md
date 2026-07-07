---
name: accessibility-test-audit
description: Use when accessibility testing needs to be wired into a QA process or a CI pipeline rather than run as a one-off pass — an automated axe-core scan added to the test suite, a WCAG 2.2 AA checklist for what automated scanning cannot catch, or a manual keyboard-navigation and screen-reader test guide handed to a human reviewer. Triggers include "add accessibility tests to CI," a compliance deadline requiring ongoing WCAG evidence, an axe-core scan that needs a pass/fail gate in the pipeline, or a request to build a repeatable accessibility test process rather than a single audit report.
---

# accessibility-test-audit

## Overview
Builds a repeatable accessibility *test process* — an automated `axe-core`
scan wired into CI as a pass/fail gate, a WCAG 2.2 AA checklist covering
what automated scanning structurally cannot catch, and a manual
keyboard-navigation/screen-reader test guide for the human reviewer who
runs the parts a scanner can't. This is the QA/CI ownership angle: turning
accessibility into a suite that runs on every change, not a single point-in-
time review of one screen's contrast and ARIA.

## When to use
- Accessibility testing needs to become part of the regular CI/test
  process rather than a one-time pre-launch check.
- A WCAG compliance deadline requires ongoing, demonstrable evidence — not
  a single pass/fail snapshot.
- An `axe-core` (or equivalent automated) scan exists but isn't gating
  anything — failures are logged and ignored rather than blocking merge.
- A manual test pass (keyboard-only navigation, screen-reader walkthrough)
  needs a repeatable guide so it doesn't depend on one person's memory of
  what to check.

## Workflow
1. **Wire automated scanning into CI as a gate, not a report nobody
   reads.** Run `axe-core` (via a CI-integrated runner, or inside an
   existing Playwright/Cypress suite using an axe integration) against
   every page/route or component story on every relevant build. Fail the
   build on new violations; a scan that only logs findings without gating
   the pipeline gets ignored within a few sprints.
2. **Set the conformance target explicitly — WCAG 2.2 Level AA is the
   default baseline** for most compliance requirements (and is what
   automated scanners default to). Confirm whether a stricter (AAA) or
   narrower (specific success criteria only) target applies before
   building the checklist around the wrong bar.
3. **Draw the line between what automated scanning catches and what it
   structurally cannot**, and don't let a clean scan stand in for full
   compliance:
   - **Scanner catches reliably:** missing alt text, insufficient color
     contrast, missing form labels, invalid ARIA attribute usage, missing
     document language, empty links/buttons.
   - **Scanner cannot catch — needs the manual checklist:** whether alt
     text is *meaningful* (not just present), whether focus order matches
     visual/reading order, whether a custom widget's keyboard interaction
     matches the ARIA pattern it claims to implement, whether a
     screen-reader announcement actually communicates state changes (a
     toast, a loading spinner, a validation error), and whether the page
     works with the operating system's actual assistive tech rather than
     just satisfying rule-level checks.
4. **Build the manual test guide as an executable checklist a human
   reviewer can run without accessibility expertise:**
   - Keyboard-only pass: unplug the mouse conceptually — Tab through every
     interactive element in a logical order, confirm every action reachable
     by mouse is also reachable by keyboard, confirm no keyboard trap
     (focus that can enter a widget but never leave it), confirm a visible
     focus indicator at every stop.
   - Screen-reader pass: navigate the page with a screen reader (VoiceOver,
     NVDA, or the platform default) and confirm headings form a logical
     outline, form fields announce their label and current state, and
     dynamic content changes (errors, loading states, live updates) are
     actually announced rather than silently updating the DOM.
   - Zoom/reflow pass: verify the layout at 200% browser zoom and at
     narrow viewport widths doesn't clip content or lose functionality.
5. **Track violations by severity and route them, don't just log a
   count.** Blocking (keyboard trap, missing form label on a required
   field, contrast failure on primary CTA text) gates the release. Non-
   blocking but tracked (minor contrast issue on decorative text) gets a
   ticket with a deadline. Route confirmed violations needing a code fix to
   an accessibility-remediation skill rather than fixing ad hoc inside the
   audit itself.
6. **Re-run the full process (automated + manual) on a cadence and on every
   major UI change**, not only before a compliance deadline — regressions
   creep back in the same way test coverage does elsewhere.

## Checklist / quality gate
- An automated `axe-core` (or equivalent) scan runs in CI and gates the
  build on new violations.
- The conformance target (WCAG 2.2 AA by default) is stated explicitly,
  not assumed.
- A manual checklist exists covering keyboard navigation, screen-reader
  announcement, and zoom/reflow — the categories automated scanning cannot
  reliably verify.
- Violations are triaged by severity with blocking vs. tracked-with-
  deadline clearly separated.
- The process re-runs on a defined cadence and on major UI changes, not
  only ahead of a compliance deadline.

## References
- [roadmap.sh — QA Engineer](https://roadmap.sh/qa) — accessibility
  testing named as a core QA testing type.
- [axe-core](https://github.com/dequelabs/axe-core) — the standard
  automated accessibility-scanning engine most CI integrations wrap.
- [Web Content Accessibility Guidelines (WCAG) 2.2](https://www.w3.org/TR/WCAG22/) — the conformance standard (Level AA is the common compliance baseline).

## Composition
Distinct from a design-side accessibility skill that runs a point-in-time
contrast/keyboard/ARIA pass on a single screen or component — this skill
owns turning that kind of check into a recurring, CI-gated test process
across the whole application. Hands confirmed violations needing a code
fix to an accessibility-remediation skill rather than fixing them here.
Wires its CI gate through `ci-pipeline-authoring`, is scoped alongside the
rest of the suite by `test-strategy-and-coverage-audit`, and can share a
test run with `e2e-test-suite-authoring` when the same Playwright/Cypress
suite already navigates the flow under audit.
