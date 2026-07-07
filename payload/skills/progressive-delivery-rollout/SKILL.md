---
name: progressive-delivery-rollout
description: Use when a release needs to ship safely rather than all-at-once — "roll this out gradually," "set up a canary," "we need blue-green deploys," or a feature-flagged release that ramps by percentage. Triggers include a request for automated rollback on a bad deploy, canary analysis, weighted traffic splitting, or wiring a rollout's abort condition to an existing SLO/error-budget signal. Also fires for Argo Rollouts, Flagger, LaunchDarkly-style flag ramps, and post-incident asks to "make sure a bad release can't reach everyone next time."
---

# progressive-delivery-rollout

## Overview
Designs and wires a staged release strategy — canary, blue-green, or
feature-flag ramp — matched to a change's actual blast-radius risk, with an
automated rollback trigger tied to the service's real health signal rather
than an arbitrary threshold. The one job it owns: make a bad release
detectable and reversible before it reaches most users, automatically.

## When to use
- A release currently goes to 100% of traffic at once, with no staged
  exposure.
- A past incident traced back to a release that should have been caught by
  a canary before full rollout.
- A team asks for canary deploys, blue-green deploys, or a feature-flag
  ramp, but has no rollback automation behind it.
- Argo Rollouts, Flagger, or a flagging platform (e.g., LaunchDarkly-style)
  is being adopted or is already in place but under-configured.
- A service has an existing SLO or error budget that nothing in the release
  path currently reads from.

## Workflow
1. **Classify blast radius before picking a strategy.** Match the strategy
   to the actual risk, not to whatever is fashionable:
   - Low-risk, stateless, easily reversible change → **rolling update** is
     often sufficient; progressive delivery may be overkill.
   - Behavior change with user-visible risk, need for fast, cheap rollback
     on a subset of traffic → **canary** (weighted traffic split, ramping
     percentage).
   - Infrastructure or platform-level change, need for instant all-or-nothing
     cutover and rollback → **blue-green** (two full environments, switch
     traffic at the load balancer / DNS level).
   - Change gated by user segment or needs a kill switch independent of a
     deploy → **feature flag ramp** (percentage-based flag rollout,
     decoupled from the deploy itself).
   These are not mutually exclusive — a canary deploy can itself be gated
   behind a feature flag for an extra layer of control.
2. **Do not invent a new threshold — reuse the SLO.** The canary
   pass/fail metric and the automated-rollback trigger should read from the
   same error-budget burn-rate signal the service's SRE practice already
   monitors, not an ad hoc "error rate under 2%" pulled out of the air. If no
   SLO exists yet, that is a prerequisite to flag, not a gap to paper over
   with a guessed number.
3. **Define the canary analysis window and traffic increments** explicitly:
   - Minimum bake time per stage, long enough to catch slow-building failure
     modes (memory leak, cache-driven regression) — not just an immediate
     error spike.
   - Traffic percentage steps (e.g., 5% → 25% → 50% → 100%) with a
     pass/fail gate at each step, not a single all-or-nothing canary check.
   - What "pass" means precisely: the canary's error rate / latency /
     saturation metrics stay within the SLO's burn-rate budget relative to
     the baseline (stable) version, compared statistically — not eyeballed.
4. **Wire the rollback trigger to fire automatically**, not just alert a
   human. A canary that pages someone at 2am instead of rolling back itself
   defeats the purpose. Confirm the rollback path (previous ReplicaSet,
   previous flag state, DNS/LB switch back to blue) is tested and fast —
   an untested rollback path is not a rollback path.
5. **Choose the mechanism**:
   - Kubernetes-native, want deep metric-provider integration (Prometheus,
     Datadog) → **Argo Rollouts**.
   - Kubernetes-native, want a GitOps-first, lighter-weight setup and
     built-in Prometheus/Datadog/CloudWatch analysis → **Flagger**.
   - Application-level ramp independent of infrastructure/deploy topology,
     need instant kill switch and per-segment targeting → a **feature-flag
     platform** with percentage rollout support.
6. **Confirm observability exists before the first live canary.** The
   canary is only as good as the metrics it reads — verify the service
   already emits the latency/error/saturation signals the analysis step
   needs (see `add-structured-logging-and-tracing` if it does not) before
   wiring the gate.
7. **Document the manual override path.** Even with automated rollback,
   an operator needs a documented, fast way to force an abort or force-promote
   mid-rollout — do not build a system that can only proceed on autopilot.

## Checklist / quality gate
- [ ] Strategy (canary / blue-green / flag ramp) matches the change's actual
      blast radius — not chosen by default.
- [ ] Canary/rollback threshold reads from an existing SLO / error-budget
      burn rate, not an invented number.
- [ ] Traffic ramp has multiple stages with a pass/fail gate at each, not a
      single all-or-nothing check.
- [ ] Rollback fires automatically on a failed gate and has been tested,
      not just alerted-and-hoped.
- [ ] Bake time per stage is long enough to catch slow-building regressions,
      not just immediate error spikes.
- [ ] Required metrics (latency, error rate, saturation) are confirmed to
      exist before the first live canary runs.
- [ ] A documented manual override (force-abort / force-promote) exists.

## References
- [Google SRE Workbook — Canarying Releases](https://sre.google/workbook/canarying-releases/)
- [Argo Rollouts documentation](https://argo-rollouts.readthedocs.io/)
- [Flagger documentation](https://flagger.app/)

## Composition
Consumes the SLO and burn-rate signal owned by `slo-error-budget-definition`
— define or confirm that before wiring the rollback gate. Sits downstream of
`gitops-deployment-setup`, which owns the deployment mechanics this skill
layers staged traffic control on top of. Follows `semantic-release-versioning`
in the pipeline: a version is cut and published first, then rolled out
progressively. On a failed rollout, hands off to `postmortem-generator` for
the RCA.
