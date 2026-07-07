---
name: iam-least-privilege-policy-authoring
description: Use when writing or reviewing IAM policies, roles, service accounts, or cross-account/cross-project trust relationships in a cloud environment. Triggers include a wildcard action or resource ("*") in a policy under review, a request to "tighten permissions" or "derive least privilege from actual usage," an overly broad admin role that needs to be split into scoped roles, a cross-account trust policy that may allow unintended public or third-party access, or an access-review/compliance finding calling out excessive permissions.
---

# iam-least-privilege-policy-authoring

## Overview
Authors or reviews identity and access management policies so that every principal — user, role, or service account — holds exactly the permissions it needs to do its job and no more. The one job it owns: turning either a set of required actions or a log of observed access into a scoped, minimal, auditable policy, and catching the wildcard grants and trust-policy mistakes that turn a single compromised credential into a full-environment breach.

## When to use
- Writing a new IAM policy, role, or service account for a workload.
- Reviewing an existing policy that uses a wildcard (`"Action": "*"`, `"Resource": "*"`) or an overly broad managed policy (for example, an administrator-access policy attached to a workload role).
- Deriving a scoped policy from observed access patterns (access-log or audit-trail history) rather than guessing at requirements up front.
- Splitting a single broad role used by multiple purposes into separate, purpose-scoped roles.
- Reviewing a cross-account or cross-project trust policy for unintended public or overly permissive access.
- Responding to an access-review or compliance finding that flags excessive standing permissions.

## Workflow
1. **Start from required actions, not from a convenient managed policy.** List the specific API calls the workload actually needs (for example, `s3:GetObject` on one bucket prefix, not a blanket storage-admin policy) before reaching for a broad built-in policy that happens to cover them.
2. **Derive from observed usage when the workload already runs.** Pull access-log or audit-trail history (for example, CloudTrail in AWS) over a representative time window and generate a policy scoped to actions actually exercised — this catches over-provisioning that a requirements-only approach would miss, but confirm the observation window covers any infrequent-but-legitimate action (a monthly batch job, an annual failover) before trimming it out.
3. **Scope every statement to the narrowest resource ARN/path/project that satisfies the requirement.** A policy scoped to `arn:aws:s3:::acme-uploads/*` is materially different from one scoped to `*` — never leave the resource field wildcarded when a specific resource, prefix, or tag-based condition would do.
4. **Lint for the two highest-risk patterns before anything else:** a wildcard `Action` combined with a wildcard `Resource` in the same statement (full-account-compromise blast radius from one leaked credential), and any `Effect: Allow` on `*:*`-shaped grants attached to a role a workload — not a human break-glass user — assumes.
5. **Use conditions to narrow further where policy language alone cannot.** Source-IP restrictions, MFA-required conditions on sensitive actions, and tag-based resource-matching (`aws:ResourceTag`) all reduce blast radius beyond what action/resource scoping achieves alone.
6. **Split broad roles by purpose, not by convenience.** A single "backend-service-role" used by five unrelated services means a compromise of any one service grants access to all five; separate the role per service or per trust boundary even when it means more roles to manage.
7. **Review cross-account and cross-project trust policies with extra scrutiny.** A trust policy's `Principal` field is the actual security boundary — verify it names a specific account/role ARN, not a wildcard, and that any external-ID or condition key required for third-party access is actually enforced, not merely documented.
8. **Prefer temporary, assumed credentials over long-lived access keys** wherever the platform supports it (role assumption, workload identity federation) — a long-lived key is a standing liability even when its policy is perfectly scoped.
9. **Document the rationale for any deliberately broad grant.** Sometimes a wildcard is genuinely correct (an audit role that must read all resource types for compliance scanning) — when that is the case, state why in the policy's accompanying documentation so a future reviewer does not flag it as a regression.

## Checklist / quality gate
- No statement combines a wildcard `Action` with a wildcard `Resource` unless explicitly justified and documented.
- Every resource-level permission is scoped to the narrowest ARN/path/project that satisfies the requirement, not the service's top-level namespace.
- Every cross-account/cross-project trust policy names a specific principal, not a wildcard, and enforces any required external-ID or condition key.
- Roles are split by purpose/trust-boundary rather than shared across unrelated workloads.
- Long-lived access keys are used only where role assumption or workload identity federation is genuinely unavailable, and that gap is noted.
- Where a policy is authored, a corresponding review pass exists (self-review at minimum) treating this as an author-then-audit two-step, matching how this skill is typically co-owned in practice.

## References
- AWS IAM best practices: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
- The same least-privilege principles apply, with platform-specific syntax, to Azure role-based access control and Google Cloud IAM — confirm the current condition-key and role-binding syntax for the target platform before authoring.

## Composition
Feeds the security pillar of `well-architected-review`. Pairs with `vpc-network-topology-design` when network-layer segmentation and identity-layer scoping need to work together as complementary controls. Typically authored by an infrastructure role and audited by a security-focused reviewer — treat authoring and review as two passes over the same artifact rather than skipping straight from draft to deploy.
