---
name: write-unit-tests-with-coverage-target
description: Use whenever a code change lands without accompanying tests, a coverage report shows a module or diff below a target threshold, or a task explicitly asks to "add tests" or "hit N% coverage" for a file, function, or pull request. Triggers include a CI coverage-gate failure, a code-review comment asking for test coverage, a new function with no corresponding test file, or a request to backfill tests for legacy code. Framework-agnostic across Jest/React Testing Library, pytest, JUnit, XCTest, and embedded frameworks like Unity or CppUTest — the workflow is the same even though the tooling differs.
---

# write-unit-tests-with-coverage-target

## Overview
Writes unit tests toward a specific coverage target using an
arrange-act-assert structure, prioritizing coverage gaps by risk rather than
chasing the percentage line-by-line. It owns turning a coverage report into a
prioritized, properly mocked, non-flaky test suite — not just the mechanical
act of writing assertions.

## When to use
- A CI coverage gate blocks a merge because a diff or module falls below the
  target threshold.
- A code reviewer asks for tests before approving a change.
- A new function, class, or module has no corresponding test file.
- Legacy code needs a backfilled safety net before a refactor.

## Workflow

**1. Establish the target and the baseline.** Run the project's real coverage
tool (`--coverage`, `pytest --cov`, a JaCoCo report, or the platform
equivalent) to get an actual number before writing anything. Never estimate
coverage by eye.

**2. Read the gap list, not just the top-line percentage.** Sort gaps by
risk, not by ease. Uncovered branches in error-handling and edge-case code
(empty input, boundary values, failure paths) outrank uncovered getters,
setters, and generated boilerplate.

**3. For each gap, write one test per behavior using arrange-act-assert:**
- **Arrange** — construct the minimal fixture or state needed. Avoid shared
  mutable global fixtures that couple tests together.
- **Act** — call exactly the unit under test.
- **Assert** — check the outcome and, where relevant, that no unintended
  side effect occurred.

**4. Decide the mocking boundary deliberately, not by default.** Mock at the
edge of the unit under test — network, filesystem, database, clock, random —
not its internal collaborators just to isolate lines. Mocking internals
produces a test that passes while the real integration is broken. If a test
needs three or more mocks to run, treat that as a signal the unit's
responsibilities should be split, not a signal to add a fourth mock.

**5. Chase gap closure, not the percentage.** A test that executes a line
without asserting a meaningful outcome raises coverage and adds no
protection — this is the single most common way a coverage target gets
gamed. Verify every new test actually protects something by briefly breaking
the logic it covers and confirming the test fails, then reverting the break.

**6. Re-run the full suite, not just the new tests,** to catch newly
introduced flakiness or shared-state collisions between tests.

**7. Re-run coverage and compare against the target from step 1.** If still
short, return to step 2's gap list rather than padding existing tests with
redundant assertions.

## Checklist / quality gate
- [ ] Coverage measured with the project's real tool before and after, not
      estimated
- [ ] Gaps prioritized by risk (error paths, edge cases) before ease
- [ ] Every new test follows arrange-act-assert with one behavior per test
- [ ] Mocking boundary is the unit's external edge, not its internal
      collaborators
- [ ] Each new test verified to fail when the covered logic is intentionally
      broken
- [ ] Full suite passes with no new flakiness, not just the new tests
- [ ] Final coverage meets or exceeds the agreed target, or the shortfall is
      explained

## Gotchas
- A 100% target is rarely the right one. Untestable glue code (framework
  wiring, trivial delegation) inflates the denominator with no safety
  benefit — agree on a target per module type (business logic higher,
  wiring code exempt) rather than one number for an entire codebase.
- Coverage tools report line and branch execution, not correctness. A suite
  can hit 100% and still miss every assertion that matters — step 5's
  break-it-and-confirm-it-fails check is what actually verifies protection.
- A flaky test (time-dependent, order-dependent, network-dependent) is worse
  than no test at all — it trains reviewers to ignore CI failures. Mock the
  clock and the network explicitly; never leave a raw sleep call as a
  flakiness workaround.

## References
- [Frontend Developer Roadmap](https://roadmap.sh/frontend)
- [Backend Developer Roadmap](https://roadmap.sh/backend)
- [Full Stack Developer Roadmap](https://roadmap.sh/full-stack)

## Composition
Consumed by `scaffold-full-feature-slice` at every layer of a new slice, and
by any scaffolding skill (component, endpoint, mobile screen) that generates
code alongside its tests. Pairs with an end-to-end test-authoring skill for
coverage above the unit level, and with a CI pipeline-authoring skill to wire
the coverage gate into the build.
