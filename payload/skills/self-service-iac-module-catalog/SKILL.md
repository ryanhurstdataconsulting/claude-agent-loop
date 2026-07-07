---
name: self-service-iac-module-catalog
description: Use when building or extending a catalog of reusable Terraform, OpenTofu, or Crossplane modules that product teams provision from directly, without a platform-team review gate on every request. Triggers include "build a self-service module for X," a platform team drowning in one-off infrastructure requests, a request to add policy-as-code guardrails (OPA/Sentinel) so modules are safe to self-provision, or a need to define module versioning and publishing conventions for an internal registry.
---

# self-service-iac-module-catalog

## Overview
A self-service infrastructure-as-code module catalog lets product teams provision approved infrastructure patterns (a database, a queue, a storage bucket, a compute service) directly from a versioned, parameterized module — with safety enforced by policy-as-code guardrails instead of a human reviewing every request. The one job it owns: making the safe way to provision infrastructure also the fast way, so teams self-serve from the catalog instead of hand-rolling their own Terraform.

## When to use
- A platform team's infrastructure-request queue is dominated by requests that are structurally identical to something already provisioned elsewhere ("another S3-equivalent bucket," "another managed Postgres instance").
- Building or extending an internal module registry that other teams pull from.
- A request to add guardrails (policy-as-code, not manual review) so a module is safe to let teams self-provision without a human in the loop on every apply.
- Defining or fixing module versioning, publishing, or deprecation conventions for an existing internal registry.
- A `golden-path-template-authoring` scaffold needs to reference a real, published module rather than inline a bespoke copy of the resources.

## Workflow
1. **Parameterize for the common case, not every case.** A module with forty optional variables to cover every conceivable configuration is not self-service — it just moves the judgment call from the platform team to a confused requester. Expose a small set of well-named, sensibly defaulted variables (size tier, region, environment) and hide the rest behind opinionated defaults.
2. **Bake safety into the default, not into a review step.** The point of self-service is removing the human gate; that only works if the module cannot be misused into an unsafe state. Default to encryption-at-rest on, private networking, least-privilege IAM, and a sane backup/retention policy — features a requester would have to actively fight the module to disable, not opt into.
3. **Enforce guardrails with policy-as-code, not tribal knowledge.** Wire an OPA (Rego) or Sentinel policy check into the module's plan/apply pipeline so violations (public S3-equivalent bucket, wildcard IAM, missing encryption) are rejected mechanically before apply, not caught in a human review that a busy reviewer might skip.
4. **Version explicitly and publish a changelog.** Semantic-version each module; a breaking change to a required variable or default is a major bump. Teams already consuming version `N` should not be silently affected by a change to `N+1` — pin consumers to a version range and communicate deprecations with a lead time before removing an old major version.
5. **Document the module's blast radius.** For each module, state plainly what it provisions, what it costs at each size tier, and what happens on destroy (is data retained, or does `terraform destroy` delete it irreversibly). A requester should not have to read the module source to find out it deletes a database on teardown.
6. **Provide a dry-run path.** `terraform plan` (or the Crossplane-equivalent preview) output should be reviewable by the requester before apply, even in a self-service flow — self-service does not mean "no visibility into what will change," only "no required human approval to proceed."
7. **Verify the policy gate actually blocks a known-bad configuration**, not just that it exists. Author a test case that deliberately violates each guardrail and confirm the pipeline rejects it before trusting the module catalog as a safety boundary.

## Checklist / quality gate
- [ ] Module exposes a small set of well-named variables with safe, opinionated defaults, not dozens of raw pass-throughs.
- [ ] Unsafe configurations (public exposure, wildcard IAM, disabled encryption) require the requester to actively override a default, not opt in from a blank slate.
- [ ] A policy-as-code gate (OPA/Sentinel or equivalent) is wired into plan/apply and verified against at least one known-bad test case per guardrail.
- [ ] Module is semantically versioned, with a changelog entry per release and a documented deprecation window for breaking changes.
- [ ] Blast radius (cost tier, destroy behavior, data retention) is documented plainly, not buried in source.
- [ ] Consumers can see a plan/preview before apply, even without a required human approval step.

## References
- env0, "Terraform Governance Tools Compared: OPA, Sentinel, Checkov and tfsec" — https://www.env0.com/insights/terraform-governance-tools-compared-opa-sentinel-checkov-tfsec-and-when-to-use-each
- Open Policy Agent documentation — https://www.openpolicyagent.org/docs
- Terraform documentation — https://developer.hashicorp.com/terraform/docs

## Composition
Consumed by `golden-path-template-authoring`, which references a published catalog module rather than inlining infrastructure resources. Pairs with `kubernetes-security-hardening` when the module provisions cluster-level resources (namespaces, RBAC), and with `terraform-module-authoring` for the mechanical module-writing conventions this skill's guardrail and cataloging layer sits on top of.
