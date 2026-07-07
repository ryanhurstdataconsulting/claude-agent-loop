---
name: test-strategy-and-coverage-audit
description: Use when a new project or feature needs a test plan before code is written, or an existing codebase needs an audit of what its test suite actually covers versus what it should. Checks test-pyramid balance (unit-vs-integration-vs-E2E ratio), applies risk-based prioritization against acceptance criteria, and produces a gap-analysis report naming untested critical paths. Triggers include "what's our test coverage strategy," a request to audit an existing suite, a coverage report that looks high but still missed a production bug, or a new feature spec that needs a test plan attached before implementation starts.
---

# test-strategy-and-coverage-audit

## Overview
Produces a test strategy — or an audit of an existing one — that answers
two questions a raw coverage percentage cannot: is the suite shaped right
(pyramid balance), and is it aimed at the right things (risk-based
prioritization against what the software is actually supposed to do). Sits
above the mechanical test-authoring skills as the planning layer that
decides where each is warranted.

## When to use
- A new project or feature is being scoped and needs a test plan before
  implementation starts, not bolted on after.
- An existing suite needs an audit — especially when a high coverage
  percentage still let a production bug through, a signal that coverage is
  measuring the wrong thing.
- The suite feels top-heavy or bottom-heavy (all E2E and no unit tests, or
  the reverse) and needs a structural read before adding more of either.
- A gap-analysis is requested naming specifically which critical paths lack
  coverage, for prioritization against a limited testing budget.

## Workflow
1. **Check the pyramid ratio first.** Count tests (or better, execution
   time and maintenance surface) by layer: unit, integration, end-to-end.
   A healthy suite is unit-heavy, with integration and E2E each covering a
   deliberately smaller slice — E2E tests are the slowest to run and the
   most expensive to maintain, so they should verify user journeys, not
   restate logic already covered at the unit layer. Flag two anti-patterns
   by name:
   - **Inverted pyramid / ice-cream cone** — heavy E2E, thin unit layer.
     Symptom: a slow, flaky CI run and long feedback cycles for a
     one-line logic bug.
   - **Hollow middle** — solid unit tests and solid E2E tests but no
     integration layer connecting them. Symptom: units pass, the full app
     passes in staging, but the seam between two services or modules
     still breaks in production.
2. **Build a risk-prioritization matrix against acceptance criteria, not
   against code structure.** For each feature or path, score likelihood of
   failure (complexity, change frequency, past bug history) against
   business impact (revenue path, data-loss risk, compliance requirement,
   blast radius). High-likelihood, high-impact paths get priority
   regardless of how easy or hard they are to test.
3. **Cross-reference coverage-tool output against the critical-path list,
   not the other way around.** A line/branch coverage report tells you
   what code executed during a test run; it does not tell you whether the
   test asserted anything meaningful, or whether the critical business
   path is actually represented. Treat coverage percentage as a floor
   signal (uncovered code is definitely a gap) rather than a ceiling signal
   (covered code is not automatically well-tested).
4. **Apply the testing-types taxonomy to name what's missing precisely** —
   functional, regression, smoke, sanity, exploratory, and user-acceptance
   testing each answer a different question. A gap report that says "needs
   more tests" is not actionable; a gap report that says "no regression
   coverage exists for the refund flow, and no exploratory pass has run
   against the new bulk-import feature" is.
5. **Produce a written test strategy or gap report with named owners.**
   The deliverable states: current pyramid shape, top N untested critical
   paths ranked by the risk matrix, and a recommendation for which
   authoring skill closes each gap (unit, contract, E2E, load,
   accessibility). Recommendations without an owner or a next skill to
   invoke don't get acted on.
6. **Re-run the audit on a cadence, not just once.** A suite's shape drifts
   as a codebase grows; a strategy written at project kickoff and never
   revisited stops matching the actual risk profile within a few release
   cycles.

## Checklist / quality gate
- Pyramid ratio is computed (by test count or execution time) and
  explicitly flagged as balanced, inverted, or hollow-middle.
- Every top-priority critical path from the risk matrix has a stated
  coverage status: covered, partially covered, or gap.
- The gap report names specific paths and the testing type missing (not a
  generic "add more tests").
- Each named gap recommends which authoring skill closes it.
- The strategy or audit has a stated owner and a re-review date.

## References
- [roadmap.sh — QA Engineer](https://roadmap.sh/qa) — testing-types
  taxonomy (functional, regression, smoke, sanity, exploratory,
  user-acceptance, unit, integration) underpinning the gap analysis.

## Composition
The planning layer that scopes `e2e-test-suite-authoring`,
`api-contract-test-authoring`, `load-performance-test-authoring`, and
`accessibility-test-audit` — run this first to decide where each is
warranted rather than defaulting to all of them everywhere. Consumes
acceptance criteria from a PRD or spec as the input to risk-based
prioritization. Shares its base-layer coverage view with
`write-unit-tests-with-coverage-target`, and receives flake-rate trend data
back from `flaky-test-triage` as an ongoing suite-health signal.
