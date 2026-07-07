---
name: cloud-cost-optimization-audit
description: Use when the task is "reduce our cloud bill," a recurring cost review is due, a cost-anomaly alert fires, or finance flags a spend spike with no matching workload growth. Triggers include a request for rightsizing recommendations, a reserved-versus-on-demand-versus-spot mix decision, orphaned-resource cleanup (unattached volumes, idle load balancers, unused elastic IPs), or a request for a cost-allocation tagging strategy.
---

# cloud-cost-optimization-audit

## Overview
Audits a cloud environment's spend against its actual utilization and surfaces the concrete, evidence-backed opportunities to reduce cost without harming reliability or performance. The one job it owns: turning a cost bill line-item list into a prioritized set of savings actions, each backed by a usage metric rather than a guess.

## When to use
- A stakeholder asks to "reduce the cloud bill" without a specific target in mind.
- A recurring (monthly/quarterly) cost review is due.
- A cost-anomaly alert fires, or finance flags a spend increase with no corresponding workload growth.
- Planning a reserved-capacity or savings-plan purchase and needing a usage baseline first.
- Onboarding a new environment and wanting a cost-allocation tagging strategy in place from day one, rather than retrofitted later.

## Workflow
1. **Pull utilization data before recommending anything.** CPU, memory, network, and storage-IOPS utilization over a representative window (at minimum two to four weeks, longer if the workload has a weekly or monthly cycle) is the evidence base for every recommendation that follows — a rightsizing suggestion made without utilization data is a guess, not an audit.
2. **Rightsize compute against actual usage, not provisioned capacity.** Flag instances/containers running consistently below roughly 40% utilization on their primary bottleneck resource as rightsizing candidates; verify against peak windows, not just the average, so a batch job that spikes once a day is not incorrectly downsized.
3. **Evaluate the commitment mix.** Compare current on-demand spend against what a reserved-instance, savings-plan, or committed-use-discount purchase would save, sized to the *baseline* (steady, always-on) portion of usage — never commit spend against the peak or bursty portion, which belongs on-demand or spot instead. State the break-even horizon for any commitment recommendation (a one-year commitment only pays off if the workload is expected to run at least that long).
4. **Identify spot/preemptible candidates.** Fault-tolerant, interruptible, or batch workloads (CI runners, non-time-critical data processing) are strong spot-instance candidates at a substantial discount over on-demand; anything stateful or latency-sensitive is not, regardless of the savings.
5. **Hunt orphaned resources — this is usually the fastest, safest win.** Unattached storage volumes, idle or unused load balancers, unassociated elastic/static IP addresses, forgotten snapshots past their retention need, and stopped-but-still-billed resources all cost money with zero corresponding value; these carry no performance-risk tradeoff, unlike rightsizing or commitment decisions, so surface them first.
6. **Check storage lifecycle policies.** Data that has not been accessed in months sitting in a hot/standard storage tier is a common, low-risk savings opportunity — verify a lifecycle policy exists to transition or expire it, and that the transition schedule matches actual access patterns rather than a guessed default.
7. **Build or verify a cost-allocation tagging strategy.** Without consistent tags (team, environment, project, cost-center), spend cannot be attributed to an owner who can act on it — a tagging gap is itself a finding, not just a prerequisite for future audits.
8. **Separate "safe to act on now" from "needs a budget owner's sign-off."** Orphaned-resource cleanup and lifecycle-policy fixes are typically safe to execute directly. Reserved-capacity purchases and any rightsizing that touches a production workload's headroom need a human owner to confirm before committing spend or capacity.

## Checklist / quality gate
- Every rightsizing recommendation cites the utilization metric and the observation window it is based on, not just "this looks oversized."
- Commitment-purchase recommendations are sized to baseline usage, with a stated break-even horizon.
- Orphaned-resource findings are separated out as immediate, low-risk wins rather than buried in the same list as capacity-commitment decisions.
- A tagging-for-cost-allocation gap, if found, is called out as its own finding.
- Every recommendation states whether it is safe to execute directly or needs a budget-owner sign-off before acting.
- The audit references the reliability tradeoff of any rightsizing recommendation — a cost-driven downsize that removes needed headroom is not actually a win.

## References
- AWS Well-Architected Framework — Cost Optimization pillar: https://docs.aws.amazon.com/wellarchitected/latest/framework/the-pillars-of-the-framework.html
- FinOps Foundation practices — the industry framework for cloud financial management (rightsizing, commitment-mix, and tagging guidance align with FinOps Foundation principles; consult the current framework version for platform-specific detail).

## Composition
Feeds the cost-optimization pillar of `well-architected-review`. Shares its capacity/utilization analysis method with any capacity-forecasting practice — headroom and spend are two ends of the same tradeoff, so a capacity forecast and a cost audit should reconcile against the same utilization data rather than each collecting it independently. Hands off commitment-purchase and production-rightsizing decisions to a human budget owner for sign-off before execution.
