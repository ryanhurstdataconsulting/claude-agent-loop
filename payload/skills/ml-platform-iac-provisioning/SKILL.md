---
name: ml-platform-iac-provisioning
description: Use when a platform team needs infrastructure-as-code for shared ML infrastructure — a model registry, an experiment-tracking server, a serving cluster, or a feature store's backing services — rather than for a single application. Triggers include "write Terraform for our MLflow tracking server," "provision a model-serving cluster," "we're clicking this ML infra together by hand in the console," or "set up GitOps for our ML platform." Scaffolds Terraform (or OpenTofu) modules for common ML-platform components and an environment-parity checklist, distinct from application-level infrastructure-as-code.
---

# ml-platform-iac-provisioning

## Overview
Scaffolds infrastructure-as-code for the shared components of an ML
platform — tracking servers, model registries, serving clusters, and the
storage/database backends they depend on — so platform teams stop
provisioning ML infrastructure by hand in a cloud console. It owns the
Terraform module structure and environment-parity checking; it does not own
the application code that runs on top of the provisioned infrastructure.

## When to use
- An ML platform's infrastructure (tracking server, registry, serving
  cluster) exists only as manually-clicked cloud-console resources with no
  code behind it.
- A new environment (staging, a second region) needs to replicate an
  existing ML platform setup and there is no module to reuse.
- A team is standing up MLflow, a feature store's backing database, or a
  Kubernetes-based serving cluster for the first time.
- An audit or disaster-recovery review asks "can we rebuild the ML platform
  from code," and the honest answer is no.

## Workflow

1. **Identify which ML-platform components actually need dedicated
   infrastructure before writing modules for all of them.** Common
   components, each provisioned only if the team has chosen that piece of
   the stack:
   - **Tracking/registry server** (MLflow or equivalent): compute (a small
     managed service or container) plus a metadata database (Postgres) plus
     artifact storage (object storage bucket).
   - **Serving cluster**: a Kubernetes namespace with autoscaling, or a
     managed model-endpoint service, sized for the expected inference QPS
     and latency SLO.
   - **Feature-store backing services**: an online store (managed
     key-value/cache service) and access to the existing warehouse for the
     offline store — see `feature-store-operationalization` for the
     feature-store-specific design, this skill only provisions its backing
     infrastructure.
   - Do not provision a component the team has not chosen a framework for
     yet — infrastructure-as-code for an undecided tool locks in a decision
     prematurely.

2. **Structure each component as its own reusable module with explicit
   variables, not a single monolithic root configuration.** Minimal shape
   for a tracking-server module:

   ```hcl
   # modules/mlflow-tracking-server/variables.tf
   variable "environment"        { type = string }
   variable "instance_size"      { type = string, default = "small" }
   variable "artifact_bucket_name" { type = string }
   variable "db_instance_class"  { type = string, default = "db.t3.micro" }

   # modules/mlflow-tracking-server/main.tf
   resource "aws_db_instance" "mlflow_metadata" {
     identifier        = "mlflow-${var.environment}"
     instance_class    = var.db_instance_class
     engine            = "postgres"
     # ... storage, backup retention, encryption per org baseline
   }

   resource "aws_s3_bucket" "mlflow_artifacts" {
     bucket = var.artifact_bucket_name
   }
   ```

   Consume the module per environment (`environment = "staging"`,
   `environment = "production"`) rather than duplicating the resource
   blocks — the module boundary is what makes environment parity checkable
   in step 4.

3. **Pin provider and module versions.** An unpinned provider version is the
   most common source of "it worked yesterday" drift in ML-platform infra —
   pin explicitly:

   ```hcl
   terraform {
     required_providers {
       aws = { source = "hashicorp/aws", version = "~> 5.0" }
     }
   }
   ```

4. **Environment-parity checklist** — run before treating staging as
   predictive of production:
   - [ ] Staging and production consume the same module with only variable
         values differing (instance size, replica count) — not forked copies
         of the module itself.
   - [ ] Database engine version, major library versions on the serving
         image, and GPU/CPU architecture match between environments where the
         model's behavior could depend on them.
   - [ ] Network topology (VPC, security groups, service mesh policy) is
         structurally the same, differing only in CIDR ranges/scale, so a
         staging connectivity test is a valid predictor of production.

5. **Wire a policy gate before merge.** Run `tfsec` or `checkov` (or an
   organization's OPA/Sentinel policy) against every ML-platform module
   change — these modules commonly provision databases and storage buckets
   holding model artifacts and training data, so unencrypted-storage or
   overly-broad IAM findings here carry real risk. Route this to the general
   `terraform-module-authoring` skill's policy-gate workflow rather than
   hand-rolling a separate check.

6. **Plan GitOps hand-off for the deploy side, not the infra side.** Terraform
   provisions the cluster and the tracking server; the actual model
   *deployments* onto that cluster are better handled by a GitOps
   controller (ArgoCD or Flux) watching the `mlops-ci-cd-pipeline-setup`
   pipeline's deploy manifests — do not try to make Terraform itself the
   mechanism for every model rollout, that conflates infrequent
   infrastructure changes with frequent model deploys.

## Checklist / quality gate
- [ ] Every provisioned component maps to a framework the team has actually
      chosen — nothing speculative.
- [ ] Each component is a reusable module consumed per environment via
      variables, not duplicated resource blocks.
- [ ] Provider and module versions are pinned.
- [ ] The environment-parity checklist passes for staging versus production.
- [ ] A policy gate (`tfsec`/`checkov`/OPA) runs on every module change
      before merge.
- [ ] Model deployment onto the provisioned infrastructure is handled by a
      GitOps or CI/CD flow, not treated as a Terraform apply on every model
      version.

## References
- Interview Kickstart, "MLOps Engineer Skills" (Terraform for IaC, ArgoCD or
  Flux for GitOps) — https://interviewkickstart.com/skills/mlops-engineer

## Composition
- Delegates general Terraform module hygiene (standard variables/outputs
  files, remote-state backend, the policy-gate mechanics) to
  `terraform-module-authoring`; this skill adds the ML-platform-specific
  component catalog and environment-parity checklist on top.
- Provisions the infrastructure that `model-registry-and-versioning-setup`
  configures at the application layer, and that
  `mlops-ci-cd-pipeline-setup`'s deploy stage targets.
- Provisions the backing services `feature-store-operationalization` needs
  (online store, database) without owning the feature-store-specific setup
  itself.
