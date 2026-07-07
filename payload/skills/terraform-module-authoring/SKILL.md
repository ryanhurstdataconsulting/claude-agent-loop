---
name: terraform-module-authoring
description: Use when writing or reviewing a Terraform (or OpenTofu) module or root configuration — new infrastructure-as-code, a module missing standard variables/outputs/versions files, a remote-state backend that needs configuring, or a request to "review this Terraform plan before apply." Also load it when a repository needs a pre-merge policy gate (tfsec, checkov, OPA/Sentinel) wired against IaC changes, or when building a self-service catalog of reusable modules for other teams to consume. Triggers include "write a Terraform module for," "review this plan diff," "add a tfsec/checkov gate," and unpinned provider versions or missing remote-state configuration.
---

# terraform-module-authoring

## Overview
Authors and reviews Terraform/OpenTofu modules and root configurations
with a consistent structure, a safe remote-state setup, and a policy gate
that catches misconfiguration before `apply`. It owns both the *authoring
mechanics* (module layout, variable/output conventions, state backend) and
the *review discipline* (plan-diff scrutiny, static-analysis gating) that
keep infrastructure changes reviewable and reversible.

## When to use
- A new Terraform/OpenTofu module or root configuration is being written.
- An existing module is missing `variables.tf`, `outputs.tf`, or a pinned `versions.tf`.
- Remote state is stored locally, unversioned, or without state locking.
- A request to "review this plan" or "check this Terraform diff before we apply."
- Building a self-service module catalog other teams will consume, and it needs sane defaults plus guardrails rather than relying on tribal-knowledge review.
- Wiring a pre-merge static-analysis gate (tfsec, checkov, OPA/Sentinel) into a pipeline that touches IaC.

## Workflow

1. **Establish module structure** before writing resource blocks:
   - `main.tf` — resource and data-source definitions.
   - `variables.tf` — every input, typed, with a `description` and a
     sensible default only where a default is genuinely safe (never
     default a credential or a wide-open CIDR).
   - `outputs.tf` — only what a consumer of the module actually needs;
     do not leak internal implementation details as outputs.
   - `versions.tf` — pin the Terraform/OpenTofu version and every
     provider version with a constraint operator (`~>`), never left
     unconstrained. An unpinned provider is the single most common
     source of "it worked yesterday, it broke today" IaC incidents.

2. **Configure remote state** with locking enabled before the first
   `apply` — a local or unlocked backend is a footgun the moment more
   than one person or one CI job touches the same state. Use a
   backend that supports native locking (for example, an object-store
   backend with a locking table/mechanism) and enable state encryption
   at rest.

3. **Design for parameterized reuse when the module is shared** —
   sensible defaults for the common case, explicit overrides for the
   uncommon case, and validation blocks (`validate` on variables) that
   reject obviously wrong input at plan time rather than failing deep
   into `apply`. A module intended for a self-service catalog needs this
   discipline more than a one-off root config does — its failure mode is
   another team's midnight page, not just your own.

4. **Run `terraform plan` and read the diff before any `apply`.** The
   plan output is the built-in dry-run — treat an unreviewed plan as an
   unreviewed pull request. Specifically check for:
   - Any resource marked for **destroy-and-recreate** that the author
     did not intend (a common cause of unplanned downtime).
   - Any change to an IAM policy, security group, or network ACL —
     these deserve a second look regardless of how routine the rest of
     the diff is.
   - Drift between the plan and what the module's documented interface
     promises (an output changing type or disappearing).

5. **Wire a static-analysis gate before merge**, not before apply — catching
   a policy violation at PR time is cheaper than catching it after a plan
   has already been generated against real infrastructure:
   - `tfsec` or `checkov` for common misconfiguration patterns (public
     S3-equivalent buckets, unencrypted volumes, overly broad security
     group rules, missing MFA-delete, etc.).
   - OPA/Sentinel-style policy-as-code for organization-specific rules
     that static scanners don't cover out of the box (naming
     conventions, mandatory tags, allowed regions).
   - Gate on severity, not on every finding — an all-or-nothing gate on
     low-severity findings trains reviewers to ignore the gate entirely.

6. **Version and publish shared modules deliberately** — semantic-version
   tags on the module repository/registry entry, a changelog entry per
   breaking change, and a documented upgrade path when a required
   variable is added or an output is removed.

## Checklist / quality gate
- [ ] Module has `variables.tf`, `outputs.tf`, and a version-pinned `versions.tf` — no bare `main.tf` with everything inlined.
- [ ] Every variable is typed and described; no credential or overly-broad network range ships as a default.
- [ ] Remote state backend has locking and encryption-at-rest enabled.
- [ ] `terraform plan` has been generated and reviewed — no unexplained destroy-and-recreate, no unreviewed IAM/network-boundary change.
- [ ] A static-analysis gate (tfsec/checkov and, where applicable, an OPA/Sentinel policy) runs in CI against the diff and blocks merge on high/critical findings.
- [ ] Shared/catalog modules are version-tagged with a documented upgrade path for breaking changes.
- [ ] No resource in the plan is unowned by the change under review (no unrelated drift silently absorbed into this diff).

## References
- [Terraform documentation](https://developer.hashicorp.com/terraform/docs)
- [Terraform governance tooling comparison — OPA, Sentinel, Checkov, tfsec](https://www.env0.com/insights/terraform-governance-tools-compared-opa-sentinel-checkov-tfsec-and-when-to-use-each)
- [Open Policy Agent documentation](https://www.openpolicyagent.org/docs)

## Composition
Slots into the deploy stage `ci-pipeline-authoring` builds — the plan-check
and static-analysis gate described here become one or more CI stages in
that pipeline. Hands off to a cloud-architecture review (a
well-architected-style pass) for design-level questions this skill
doesn't own — module authoring covers *how* infrastructure is expressed
in code, not whether the target architecture itself is sound. Pairs with
an IAM least-privilege policy review whenever a module provisions roles
or trust relationships.
