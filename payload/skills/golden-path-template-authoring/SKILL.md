---
name: golden-path-template-authoring
description: Use when asked to create a paved-road, golden-path, or "starter template" for a new microservice, database, batch job, or frontend app, or when standing up a software-template catalog entry that other teams will self-serve from. Triggers include "scaffold a new service template," "add a golden path for X," a Backstage/Spotify-style software-template request, or a platform team asking for security and reliability defaults to be pre-wired into every new repo instead of bolted on after launch.
---

# golden-path-template-authoring

## Overview
Golden-path template authoring produces an opinionated, batteries-included starter that a product team scaffolds a new service from — repo layout, CI pipeline, infrastructure-as-code module reference, and catalog registration, with security and reliability defaults pre-wired rather than left to the requesting team to reinvent. The one job it owns: turning "spin up a new service the right way" into a single scaffold command that a team cannot easily get wrong.

## When to use
- A platform or developer-experience team is asked to add a new paved road (service, database, scheduled job, frontend app) to the internal catalog.
- An existing template is missing a default that keeps surfacing as a post-launch fix (no SLO stub, no non-root Dockerfile, no least-privilege IAM role).
- A team's onboarding time for "get a new service to first deploy" is longer than the platform team wants, and the root cause is every team re-solving the same setup from scratch.
- A request to align disparate one-off service scaffolds ("every team built their own copy-pasted starter") into one maintained template.

## Workflow
1. **Scope the template to one workload shape.** A "new microservice" template and a "new scheduled batch job" template are different templates — do not try to build one template that branches into five shapes via prompts; that pattern rots. Confirm the target workload shape and its language/framework before scaffolding.
2. **Lay out the repo skeleton.** Standard layout for the language/framework, a `README` stub with the paved-road's intended use, and placeholders clearly marked `TODO` so the generated repo is honest about what still needs filling in — never generate silently-wrong boilerplate.
3. **Wire the CI pipeline by default**, not as a follow-up ticket: lint → test → build → deploy stages, with dependency caching and secrets pulled from the platform's native secret store. Hand this stage off to `ci-pipeline-authoring` rather than reinventing pipeline YAML conventions inline.
4. **Bake in security and reliability defaults up front** — these are the details teams skip under deadline pressure if left optional:
   - A hardened base Dockerfile (non-root user, pinned digest, multistage build).
   - A least-privilege IAM/service-account role scoped to only what the template's own resources need.
   - An SLO stub (a starter set of SLIs and a placeholder target) so reliability is a decision made at day one, not retrofitted after the first incident.
   - A default-deny network policy or security-group baseline for anything that talks over the network.
5. **Reference the IaC module, don't inline it.** The template should call into the organization's published, versioned infrastructure module (see `self-service-iac-module-catalog`) rather than embedding a bespoke copy of Terraform/Crossplane resources that drifts from the maintained version.
6. **Register the catalog entry.** Generate the software-catalog metadata (ownership, dependencies, links) alongside the code — see `backstage-catalog-entity-authoring` — so a scaffolded service is discoverable the moment it exists, not after a manual follow-up.
7. **Verify the template scaffolds a working service.** Run the template end to end: does a freshly scaffolded repo pass its own generated CI on the first commit? A template that fails its own pipeline is worse than no template — it teaches teams to distrust the paved road.
8. **Version the template and publish a changelog entry** on any breaking change to the generated output, so already-scaffolded services know when they have drifted from the current paved road.

## Checklist / quality gate
- [ ] Scoped to exactly one workload shape; no branching mega-template.
- [ ] CI pipeline present and green on a fresh scaffold, not left as a follow-up task.
- [ ] Non-root, pinned-digest Dockerfile (or language-equivalent hardened build) included by default.
- [ ] Least-privilege role/service-account generated, not a broad admin credential.
- [ ] An SLO stub exists, even if the target itself needs a human sign-off.
- [ ] IaC referenced from the shared module catalog, not inlined and forked.
- [ ] Catalog entry (ownership, dependencies) generated alongside the code.
- [ ] Template version bumped and changelog entry written for any breaking change.

## References
- Red Hat, "Golden paths" — https://www.redhat.com/en/topics/platform-engineering/golden-paths
- Backstage software templates documentation — https://backstage.io/docs/features/software-templates/

## Composition
Feeds into `backstage-catalog-entity-authoring` for the catalog-registration step and `self-service-iac-module-catalog` for the infrastructure reference. Pulls in `ci-pipeline-authoring` for the build/deploy stages, `slo-error-budget-definition` for the reliability stub, and `kubernetes-security-hardening` when the workload runs on a shared cluster. Pairs with `dockerfile-hardening` for the Dockerfile default.
