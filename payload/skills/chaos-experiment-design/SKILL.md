---
name: chaos-experiment-design
description: Use when resilience needs to be tested deliberately rather than discovered during an outage — "let's test what happens if X fails," a postmortem reveals an untested failure mode, or a service is about to take on critical load without ever having had a dependency, zone, or node killed under it on purpose. Designs a hypothesis-driven chaos or fault-injection experiment — steady-state definition, fault selection, blast-radius and abort conditions, and a staged staging-to-limited-production-to-full-production rollout. Triggers include "run a game day," "chaos test this," "what happens if this dependency goes down," or "we've never actually tested our failover."
---

# chaos-experiment-design

## Overview
Designs a chaos-engineering experiment: a falsifiable hypothesis about how the system
behaves under a specific, deliberately injected fault, a definition of the steady
state that would confirm or refute it, and the blast-radius and abort controls that
keep the experiment from becoming the incident it's meant to prevent. This skill owns
experiment *design*; running fault injection against production is a human go/no-go
decision it surfaces but never makes unilaterally.

## When to use
- A postmortem or architecture review surfaces an untested failure mode ("we assume
  the cache falls back gracefully, but we've never actually killed it").
- A team wants to validate a resilience claim before it's load-bearing — a new
  failover path, a new retry or circuit-breaker configuration, a newly added
  redundant zone.
- A game day is being planned to rehearse an incident response as much as to test the
  system itself.
- A dependency's blast radius on the rest of the system is unknown and needs to be
  measured deliberately rather than discovered the hard way.

## Workflow

**1. Write the hypothesis before picking a tool.** State it as a falsifiable claim
about system behavior: "if the primary cache becomes unreachable, request latency
stays under the SLO threshold because the service falls back to the origin
datastore." An experiment with no hypothesis just breaks things and watches — it
produces anecdotes, not evidence.

**2. Define steady state in measurable terms**, using the service's existing
golden-signal dashboards where possible: the metric, its normal range, and the
specific threshold that would count as the hypothesis failing. If no dashboard already
measures the relevant signal, close that gap before the experiment, not during it.

**3. Pick the smallest fault that tests the hypothesis, not the most dramatic one.**
Common categories: dependency failure (kill or blackhole a downstream call), resource
exhaustion (CPU, memory, disk, connection pool), network fault (latency injection,
packet loss, DNS failure), infrastructure fault (kill a node, an availability zone, a
pod). Match the fault to the specific claim under test — testing zone failover with a
full-region outage is over-scoped.

**4. Set blast-radius limits before the fault is injected, not during:** the
percentage of traffic or instances affected, which environment (see the staged
rollout below), and a hard ceiling on customer impact — for example, "abort
automatically if the error rate exceeds 1%, or exceeds baseline plus three standard
deviations, whichever is lower."

**5. Set explicit abort conditions and confirm the rollback path works before
injecting the fault.** "We'll just stop the experiment" is not a rollback plan if the
fault-injection tool itself becomes unreachable mid-experiment. Prefer tools with a
dead-man's-switch behavior — the fault self-reverts if the controller loses contact —
over ones that require an active stop command.

**6. Select the tool to match the fault and the platform:** Chaos Mesh or Litmus for
Kubernetes-native fault injection, AWS Fault Injection Simulator for AWS-managed
infrastructure faults, Gremlin for a managed cross-platform option, or a small
hand-rolled script for a narrow, simple fault (`tc netem` for network latency or loss,
for example). Do not reach for a heavyweight platform when a five-line script covers
the hypothesis.

**7. Stage the rollout — never debut a new experiment in full production:**
- **Staging or pre-production** first, to catch tooling mistakes and confirm the fault
  actually injects what's intended.
- **Limited production** next — a single instance, a single availability zone, or a
  small traffic percentage, with the blast-radius limits from step 4 active.
- **Full production** only after limited-production runs confirm both the hypothesis
  and the abort path, and only with an explicit human go/no-go — this is the one step
  this skill does not make unilaterally.

**8. Capture the result against the original hypothesis**, not just "it worked" or
"it didn't." A confirmed hypothesis still gets documented, since resilience claims
decay as the system changes; a falsified hypothesis becomes an incident-shaped writeup
and, often, a runbook or architecture fix.

## Checklist / quality gate
- A falsifiable hypothesis is stated before any tool or fault is chosen.
- Steady state is defined against an existing or newly added measurable signal, with
  an explicit failure threshold.
- The fault chosen is the smallest one that tests the hypothesis, matched to the
  specific claim under test.
- Blast-radius limits — traffic percentage, environment, hard impact ceiling — are set
  before injection, not improvised during it.
- An abort or rollback path is confirmed working before the fault is injected, ideally
  with a dead-man's-switch default.
- The rollout is staged staging, then limited production, then full production, with
  an explicit human go/no-go before full production.
- The result is recorded against the original hypothesis, whether confirmed or
  falsified.

## References
- Principles of Chaos Engineering: https://principlesofchaos.org/
- Quinnox — Chaos Engineering for DevOps/SRE: https://www.quinnox.com/blogs/chaos-engineering-for-devops-sre/
- Google SRE Book — Embracing Risk: https://sre.google/sre-book/embracing-risk/

## Composition
Blast-radius and abort thresholds should reference the remaining error budget from
`slo-error-budget-definition` rather than an arbitrary percentage. Steady-state
signals come from `observability-instrumentation`, and load-test or fault-injection
results feed directly into `capacity-planning-forecast`. A falsified hypothesis is
written up the same way a real incident is, using `postmortem-generator`, and often
produces or validates a `runbook-authoring-from-incident` procedure.
