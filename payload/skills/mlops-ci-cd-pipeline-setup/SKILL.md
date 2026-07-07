---
name: mlops-ci-cd-pipeline-setup
description: Use when a repository needs continuous integration and deployment wired specifically for a trained-model artifact rather than an application binary — task phrasings like "set up CI/CD for model training and deployment," "add an eval gate before we promote a model," "the last model regressed in production and nobody caught it," or "wire training to auto-deploy to staging." Scaffolds a train-to-eval-gate-to-registry-to-deploy pipeline with automated rollback on gate failure and environment promotion (dev/staging/production). Distinct from generic application CI/CD in that the pipeline's primary artifact is a model plus its metrics, not just a build.
---

# mlops-ci-cd-pipeline-setup

## Overview
Scaffolds a CI/CD pipeline whose stages are shaped around a model's lifecycle —
train, evaluate against a gate, register, deploy, and monitor — instead of the
generic build-test-deploy shape used for application code. It owns the
stage-gate-promote wiring and the automated-rollback trigger; it hands off the
registry mechanics and the serving container to sibling skills.

## When to use
- A repository trains a model but has no automated path from a training run to
  a served endpoint.
- A team asks for "CI for our model" or "a pipeline that blocks promotion if
  accuracy drops."
- A prior model regression shipped to production undetected — the request is
  usually phrased as wanting a gate that would have caught it.
- An existing pipeline retrains on a schedule but promotes every run
  unconditionally, with no evaluation checkpoint.
- A multi-environment ML platform (dev/staging/production) needs an explicit
  promotion path between them, not manual artifact copying.

## Workflow

1. **Map the stages before writing any YAML.** The canonical shape is:
   `train → evaluate (gate) → register → deploy → monitor`. Confirm which
   stages already exist informally (a notebook, a cron job) versus which need
   to be built from scratch — do not assume a greenfield pipeline.

2. **Design the eval gate first, not last.** The gate is the pipeline's most
   important decision point: it is the difference between "CI that runs
   training" and "CI that protects production." Define, before scaffolding
   any stage config:
   - The metric(s) and their promotion threshold (for example, `accuracy >=
     baseline - 0.5pp`, or `AUC >= 0.80`).
   - The comparison baseline — the currently deployed model's held-out
     score, not a fixed constant, so the gate adapts as the model improves.
   - What happens on gate failure: the pipeline must fail loudly (non-zero
     exit, a blocked deploy step) and never silently promote a worse model.

3. **Scaffold the pipeline as explicit, ordered jobs with artifact
   hand-off.** Each stage should consume the previous stage's declared
   artifact, not re-derive it. Minimal GitHub Actions shape:

   ```yaml
   jobs:
     train:
       steps:
         - run: python train.py --output model.pkl --metrics metrics.json
         - uses: actions/upload-artifact@v4
           with: { name: candidate-model, path: "model.pkl metrics.json" }

     evaluate:
       needs: train
       steps:
         - uses: actions/download-artifact@v4
           with: { name: candidate-model }
         - run: python eval_gate.py --metrics metrics.json --min-auc 0.80
           # non-zero exit here halts the pipeline — no `continue-on-error`

     register:
       needs: evaluate
       steps:
         - run: python register_model.py --stage staging

     deploy-staging:
       needs: register
       environment: staging
       steps:
         - run: ./deploy.sh --env staging --model-version "${{ needs.register.outputs.version }}"

     deploy-production:
       needs: deploy-staging
       environment: production   # gated by required reviewers, not automatic
       steps:
         - run: ./deploy.sh --env production --model-version "${{ needs.register.outputs.version }}"
   ```

   Route the model-registry stage to `model-registry-and-versioning-setup` and
   the container/serving stage to a model-packaging skill rather than
   reinventing either inline here.

4. **Wire the rollback trigger, not just the forward path.** On a
   production-deploy failure or a post-deploy health-check failure, the
   pipeline must be able to re-point traffic at the last known-good model
   version automatically — do not rely on a human noticing a dashboard.
   Prefer keeping the previous version's serving artifact warm (blue/green or
   canary) over a cold redeploy, since a cold rollback under incident pressure
   is itself a risk.

5. **Promote by reference, never by rebuild.** The exact artifact evaluated
   in the gate must be the one deployed — retraining between stages
   reintroduces the train/serve skew and non-determinism the pipeline exists
   to prevent. Pin the artifact by its registry version or content hash at
   every downstream stage.

6. **Environment parity check.** Before wiring `deploy-production`, verify
   the staging environment's feature source, library versions, and hardware
   (CPU/GPU) match production closely enough that a staging pass is
   predictive. A gate that passes in a mismatched staging environment is a
   false signal, not a safety net.

7. **Decide human-in-the-loop boundaries explicitly.** Auto-promote
   dev → staging is usually safe to fully automate. Staging → production
   should almost always keep a required-reviewer gate or a canary/shadow
   period — treat "should this ship to production automatically" as a policy
   decision for the team to confirm, not a default the agent should pick
   silently.

## Checklist / quality gate
- [ ] Every stage consumes an explicit upstream artifact (no silent retrain
      between train and deploy).
- [ ] The eval gate compares against the live baseline's score, not a
      hardcoded constant, and a gate failure halts promotion with a non-zero
      exit.
- [ ] A rollback path exists and has been exercised (manually triggered at
      least once) before the pipeline is trusted for unattended runs.
- [ ] Staging and production environments are close enough in feature source
      and dependency versions that a staging pass is meaningful.
- [ ] Production promotion has an explicit human-in-the-loop boundary (review
      gate, canary window, or documented full-auto decision) that the team
      signed off on.
- [ ] Secrets (registry credentials, deploy tokens) are injected via the CI
      platform's native secret store, never hardcoded in pipeline YAML.

## References
- ml-ops.org, "MLOps Principles" — https://ml-ops.org/content/mlops-principles
- devopsschool.com, "MLOps Engineer Role Blueprint" — https://www.devopsschool.com/blog/mlops-engineer-role-blueprint-responsibilities-skills-kpis-and-career-path/
- Interview Kickstart, "MLOps Engineer Skills" — https://interviewkickstart.com/skills/mlops-engineer

## Composition
- Pairs with `model-registry-and-versioning-setup` for the register stage —
  this skill scaffolds the pipeline shell; the registry skill owns the
  version/lineage mechanics inside it.
- Hands off the model-packaging/container step to a model-serving packaging
  skill when the deploy stage needs a Dockerfile or a Kubernetes manifest.
- Shares its stage-gate-promote pattern with `dbt-ci-cd-pipeline-setup` (same
  shape, different artifact type — a dbt model versus a trained model); reuse
  the general `ci-pipeline-authoring` skill for the underlying CI-platform
  mechanics (caching, runner selection, secret wiring) rather than
  re-deriving them here.
- Feeds `model-drift-monitoring-setup` once a model is live — the monitoring
  skill's retrain-trigger checklist should loop back into this pipeline's
  `train` stage.
