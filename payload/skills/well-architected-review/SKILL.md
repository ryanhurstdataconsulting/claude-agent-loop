---
name: well-architected-review
description: Use when the task is "review our cloud architecture," an architecture-assessment deliverable is requested, a new workload needs a pre-launch architecture sign-off, or a due-diligence review must score a cloud environment against a recognized framework. Triggers include requests to audit a topology (from IaC source or a live account read) against operational excellence, security, reliability, performance efficiency, cost optimization, and sustainability; a leadership brief comparing current-state versus target-state architecture; or any ask to turn scattered infrastructure risk into a prioritized, severity-ranked remediation plan.
---

# well-architected-review

## Overview
Runs a structured review of a cloud architecture against the six Well-Architected pillars — operational excellence, security, reliability, performance efficiency, cost optimization, and sustainability — and turns the findings into a severity-ranked, actionable remediation plan. The one job it owns: converting "how healthy is this architecture" into a defensible, pillar-by-pillar scored assessment a technical or executive audience can act on.

## When to use
- A stakeholder asks for a cloud architecture review, audit, or assessment.
- A new workload needs a pre-launch architecture sign-off.
- An incident or near-miss (an outage, a cost spike, a security finding) prompts "how did our architecture let this happen, and where else are we exposed?"
- A due-diligence exercise (acquisition, new engagement, compliance audit) needs an independent architecture score.
- Leadership needs a current-state-versus-target-state comparison to justify an infrastructure investment.

## Workflow
1. **Establish scope and source of truth.** Confirm whether the review reads from IaC source (Terraform/CloudFormation/Pulumi), a live account/API read, or both. A live read catches configuration drift that IaC alone will miss; IaC alone is faster and safer when live access is not granted. State which source was used — findings sourced only from IaC should be flagged as "as-declared, not verified live."
2. **Inventory the actual topology** before scoring anything: compute, storage, network (VPCs, subnets, peering), data stores, IAM boundaries, and the services in the request path of the workload under review. A pillar review against an incomplete inventory produces false confidence.
3. **Walk each pillar with its own checklist** rather than one generic pass — the pillars pull in different, sometimes conflicting directions (for example, reliability wants redundancy; cost optimization wants to remove it), so score them independently and surface tensions explicitly:
   - **Operational excellence** — is infrastructure changed through code review and CI, or through manual console edits? Are runbooks current? Is there a single source of truth for configuration?
   - **Security** — least-privilege IAM (see `iam-least-privilege-policy-authoring`), encryption at rest and in transit, network segmentation, secrets management, patch/vulnerability posture.
   - **Reliability** — single points of failure, multi-AZ/multi-region posture, backup and recovery coverage (see `disaster-recovery-plan-authoring`), documented RTO/RPO versus what the architecture can actually deliver, health-check and auto-recovery coverage.
   - **Performance efficiency** — right-sized compute, appropriate data-store choice for the access pattern, caching layers, and whether the architecture can scale to the next order of magnitude of load without a redesign.
   - **Cost optimization** — see `cloud-cost-optimization-audit` for the deep pass; at minimum flag obvious waste (idle resources, oversized instances, missing lifecycle policies).
   - **Sustainability** — region selection against renewable-energy availability, workload scheduling to reduce idle-resource carbon footprint, and whether obsolete resources are decommissioned rather than left running.
4. **Score and rank, don't just list.** For each finding, assign a severity (critical / high / medium / low) based on blast radius and likelihood, not just theoretical badness. A wildcard IAM policy on an unused test account is a lower priority than the same policy on the production data plane.
5. **Separate quick wins from structural rework.** A remediation plan that lists forty items with no sequencing is not actionable. Group findings into: fix-this-week (low effort, high impact), plan-this-quarter (moderate effort, structural), and roadmap (requires a redesign or a budget cycle).
6. **Produce a current-state-versus-target-state artifact** when the audience is leadership rather than the engineering team directly doing the fix — a diagram or table contrasting "what exists today" against "what the target architecture looks like" communicates the gap faster than a findings list alone.
7. **Note tool support.** AWS, Azure, and Google Cloud each publish a Well-Architected (or equivalent Architecture Framework) review tool that can generate a baseline scorecard — use it as a starting checklist, not a substitute for the contextual judgment above; automated tools miss business-context tradeoffs (an intentional single-region deployment for a regulatory reason isn't a reliability defect).

## Checklist / quality gate
- Every pillar was reviewed against the actual topology, not a generic template with no findings tied to real resources.
- Every finding has a severity and a stated blast radius/likelihood rationale, not just a label.
- Findings are grouped into quick-win / structural / roadmap tiers, not left as a flat list.
- Any pillar with zero findings is verified as genuinely clean, not skipped for lack of access.
- IAM findings cross-reference `iam-least-privilege-policy-authoring`; DR/backup findings cross-reference `disaster-recovery-plan-authoring`; cost findings cross-reference `cloud-cost-optimization-audit` rather than duplicating their depth here.
- The deliverable states its source (IaC-declared versus live-account-verified) for every finding.

## References
- AWS Well-Architected Framework — the six pillars: https://docs.aws.amazon.com/wellarchitected/latest/framework/the-pillars-of-the-framework.html
- AWS Well-Architected Framework docs (full): https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html
- Azure Well-Architected Framework and the Google Cloud Architecture Framework are structurally equivalent five/six-pillar frameworks — check the current version of each before citing pillar names, as naming has shifted across framework revisions.

## Composition
Feeds into `disaster-recovery-plan-authoring` (reliability-pillar findings become the DR plan's starting risk register) and `iam-least-privilege-policy-authoring` (security-pillar IAM findings hand off directly). Pairs with `vpc-network-topology-design` for the network-segmentation portion of the security and reliability pillars, and with `cloud-cost-optimization-audit` for a deeper cost-optimization pass than this review's checklist-level treatment. When the review surfaces a hard architectural tradeoff, hand off to an architecture-decision-record skill to make the call durable.
