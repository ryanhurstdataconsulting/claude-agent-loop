---
name: gitops-deployment-setup
description: Use when moving a service's deployment from imperative `kubectl apply`/`helm upgrade` runs to a GitOps model, or when configuring Argo CD or Flux for a cluster — "move this service to GitOps," "set up Argo CD/Flux for this repo," a cluster that has drifted from what's declared in git, or a rollback that needs to happen by reverting a commit instead of hand-editing a live resource. Produces a repo structure (app-of-apps or per-team), an explicit sync policy per environment, drift-detection alerting, and a git-revert rollback path, rather than leaving deployment as ad hoc imperative commands. Also triggers on "why did this cluster drift from git," "our rollback is a manual kubectl patch," or setting up secrets management for a GitOps repo.
---

# gitops-deployment-setup

## Overview
Establishes git as the single source of truth for a cluster's desired state,
with an operator (Argo CD or Flux) continuously reconciling the live cluster
toward it. The one job it owns: every deployment and every rollback goes
through a git commit, never a direct, unrecorded mutation of the cluster.

## When to use
- A service's deployments are currently a sequence of manual `kubectl
  apply`/`helm upgrade` commands with no audit trail.
- A team wants to adopt Argo CD or Flux and needs the repo structure,
  sync policy, and bootstrap path designed, not just the tool installed.
- The cluster has drifted from what's declared in git and there's no
  alerting to catch it next time.
- A past incident's root cause was an untracked manual change (`kubectl
  edit`/`kubectl patch`) that nobody could reconstruct afterward.
- Rollback currently means someone remembers what the old config was and
  hand-types it back in.

## Workflow
1. **Choose the repo topology first — it drives everything else.**
   - **App-of-apps (Argo CD)** or a single **Flux Kustomization tree**: one
     root manifest that references per-service/per-team child manifests.
     Good default for a small-to-mid number of services under one platform
     team.
   - **Per-team repos**: each team owns its manifests repo; the platform
     team's root config only references team repo URLs. Better blast-radius
     isolation when teams have different release cadences or trust levels.
   - Decision factors: number of teams and services, how much blast-radius
     isolation matters, and whether an existing monorepo/polyrepo split
     already constrains the choice.
2. **Structure manifests per environment with overlays, not branches.**
   Use Kustomize `base/` + `overlays/dev|staging|prod/` (or Helm charts with
   per-environment `values-<env>.yaml`). A long-lived branch per environment
   drifts and merge-conflicts in ways overlays don't.
3. **Set an explicit sync policy per environment — don't leave it implicit.**
   ```yaml
   # Argo CD Application, lower environment
   syncPolicy:
     automated:
       prune: true      # remove resources deleted from git
       selfHeal: true    # revert manual cluster drift automatically
     syncOptions:
       - CreateNamespace=true
   ```
   For production, either gate sync on manual approval, or keep it
   automated but pair it with a progressive-delivery strategy (canary/blue-
   green via Argo Rollouts or Flagger) so `selfHeal` doesn't instantly
   redeploy a bad revision to 100% of traffic.
4. **Wire drift-detection alerting.** Argo CD: alert on `OutOfSync` status
   via its notifications controller. Flux: alert via the
   `notification-controller`'s `Alert`/`Provider` resources, or poll `flux
   get kustomizations` in a scheduled check. Drift with no alert is
   indistinguishable from no drift detection at all.
5. **Make rollback a `git revert`, not a live patch.** Document (and, where
   possible, enforce via RBAC) that GitOps-managed resources are never
   edited with `kubectl edit`/`kubectl patch`/`helm upgrade` directly — with
   `selfHeal` on, the operator reverts the manual change anyway; with it
   off, the manual change silently drifts from git until the next sync.
   The rollback runbook is: revert the offending commit, confirm the
   operator reconciles, done.
6. **Encrypt secrets before they touch the repo.** Plaintext secrets never
   go into a GitOps repo. Use Sealed Secrets, the External Secrets
   Operator (pulling from a real secret store at sync time), or SOPS-
   encrypted values committed alongside the manifests.
7. **Document the bootstrap path.** How does the operator itself get
   installed and pointed at the repo — an Argo CD root `Application`
   manifest applied once by hand, or `flux bootstrap github --owner=... 
   --repository=...`? This is the one step that is legitimately imperative;
   everything downstream of it should not be.

## Checklist / quality gate
- [ ] Repo topology (app-of-apps, single tree, or per-team repos) matches
      the number of teams/services and the blast-radius tolerance —
      decided deliberately, not defaulted.
- [ ] Environments are split by overlay/values, not by long-lived branch.
- [ ] Sync policy is explicit per environment: automated with
      prune/selfHeal for lower environments, gated or progressive-delivery-
      backed for production.
- [ ] Drift-detection alerting is wired to a real notification channel, not
      just visible on a dashboard nobody watches.
- [ ] No documented or scripted path exists for imperative mutation of a
      GitOps-managed resource.
- [ ] All secrets in the repo are encrypted at rest (Sealed Secrets, SOPS,
      or an External Secrets Operator reference) — never plaintext.
- [ ] The rollback runbook is "git revert, confirm reconciliation" and has
      been exercised at least once.
- [ ] The operator's own bootstrap/install path is documented.

## References
- [Argo CD documentation](https://argo-cd.readthedocs.io/)
- [Flux documentation](https://fluxcd.io/flux/)
- [Kustomize documentation](https://kubectl.docs.kubernetes.io/references/kustomize/)
- [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets), [SOPS](https://github.com/getsops/sops)
- [Argo Rollouts](https://argo-rollouts.readthedocs.io/), [Flagger](https://fluxcd.io/flagger/) for progressive delivery on top of a GitOps sync

## Composition
Bakes into `golden-path-template-authoring` as the default deployment path
for new services. Pairs with `progressive-delivery-rollout` for the canary
or blue-green strategy sitting on top of the sync policy, and with
`terraform-module-authoring` for the cluster infrastructure underneath the
GitOps layer. Run `secrets-scanning-remediation` against the GitOps repo
before first commit to confirm nothing plaintext slipped in. A bad rollout
caught by drift alerting feeds `postmortem-generator`.
