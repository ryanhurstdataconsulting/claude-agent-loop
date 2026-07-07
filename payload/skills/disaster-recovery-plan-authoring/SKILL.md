---
name: disaster-recovery-plan-authoring
description: Use when designing a disaster-recovery or backup strategy, defining RTO/RPO targets, or producing a failover runbook for a critical system. Triggers include "what's our recovery plan if the primary region/database goes down," a post-incident review that surfaces a missing or untested DR plan, a compliance or customer-contract requirement for a documented recovery-time commitment, or a request to choose between pilot-light, warm-standby, and multi-site active-active architectures.
---

# disaster-recovery-plan-authoring

## Overview
Designs a disaster-recovery strategy for a system or environment — from RTO/RPO target-setting through backup-strategy selection to a concrete failover runbook — so that "what happens if this goes down" has a tested, documented answer instead of an assumption. The one job it owns: turning business-impact tolerance into a specific, budget-appropriate recovery architecture and the runbook to execute it.

## When to use
- Standing up disaster recovery for a system that has none.
- A post-incident review reveals recovery took longer than expected, or a recovery step was undocumented and improvised.
- A compliance requirement or customer contract demands a documented, tested recovery-time commitment.
- Choosing between backup-and-restore, pilot-light, warm-standby, and multi-site active-active architectures for a given system, and needing the tradeoffs made explicit.
- A Well-Architected review's reliability pillar surfaces a single point of failure with no recovery path.

## Workflow
1. **Start from business impact, not from a technology preference.** For each system in scope, quantify the cost of downtime and the cost of data loss per unit of time — this produces the actual RTO (recovery time objective: how long can the system be down) and RPO (recovery point objective: how much data can be lost, measured in time since the last recoverable point) targets. A system with no clear business-impact number gets an arbitrary target that either overspends or under-protects.
2. **Match architecture to the RTO/RPO target, not the other way around.** The recovery-strategy spectrum trades cost against recovery speed:
   - **Backup and restore** — lowest cost, RTO/RPO measured in hours; appropriate for non-critical systems.
   - **Pilot light** — minimal always-on core infrastructure in the recovery region/site, scaled up on failover; RTO/RPO in tens of minutes to a couple of hours.
   - **Warm standby** — a scaled-down but fully functional replica running continuously; RTO/RPO in minutes.
   - **Multi-site active-active** — full capacity running in more than one location simultaneously; RTO/RPO near zero, at the highest cost and operational complexity.
   Do not default to the most robust (and most expensive) option — match the strategy to the business-impact number from step 1, and state the cost/complexity tradeoff explicitly so a budget owner can confirm the choice.
3. **Design the backup layer independently of the failover layer.** Even an active-active architecture needs point-in-time backups — replication propagates corruption and accidental deletion just as fast as it propagates legitimate writes, so backups protect against a different failure mode than failover does. Verify backup retention, encryption, and — critically — that backups are tested by actually restoring from them, not just confirmed to exist.
4. **Design for the failure modes that actually threaten the system**, not only "the whole region disappears." Database corruption, a bad deployment, an accidental deletion, and a credential compromise are all more statistically likely than a full regional outage, and each needs its own recovery path in the plan, not just the region-failover scenario.
5. **Write the failover runbook as a concrete, sequenced procedure** — who declares a disaster, what the exact steps are to redirect traffic (DNS cutover, load-balancer reweighting, database promotion), what the rollback path is if failover itself fails partway through, and how success is verified before declaring the incident resolved. A DR plan that exists only as an architecture diagram, with no runbook, is not executable during an actual incident.
6. **Define the disaster-declaration trigger and owner explicitly.** Vague plans fail at exactly the moment they are needed because no one is sure it is bad enough to invoke, or who has the authority to invoke it — name the specific signal (for example, primary-region health check failing past a defined threshold for a defined duration) and the specific role authorized to declare.
7. **Test the plan, not just the architecture.** A DR architecture that has never been exercised via a game-day or failover drill is unverified — schedule a recurring test (tabletop at minimum, live failover drill where risk tolerance allows) and treat any gap the drill surfaces as a plan defect, not a footnote.
8. **State assumptions and dependencies explicitly.** A recovery plan that depends on a third-party DNS provider, a specific team member's availability, or a manual approval step outside business hours needs those dependencies named — an unstated dependency is the most common reason a documented RTO turns out to be unachievable in practice.

## Checklist / quality gate
- RTO and RPO targets are tied to a stated business-impact justification, not chosen arbitrarily.
- The chosen recovery-strategy tier (backup-restore / pilot-light / warm-standby / active-active) is matched to the RTO/RPO target with the cost tradeoff stated explicitly.
- Backups are verified as restore-tested, not merely confirmed to exist.
- The plan covers non-regional failure modes (corruption, bad deploy, accidental deletion, credential compromise), not only full-region loss.
- A concrete, sequenced failover runbook exists — with an explicit disaster-declaration trigger and named authority — not just an architecture diagram.
- A test/drill cadence is defined, and any gap a prior drill surfaced has a tracked remediation.
- External dependencies (third-party services, specific personnel, manual approval steps) are named explicitly.

## References
- AWS Well-Architected Framework — Reliability pillar: https://docs.aws.amazon.com/wellarchitected/latest/framework/the-pillars-of-the-framework.html
- The backup-and-restore / pilot-light / warm-standby / multi-site-active-active spectrum is a standard disaster-recovery taxonomy used consistently across major cloud providers' reliability guidance — confirm current provider-specific service names (for example, the managed database failover feature in use) before finalizing an architecture.

## Composition
Feeds from the reliability pillar of `well-architected-review` (single-point-of-failure findings become the DR plan's starting risk register) and from `vpc-network-topology-design` for the multi-region connectivity the failover architecture depends on. The failover runbook this skill produces should be handed off in the same symptom-diagnosis-remediation-escalation structure an incident-runbook skill would use, so it can be exercised the same way any other production runbook is.
