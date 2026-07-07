---
name: vpc-network-topology-design
description: Use when designing or reviewing a cloud VPC/VNet — subnetting, CIDR-range planning, routing, NAT/internet-gateway placement, security-group versus network-ACL layering, or multi-region peering and transit-gateway topology. Triggers include "design the network for a new environment," a subnet-exhaustion or IP-overlap error, a request to diagram network topology from Terraform/CloudFormation source, or a disaster-recovery design that needs a second region wired to the first.
---

# vpc-network-topology-design

## Overview
Designs or reviews the network layer of a cloud environment — CIDR allocation, subnet segmentation, routing, gateway placement, and cross-region connectivity — so that traffic flows only where it is meant to and the topology has headroom to grow without a re-architecture. The one job it owns: turning a set of workload and connectivity requirements into a concrete, non-overlapping, defensible network topology.

## When to use
- Standing up a new VPC/VNet for a new environment, account, or region.
- A subnet is running out of address space, or a peering/transit-gateway attempt fails with a CIDR-overlap error.
- Reviewing an existing topology for correctness before a security or compliance audit.
- Designing multi-region connectivity to support disaster recovery or global traffic routing.
- Generating a topology diagram from IaC source for a design review or onboarding document.

## Workflow
1. **Gather requirements before drawing anything.** How many environments (dev/staging/prod)? How many regions? Expected workload count and growth rate? Which workloads must be internet-facing versus fully private? Any compliance requirement forcing traffic through a specific inspection point? Skipping this step is the single most common cause of a topology that needs to be redone within a year.
2. **Plan the CIDR range top-down, not bottom-up.** Reserve a large enough address block per environment/region up front (a /16 per VPC is a common starting point for anything beyond a toy environment) and carve subnets from it — resizing a live VPC's CIDR range later is disruptive. Leave headroom: an under-sized allocation is the most common reason a topology needs rework.
3. **Split public and private subnets deliberately.** Public subnets hold only what must be internet-reachable (load balancers, NAT gateways, jump hosts); everything else — application servers, databases, internal services — goes in private subnets with no direct route to an internet gateway.
4. **Place NAT and internet gateways correctly.** One NAT gateway per availability zone for resilience (a single NAT gateway is a single point of failure for all outbound traffic from every private subnet behind it); internet gateways attach at the VPC level and only route to subnets with an explicit route-table entry pointing to them.
5. **Layer security groups and network ACLs deliberately, not redundantly.** Security groups are stateful and instance-level — use them as the primary control. Network ACLs are stateless and subnet-level — use them for a coarse, defense-in-depth layer (for example, an explicit deny on a known-bad range) rather than duplicating every security-group rule.
6. **Design peering or transit-gateway topology for multi-region or multi-account connectivity.** Direct VPC peering does not transit — if VPC One is peered to VPC Two, and VPC Two is peered to VPC Three, VPC One still has no route to VPC Three — so for anything beyond two or three VPCs, a transit gateway or hub-and-spoke model scales better and centralizes route management. Verify no CIDR ranges overlap across any two VPCs that will ever need to route to each other, including ranges reserved for future growth.
7. **Wire DNS deliberately.** Decide whether private hosted zones, VPC-associated DNS resolution, or a centralized DNS resolver (Route 53 Resolver, Azure Private DNS) fits the topology — cross-VPC DNS resolution is a common gap that breaks service discovery after a peering or transit-gateway change.
8. **Verify structurally before calling it done.** Check for overlapping CIDR ranges across every VPC pair that will route to each other, orphaned route tables with no subnet association, security groups with an unrestricted `0.0.0.0/0` ingress rule that was not deliberate, and subnets with no route to a NAT/internet gateway that were meant to have one.
9. **Generate a topology diagram** when the deliverable is for a review or onboarding audience — a diagram communicates subnet/AZ/gateway relationships far faster than a route-table listing.

## Checklist / quality gate
- No two CIDR ranges overlap across any VPC pair that has (or will have) a route between them.
- Every subnet's public/private classification matches its actual route-table entries (no "private" subnet with a route to an internet gateway).
- Every private subnet that needs outbound internet access has a route to a NAT gateway in its own availability zone.
- Security-group and NACL rules are reviewed together for redundancy or contradiction, not authored independently.
- Multi-region/multi-account connectivity uses a topology (peering versus transit gateway) that matches the actual number of VPCs involved — not ad hoc peering left over from an earlier, smaller footprint.
- A topology diagram exists for any deliverable aimed at a review or onboarding audience.

## References
- AWS VPC design and best-practices documentation: https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html
- AWS Well-Architected Framework — Reliability and Security pillars (network segmentation guidance): https://docs.aws.amazon.com/wellarchitected/latest/framework/the-pillars-of-the-framework.html

## Composition
Feeds the network-segmentation portion of `well-architected-review` (security and reliability pillars) and the multi-region connectivity layer of `disaster-recovery-plan-authoring`. Hands off to `iam-least-privilege-policy-authoring` when network boundaries alone are insufficient and identity-based controls are needed at the resource layer. Pairs with a diagramming skill when the deliverable needs a visual topology rather than a route-table listing.
