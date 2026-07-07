---
name: ci-runner-capacity-and-queue-tuning
description: Use when CI queue times are growing, jobs sit "waiting for a runner" for minutes before starting, or runner capacity needs planning ahead of a headcount or repo-count increase. Triggers include complaints that "CI is slow" that turn out to be queueing rather than build time, a request to size a self-hosted runner pool, autoscaling policy for build infrastructure, or a cost-vs-speed tradeoff writeup for adding CI capacity.
---

# ci-runner-capacity-and-queue-tuning

## Overview
Diagnoses whether a CI slowness complaint is actually a queueing problem
(not enough runners) rather than a build-time problem (slow builds), then
sizes and configures runner capacity — autoscaling policy, job priority,
queue-depth thresholds — with an explicit cost-vs-speed tradeoff for the
capacity decision. The one job it owns: find the real bottleneck before
recommending "add more runners."

## When to use
- Developers report "CI is slow" — before assuming it is build performance,
  check whether jobs are waiting in queue.
- Queue-wait time (time from job-triggered to job-started) is growing over
  weeks or months, even if individual job duration is flat.
- A runner pool needs sizing ahead of a known headcount or repo-count
  increase.
- Peak-hour CI contention causes jobs from different teams to compete for
  the same limited runner pool.
- A request to evaluate self-hosted vs. hosted runners, or to tune
  autoscaling policy for an existing self-hosted pool.

## Workflow
1. **Separate queue time from run time before doing anything else.** Pull
   per-job timestamps: triggered → started → finished. If queue time (started
   minus triggered) is a small fraction of total time, this is a build-speed
   problem — hand off to `monorepo-build-optimization` or general build
   profiling instead. If queue time is a significant or growing share, this
   is a capacity problem — proceed.
2. **Characterize the queue pattern**, not just its average:
   - Is contention concentrated at specific hours (e.g., a shared "everyone
     pushes before EOD" spike) or steady throughout the day?
   - Is it a specific job type (e.g., GPU or large-memory runners) that is
     capacity-constrained while general-purpose runners sit idle?
   - Is one team or repo monopolizing the shared pool, starving others?
   The fix differs by pattern: a load-shape spike wants better scheduling or
   priority, not necessarily more total capacity; a bursty single-tenant hog
   wants job-priority/quota, not a bigger pool for everyone.
3. **Check for the cheap fixes before recommending spend**:
   - **Affected-only scoping** (see `monorepo-build-optimization`) reduces
     total job volume, which reduces queue pressure without adding a single
     runner.
   - **Job right-sizing** — jobs requesting more CPU/memory than they use
     shrink the effective pool; check actual utilization against requested
     resources before assuming the pool itself is undersized.
   - **Concurrency limits and cancel-in-progress** — superseded commits on
     the same branch/PR still consuming a runner slot is pure waste; cancel
     stale runs on new pushes to the same ref.
   - **Job priority / queue ordering** — a fast-fail lint or unit-test stage
     queued behind a slow integration-test job delays feedback without any
     more capacity being needed; reordering or splitting queues can fix it.
4. **Only after the cheap fixes are exhausted, size the pool.** Forecast
   demand using the same capacity-planning method used for production
   infrastructure: current peak concurrent job count, projected growth
   (headcount, repo count, commit frequency), and a target queue-wait SLO
   (e.g., "95% of jobs start within 2 minutes of trigger"). Undersizing
   the target erodes trust in CI turnaround; oversizing wastes budget — state
   the tradeoff explicitly rather than picking a number silently.
5. **Configure autoscaling with real bounds**, not defaults:
   - Minimum pool size that absorbs typical start-of-day/burst load without
     a cold-start scaling lag.
   - Maximum pool size that caps runaway spend from a misbehaving workflow
     (e.g., an accidental infinite retry loop).
   - Scale-down cooldown long enough to avoid thrashing (scale up, immediately
     scale down, scale up again) under bursty-but-not-sustained load.
6. **Write the cost-vs-speed tradeoff up explicitly** for whoever owns the
   budget decision: current queue-wait cost in engineering time (jobs
   waiting × average team size × loaded cost estimate, if available) versus
   the marginal cost of additional runner capacity or a larger instance
   tier. This skill produces the analysis; the spend decision itself is a
   human call.
7. **Re-measure after the change** using the same queue-time metric from
   step 1 — confirm the fix moved the number, not just that it "feels
   faster."

## Checklist / quality gate
- [ ] Queue time and run time were measured separately before diagnosing
      the cause.
- [ ] The queue pattern (time-of-day spike, job-type-specific, single-tenant
      hog) is characterized, not just averaged.
- [ ] Cheap fixes (affected-only scoping, job right-sizing, stale-run
      cancellation, queue priority) were checked before recommending more
      capacity.
- [ ] Any pool-size recommendation is tied to a stated target queue-wait SLO
      and a growth forecast, not a round number.
- [ ] Autoscaling has an explicit min, max, and scale-down cooldown.
- [ ] The cost-vs-speed tradeoff is written up for the budget owner rather
      than the agent silently deciding the spend.
- [ ] Post-change queue-time was re-measured against the same metric used
      to diagnose the problem.

## References
- [DevOpsSchool — Build Engineer role blueprint](https://www.devopsschool.com/blog/build-engineer-role-blueprint-responsibilities-skills-kpis-and-career-path/) — names uptime, queue time, and runner-availability ownership as core to the role.

## Composition
Shares its forecasting method with the SRE `capacity-planning-forecast`
skill (same technique, applied to build infrastructure instead of
production) and with the `cloud-cost-optimization-audit` skill for the
spend side of the tradeoff. Hands off to `monorepo-build-optimization` when
the real bottleneck turns out to be build time or job volume rather than
runner count. Feeds `engineering-delivery-metrics` — queue-time
trends are a direct input to delivery-speed reporting.
