---
name: load-performance-test-authoring
description: Use when a service or endpoint needs load, stress, spike, or soak testing before launch, a capacity question needs empirical evidence rather than a guess, or the task is phrased as "load test this before we ship," "how many concurrent users can this handle," or "will this survive a traffic spike." Selects a tool (k6, Locust, Gatling) matched to the protocol under test, designs the scenario (smoke, load, stress, soak, spike), sets pass/fail thresholds tied to the service's SLO rather than an arbitrary number, and produces a results-to-report pipeline. Triggers include a pre-launch capacity gate, a past incident traced to unhandled load, or a request to validate a scaling change.
---

# load-performance-test-authoring

## Overview
Designs and runs load-testing scenarios that produce empirical, repeatable
evidence about a service's behavior under concurrent load — matching the
right tool to the protocol, the right scenario shape to the question being
asked, and grounding pass/fail thresholds in the service's actual SLO
rather than a number picked because it sounded reasonable.

## When to use
- A service is heading toward launch and needs a capacity gate before
  traffic arrives.
- An incident was traced to unhandled load (a traffic spike, a batch job,
  a retry storm) and the fix needs empirical proof it holds this time.
- A scaling change (new instance type, autoscaling policy, connection-pool
  resize, cache layer added) needs before/after evidence.
- A capacity-planning question ("how many concurrent users can this
  handle") has no answer better than a guess.

## Workflow
1. **Define the pass/fail threshold from the SLO before writing the
   scenario, not after seeing the results.** Pull the latency, error-rate,
   and availability targets from the service's stated SLO/error budget. A
   threshold invented after looking at the numbers is not a threshold, it's
   a rationalization. If no SLO exists yet, that's a prerequisite gap —
   define one first rather than testing against an arbitrary number.
2. **Match the tool to the protocol and team context:**
   - **k6** — scripting-first (JavaScript), strong for HTTP/REST, gRPC, and
     WebSocket, good CI/CD integration and cloud-run options. Default
     choice for most HTTP API load testing.
   - **Locust** — Python-based, models user behavior as classes/tasks
     rather than raw request scripts; a good fit when the team already
     thinks in Python and the scenario needs complex, stateful user
     journeys.
   - **Gatling** — JVM-based, strong for very high-throughput scenarios and
     teams already in a Java/Scala stack; richer built-in reporting than
     the other two out of the box.
   Pick based on protocol fit and what the team can maintain, not on
   novelty.
3. **Design the scenario to match the question being asked — these are not
   interchangeable:**
   - **Smoke test** — minimal load (1–5 virtual users), sanity-checks the
     script itself works before a real run.
   - **Load test** — expected peak traffic, sustained for a representative
     window; answers "does this hold up at normal-to-busy volume."
   - **Stress test** — ramps load past expected peak until something
     breaks; answers "where is the ceiling and what fails first."
   - **Soak test** — moderate load sustained for hours, not minutes;
     surfaces memory leaks, connection-pool exhaustion, and slow resource
     drains that a short test never reveals.
   - **Spike test** — a sudden, sharp jump in load with no ramp; answers
     "does autoscaling/backpressure react fast enough," a distinct failure
     mode from steady-state stress.
4. **Model virtual users realistically, not as a uniform hammer.** Include
   think-time between requests, a realistic mix of endpoint calls (not
   100% of traffic hitting the single heaviest endpoint), and ramp-up
   rather than an instant jump, unless the scenario is specifically a spike
   test.
5. **Run against a production-like environment**, not a scaled-down dev
   box — a passing result against under-provisioned infrastructure proves
   nothing about production behavior. If a full production-scale
   environment is infeasible, scale the pass/fail thresholds proportionally
   and say so explicitly in the report, not silently.
6. **Report p50/p95/p99 latency, error rate, and throughput against the
   threshold — not just an average.** An average latency can look fine
   while the p99 is failing the SLO for a meaningful slice of real users.
   Compare against the previous baseline run so a regression is visible
   even when the absolute numbers still pass.
7. **Feed the result forward.** A load test that finds a ceiling is direct
   input to capacity planning; a load test that finds a failure mode is
   direct input to whatever remediation (connection pool, cache, autoscale
   policy) addresses it — don't let the report be the last step.

## Checklist / quality gate
- Pass/fail thresholds are stated before the run and are traceable to an
  SLO, not chosen after seeing results.
- The tool matches the protocol under test.
- The scenario type (smoke/load/stress/soak/spike) matches the actual
  question being asked, and is named as such in the report.
- The test environment is production-like, or the report explicitly notes
  the scaling gap and adjusts thresholds accordingly.
- The report includes p95/p99 latency (not only average), error rate, and
  throughput, compared against a prior baseline where one exists.

## References
- [k6 documentation](https://k6.io/docs/) — scripting, scenario types,
  thresholds.
- [Locust documentation](https://docs.locust.io/) — Python-based user
  behavior modeling.
- [Gatling documentation](https://gatling.io/docs/) — high-throughput JVM
  load testing.
- [roadmap.sh — QA Engineer](https://roadmap.sh/qa) — load, performance,
  and stress testing as core QA competencies.

## Composition
Consumes SLO/error-budget targets as its threshold input rather than
inventing thresholds independently. Feeds its ceiling-and-failure-mode
findings into capacity-planning work and into whatever remediation skill
owns the fix (caching, connection pooling, autoscaling policy). Runs as a
pre-launch gate alongside `e2e-test-suite-authoring` and
`api-contract-test-authoring` in `ci-pipeline-authoring`'s pipeline stages,
and is scoped in the first place by `test-strategy-and-coverage-audit`
deciding whether a given service needs this layer of testing at all.
