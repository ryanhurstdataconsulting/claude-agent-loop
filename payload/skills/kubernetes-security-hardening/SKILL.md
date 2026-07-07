---
name: kubernetes-security-hardening
description: Use when authoring or reviewing Kubernetes manifests, Helm charts, namespace/RBAC configuration, or a live cluster's security posture — setting up multi-tenant namespace isolation, writing NetworkPolicy and ResourceQuota objects, auditing Pod Security Standards compliance, or checking RBAC for over-broad permissions. Triggers include "harden this cluster," "review this manifest for security issues," a shared cluster with multiple teams needing isolation, a pod running as root or privileged, a missing default-deny NetworkPolicy, an RBAC ClusterRoleBinding granting cluster-admin to a service account, or an admission-controller (Kyverno/OPA Gatekeeper) policy gap.
---

# kubernetes-security-hardening

## Overview
Kubernetes security hardening covers both **authoring** a secure-by-default multi-tenant cluster configuration (namespace isolation, RBAC, quotas) and **auditing** existing manifests, Helm charts, or a live cluster against a security baseline. The one job it owns: making sure workloads on a shared cluster cannot see, starve, or escalate into each other, and that no manifest ships with an avoidable, checklist-catchable security gap.

## When to use
- Setting up a new namespace, tenant, or team boundary on a shared Kubernetes cluster.
- Writing or reviewing `NetworkPolicy`, `RBAC` (`Role`/`RoleBinding`/`ClusterRole`/`ClusterRoleBinding`), `ResourceQuota`, or `LimitRange` objects.
- A security review of a Kubernetes manifest, Helm chart, or live cluster configuration is requested before a workload goes to production.
- A pod spec runs as root, is privileged, mounts the host path or host network, or otherwise fails Pod Security Standards.
- An admission-controller (Kyverno, OPA Gatekeeper) policy set needs coverage gaps identified.
- A `ClusterRoleBinding` or wildcard RBAC rule (`resources: ["*"]`, `verbs: ["*"]`) is spotted anywhere in the manifest set.

## Workflow

### Mode 1 — Author (new namespace / tenant setup)
1. **One namespace per team or workload boundary**, not shared namespaces across teams. Namespace is the unit RBAC and quotas attach to; sharing one across tenants defeats isolation before any other control is applied.
2. **Default-deny the network first, then add explicit allows.** Every namespace gets a baseline `NetworkPolicy` that denies all ingress and egress by default; add narrowly scoped allow rules per actual traffic need (same-namespace, specific cross-namespace, egress to a known external endpoint). A namespace with no `NetworkPolicy` at all is fully open to every other pod on the cluster by default — treat that as a finding, not a neutral state.
3. **Generate least-privilege RBAC, not namespace-admin-by-default.** Scope `Role`/`RoleBinding` to the specific verbs and resources the team's workflow actually needs (e.g., `get`/`list`/`watch`/`update` on `deployments` in their own namespace) rather than granting a broad `edit` or `admin` `ClusterRole` because it's convenient. Verify with `kubectl auth can-i --as=<subject> <verb> <resource> -n <namespace>` before shipping.
4. **Size `ResourceQuota`/`LimitRange` to the tenant's actual workload**, not an arbitrary round number — undersizing causes evictions and pending pods; oversizing on a shared cluster lets one tenant starve the rest. On a cluster with a known fixed node count (for example, an 8-node shared cluster), size quotas against the cluster's real allocatable capacity divided across tenants, not against an assumed-infinite pool.
5. **Enforce Pod Security Standards at admission time**, not just by convention: set the namespace label for `restricted` (or `baseline` where a documented exception applies) rather than relying on developers to remember not to request `privileged: true`.

### Mode 2 — Audit (review an existing manifest, chart, or live cluster)
1. **Pod Security Standards compliance** — no `privileged: true`, no `hostPath` mounts without an explicit, documented justification, no `hostNetwork`/`hostPID`/`hostIPC`, `runAsNonRoot: true` set, read-only root filesystem where the workload allows it.
2. **Image provenance** — only signed/scanned images admitted; flag any `:latest` tag or unpinned digest reaching a production namespace (see `dockerfile-hardening` for the image-build-side half of this).
3. **NetworkPolicy presence** — confirm every namespace has a default-deny baseline; flag any namespace with zero `NetworkPolicy` objects as an open finding, not an assumption of "probably fine."
4. **RBAC over-permission audit** — scan for wildcard verbs/resources, `ClusterRoleBinding`s granting `cluster-admin` to a service account (a near-automatic critical finding), and `RoleBinding`s that outlive the workload they were created for.
5. **Admission-controller coverage** — check that Kyverno or OPA Gatekeeper policies actually cover what the audit just flagged manually; a manual finding that has no corresponding automated policy will recur on the next deploy.
6. **Severity-rank findings** and separate quick wins (add a missing `NetworkPolicy`, remove a wildcard RBAC rule) from structural rework (re-namespace a shared tenant boundary) so remediation can be sequenced.

## Checklist / quality gate
- [ ] Every namespace has a default-deny `NetworkPolicy` plus explicit, justified allow rules.
- [ ] RBAC is least-privilege and verified with `kubectl auth can-i`, not granted at `admin`/`cluster-admin` by convenience.
- [ ] No `ClusterRoleBinding` grants `cluster-admin` to a workload service account without a documented, time-bound exception.
- [ ] `ResourceQuota`/`LimitRange` sized against actual cluster capacity and tenant need, not a round guess.
- [ ] Pod Security Standards enforced at the namespace-label/admission level, not by convention alone.
- [ ] No pod runs privileged, as root, or with `hostPath`/`hostNetwork`/`hostPID` without a documented exception.
- [ ] Only signed/scanned, digest-pinned images admitted to production namespaces.
- [ ] Every manually flagged finding has a corresponding admission-controller policy, or a ticket to add one.

## References
- Kubernetes multi-tenancy documentation — https://kubernetes.io/docs/concepts/security/multi-tenancy/
- Kubernetes Pod Security Standards — https://kubernetes.io/docs/concepts/security/pod-security-standards/
- CIS Kubernetes Benchmark (verify current version before use)

## Composition
The author mode feeds directly into `golden-path-template-authoring` (a new service scaffold on a shared cluster should ship these defaults already applied) and into `self-service-iac-module-catalog` when namespace/RBAC setup is itself a self-service module. The audit mode pairs with `dockerfile-hardening` for the image-build half of supply-chain risk, and with `supply-chain-signing` for the "only signed images admitted" control. Feeds findings into `postmortem-generator` or `vulnerability-triage-and-disclosure` when an audit uncovers an active exposure rather than a latent gap.
