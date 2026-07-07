---
name: flaky-test-triage
description: Use when a CI test suite shows intermittent, non-deterministic failures — a test that is red on one run and green on the next with no code change in between, a "just re-run it" pattern creeping into the team's habits, or a request to quarantine, fix, or delete an unreliable test. Applies a repeated-run reproduction step, a root-cause classification (timing/race condition, test-order dependence, shared environment state, external dependency), and a fix-vs-quarantine-vs-delete decision tree with an owner and deadline. Triggers include a flapping CI status check, a test passing locally but failing only in CI, or a growing "known flaky" list with no expiration date.
---

# flaky-test-triage

## Overview
Diagnoses and resolves non-deterministic test failures — tests that fail
intermittently with no corresponding code change — through reproduction,
root-cause classification, and a disciplined decision between fixing,
quarantining with a deadline, or deleting the test outright. Owns the
policy that keeps "known flaky" from becoming a permanent, ever-growing
exemption list that quietly erodes suite trust.

## When to use
- A CI status check flaps red/green across runs with no relevant code
  change between them.
- A test passes reliably on a developer's machine but fails intermittently
  only in CI.
- The team has started reflexively re-running a failed job instead of
  investigating it — a leading indicator that flake has already eroded
  trust in the suite.
- A "known flaky" or `@skip` list exists with no review date and no owner.

## Workflow
1. **Reproduce before diagnosing.** Run the suspect test repeatedly in
   isolation and under the same conditions CI uses (same OS, same
   parallelism, same seed data) — for example `--repeat-each 20` in
   Playwright, `pytest-repeat`, or `go test -count=50`. A test that fails
   0/50 in isolation but fails in the full suite points to shared-state
   contamination, not the test itself; capture that distinction, it changes
   the fix.
2. **Classify the root cause before choosing a remedy:**
   - **Timing / race condition** — an assertion runs before an async
     operation (animation, network response, database write) completes.
     Symptom: fails more often under load or in a slower CI runner.
   - **Test-order dependence** — the test assumes state left behind by a
     prior test (a database row, a global variable, a file on disk).
     Symptom: passes alone, fails only in full-suite or shuffled-order runs.
   - **Shared environment state** — parallel test workers collide on a
     port, a file, a database row, or an external rate limit. Symptom:
     flake rate scales with parallelism/worker count.
   - **External dependency flakiness** — a third-party API, a network call
     not under test control, or a non-deterministic clock/random value.
     Symptom: failure correlates with an external outage or a specific
     time-of-day/timezone boundary.
   - **Resource contention** — CI runner under-provisioned for the
     suite's actual CPU/memory/IO needs. Symptom: flake rate correlates
     with concurrent job count on shared runners, not with the test's own
     logic. If this is the cause, hand off to CI-runner-capacity ownership
     rather than treating it as a test bug.
3. **Apply the decision tree:**
   - **Fix now** — root cause is clear, cheap to correct (add a proper
     wait condition, isolate shared state, seed a fixed random value), and
     doesn't require redesigning the test. Default choice whenever
     possible; ship the fix in the same change that diagnosed it.
   - **Quarantine** — root cause is understood but the fix is non-trivial,
     or root cause is still unclear and the test is blocking unrelated
     work. Quarantine means: mark it explicitly (a `flaky`/`quarantine` tag
     or `test.fixme`, not a silent `skip`), open a tracking ticket, assign
     an owner, and set an expiration date. A quarantined test with no
     deadline is a deleted test that still costs CI time.
     Re-review at the deadline — reproduce again, decide fix or delete.
   - **Delete** — the test provides no reliable signal (has been flaky
     across multiple root-cause attempts), duplicates coverage that a more
     stable test already provides, or tests an implementation detail
     rather than a behavior worth guarding. Deleting a low-value flaky
     test is a legitimate outcome, not a failure to fix it.
4. **Track the suite's flake rate over time**, not just the current
   incident. A rising flake rate across the suite — even if each individual
   test looks like a one-off — is an early signal of infrastructure or
   test-isolation debt that needs its own remediation project.
5. **Never respond to flake by adding blanket retries without a root-cause
   note.** A retry can mask a real, intermittent product bug (a genuine
   race condition in the application, not just the test). Retries are
   acceptable as a stopgap only alongside a ticket, never as the permanent
   fix.

## Checklist / quality gate
- The failure was reproduced with a repeated-run count, and the result
  (reliable, order-dependent, or truly random) is recorded.
- A root-cause category is assigned with the specific evidence that
  supports it (not a guess).
- A decision — fix, quarantine, or delete — is made and, for quarantine,
  carries an owner and a deadline.
- Any quarantine tag is visible in CI output and in the suite's flake-rate
  tracking, not a silent skip that disappears from view.
- If the root cause is CI-runner resource contention rather than the test
  itself, the finding is routed to CI-capacity ownership instead of being
  treated as a test-code fix.

## References
- Flaky-test classification and quarantine practices are a well-established
  industry pattern documented across major test-engineering blogs and
  conference talks on large-scale CI reliability; verify current
  team/tooling-specific guidance (retry plugins, quarantine tagging
  conventions) before adopting a specific implementation.
- [roadmap.sh — QA Engineer](https://roadmap.sh/qa) — CI test-suite
  integration and flaky-test management as a core QA/SDET competency.

## Composition
Receives destabilized tests from `e2e-test-suite-authoring` and
`api-contract-test-authoring` as its primary intake. Hands infrastructure-
caused flake (runner capacity, queue contention) to CI-runner-capacity
ownership rather than treating it as a test-code problem. Wires quarantine
tags and retry policy through `ci-pipeline-authoring`. Feeds its flake-rate
trend back into `test-strategy-and-coverage-audit` as a suite-health signal
alongside pyramid balance and gap coverage.
