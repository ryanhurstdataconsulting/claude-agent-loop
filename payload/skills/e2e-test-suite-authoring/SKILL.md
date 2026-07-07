---
name: e2e-test-suite-authoring
description: Use when a critical user journey lacks browser-level coverage, a new feature slice ships without end-to-end tests, or the task is phrased as "write E2E tests for this flow," "add Playwright coverage," or "test this checkout/signup/login path end to end." Builds Playwright-first (Cypress as a fallback in an existing Cypress repo) test suites with a Page Object Model, a role/data-testid selector strategy, an API-seeded fixture approach, and CI wiring with retries and parallel sharding. Triggers include a shipped feature with zero browser-level test coverage, a regression that only reproduces in a real browser, or a request to convert manual QA click-throughs into automated checks.
---

# e2e-test-suite-authoring

## Overview
Authors browser-level end-to-end tests that exercise a real user journey
through the running application — not a mocked component, the actual
rendered UI driving real (or realistically stubbed) network calls. Owns the
full path from framework choice through Page Object Model structuring,
fixture/seed-data strategy, flake-mitigation, and CI wiring with retries and
sharding.

## When to use
- A new critical user journey (signup, checkout, search-to-purchase,
  onboarding) ships with no browser-level test.
- A regression only reproduces in a real browser (timing, layout, a
  third-party script) and needs a repeatable automated check.
- Manual QA click-throughs are being converted into an automated suite.
- A feature slice is scaffolded and needs its top-of-pyramid coverage layer
  alongside the unit and integration tests underneath it.

## Workflow
1. **Pick the framework — Playwright by default.** Playwright is the current
   default choice for new suites: auto-waiting, multi-browser support
   (Chromium, Firefox, WebKit) from one API, built-in trace/video capture,
   and native parallel sharding. Use Cypress only when the repository
   already has an established Cypress suite — do not introduce a second E2E
   framework into a codebase that has one working.
2. **Prioritize journeys by business risk, not by what is easiest to
   automate.** Cover the paths where a silent break costs the most: auth,
   checkout/payment, data-loss-risk actions (delete, submit), and any flow a
   support ticket has already been filed against.
3. **Structure with the Page Object Model (or a component-object variant for
   SPA UIs).** Each page or major component gets an object exposing
   locators and actions (`login(email, password)`, `addToCart(itemId)`);
   test files read as a sequence of user actions and assertions, never raw
   selectors. This is what keeps a UI redesign from requiring a rewrite of
   every test file.
4. **Use a selector-priority ladder — resilient before convenient:**
   - `getByRole` / accessible name (mirrors what a screen reader and a real
     user perceive) — first choice.
   - `data-testid` (or an equivalent stable test hook) — second choice,
     when no accessible role/name distinguishes the element.
   - CSS class or DOM structure — last resort only; these break on any
     styling refactor and should be flagged for a `data-testid` follow-up.
   - Never select on visible text alone in a UI with copy under active
     iteration or localization.
5. **Seed test data through the API or a direct database fixture, not
   through the UI.** Driving five prior screens just to reach the screen
   under test multiplies flake surface and runtime for no coverage benefit.
   Reserve UI-driven setup for the one test that specifically verifies that
   flow.
6. **Apply the flake-mitigation checklist before merging any new test:**
   - Rely on Playwright's auto-waiting and web-first assertions
     (`expect(locator).toBeVisible()`) instead of arbitrary `sleep`/`wait`
     calls.
   - Stub or intercept third-party network calls (payment widgets, ad
     scripts, analytics beacons) that are non-deterministic or rate-limited.
   - Isolate tests with a fresh browser context (and fresh seed data) per
     test — no shared mutable state between tests in the same file.
   - Avoid order-dependent tests; each test must pass when run alone and in
     any order.
7. **Wire into CI with retries and sharding.** One retry on failure
   (`retries: 1` in CI, `0` locally so real bugs surface immediately),
   `trace: 'on-first-retry'` for post-mortem debugging, and parallel
   sharding across workers to keep wall-clock time flat as the suite grows.
   Capture screenshots and video on failure by default.
8. **Route destabilized tests, don't just re-run them.** A test that starts
   failing intermittently after merge is a triage problem, not a re-run
   problem — hand it to a flaky-test workflow rather than adding retries
   until it goes green.

## Checklist / quality gate
- Every new critical-journey test passes in isolation and in full-suite
  order, run twice back to back.
- No arbitrary `sleep`/fixed-delay waits remain in the diff.
- Selectors follow the role → `data-testid` → CSS priority ladder; no raw
  CSS selector on a testable interactive element without a documented
  reason.
- Test data is seeded via API/fixture, not multi-screen UI navigation,
  except for the one test verifying that navigation itself.
- CI config runs the suite with retries, sharding, and failure artifacts
  (trace/screenshot/video) enabled.
- No new test shares mutable state with another test in the same file.

## References
- [Playwright documentation](https://playwright.dev/docs/intro) — auto-waiting, locators, trace viewer, sharding.
- [Playwright best practices](https://playwright.dev/docs/best-practices) — selector strategy, test isolation.
- [roadmap.sh — QA Engineer](https://roadmap.sh/qa) — white/gray/black-box and end-to-end testing coverage in the broader QA skill set.
- [roadmap.sh — Full-Stack Developer](https://roadmap.sh/full-stack) — end-to-end testing as a full-stack delivery competency.

## Composition
Downstream of `test-strategy-and-coverage-audit`, which decides whether a
journey warrants E2E coverage versus a cheaper integration test. Sits above
`write-unit-tests-with-coverage-target` and `api-contract-test-authoring` in
the test pyramid — reach for those first for logic and contract coverage,
and reserve this skill for the user-facing journey itself. Feeds
`accessibility-test-audit` when the same flow needs a keyboard/screen-reader
pass alongside functional coverage. Hands off to `flaky-test-triage` the
moment a test destabilizes post-merge, and to `ci-pipeline-authoring` when
the suite needs its own pipeline stage rather than an ad hoc CI job.
