---
name: model-registry-and-versioning-setup
description: Use when a project trains models with no central place to track which version is deployed where — task phrasings like "we don't have a model registry," "set up MLflow/SageMaker/Vertex model versioning," "which model version is actually in production right now?," or "add lineage tracking so we know what data and code produced this model." Configures a registry with an explicit stage-transition workflow (staging → production → archived) and lineage tags (data version, code commit, hyperparameters, training-run ID). Distinct from experiment tracking, which logs many candidate runs — this skill governs the smaller set of versions promoted toward production.
---

# model-registry-and-versioning-setup

## Overview
Configures a model registry — the system of record for which model version is
staged, which is in production, and what produced each one. It owns the
version-naming scheme, the stage-transition workflow, and lineage tagging; it
does not own experiment tracking (the many-candidate-runs firehose) or the
deploy mechanics that consume a registered version.

## When to use
- A team cannot answer "which model version is live in production right now"
  without checking a deploy script or asking a person.
- Models are versioned informally (`model_v2_final_ACTUALLY_final.pkl`) or
  overwritten in place with no history.
- A `mlops-ci-cd-pipeline-setup` pipeline needs a `register` stage to write
  to.
- An incident requires rolling back to "whatever was deployed two weeks ago"
  and there is no reliable way to identify or fetch it.
- Compliance or audit requirements demand knowing exactly what data, code, and
  hyperparameters produced a given production model.

## Workflow

1. **Pick the registry platform by where the model already lives, not by
   preference.** Decision guide:
   - Already training in a managed cloud environment (SageMaker, Vertex AI,
     Azure ML) → use that platform's native registry first; it is already
     wired to the platform's deploy and IAM surfaces.
   - Self-hosted, multi-cloud, or platform-agnostic → MLflow Model Registry,
     backed by a database (Postgres) for metadata and object storage (S3-
     compatible or equivalent) for artifacts.
   - Do not stand up a second registry alongside a platform-native one
     "for flexibility" — that produces two sources of truth, which is the
     exact failure mode this skill exists to prevent.

2. **Define the stage-transition workflow before registering anything.**
   The canonical three stages are `staging → production → archived`, with an
   explicit rule for who or what can move a version between them:
   - `None → Staging`: automatic, on a passing eval gate (see
     `mlops-ci-cd-pipeline-setup`).
   - `Staging → Production`: gated — either a required human approval or a
     passing canary/shadow period, never silent.
   - `Production → Archived`: automatic when a newer version reaches
     `Production`, but the artifact itself is retained, not deleted — a
     rollback target must still resolve.

   MLflow example:
   ```python
   import mlflow
   from mlflow import MlflowClient

   client = MlflowClient()
   mv = mlflow.register_model(
       model_uri=f"runs:/{run_id}/model",
       name="churn-classifier",
   )
   client.set_model_version_tag(mv.name, mv.version, "data_version", "2026-06-01")
   client.set_model_version_tag(mv.name, mv.version, "code_commit", commit_sha)
   client.transition_model_version_stage(
       name=mv.name, version=mv.version, stage="Staging"
   )
   ```

3. **Version by immutable, traceable identifiers — never by a mutable
   filename.** Every registered version must carry:
   - The training-run ID (links back to the experiment-tracking system).
   - The exact code commit SHA that produced it.
   - The data version or snapshot identifier used for training (a table
     partition, a dataset hash, or a feature-store timestamp).
   - The hyperparameter set, either inline as tags or by reference to the
     training-run's logged config.

   Prefer the registry's built-in incrementing version number
   (`churn-classifier` version `7`) over a hand-assembled semver string —
   semver implies compatibility guarantees a model rarely has, and a bare
   incrementing integer is simpler to reconcile against a deploy log.

4. **Tag lineage at registration time, not after the fact.** Retrofitting
   lineage tags onto already-registered versions is a common cleanup task and
   a sign the registration script is missing a step — wire the tags into the
   same call that registers the model so the two can never drift apart.

5. **Decide retention policy explicitly.** Unbounded retention of every
   registered version, including ones that never left `Staging`, silently
   grows storage cost. A reasonable default: retain every version that ever
   reached `Production` indefinitely (or per the organization's audit
   window); prune `Staging`-only versions older than a fixed window (for
   example, 90 days) unless tagged `keep`.

## Checklist / quality gate
- [ ] Exactly one registry is the source of truth — no parallel informal
      versioning (filenames, spreadsheet trackers) survives after setup.
- [ ] Every registered version carries data version, code commit, and
      training-run ID tags at registration time.
- [ ] The stage-transition workflow has an explicit, documented rule for who
      or what can promote `Staging → Production` — not left implicit.
- [ ] "Which model version is live in production" is answerable with a
      single registry query, not tribal knowledge.
- [ ] A retired (`Archived`) version's artifact is still fetchable — retention
      policy does not delete anything a rollback might need.

## References
- Interview Kickstart, "MLOps Engineer Skills" — https://interviewkickstart.com/skills/mlops-engineer
- Brolly AI, "MLOps Roles and Responsibilities" — https://brollyai.com/mlops-roles-and-responsibilities/
- MLflow Model Registry documentation — https://mlflow.org/docs/latest/model-registry.html

## Composition
- Feeds the `register` stage of `mlops-ci-cd-pipeline-setup` — that skill
  scaffolds the surrounding pipeline; this skill owns what happens at the
  register step.
- Consumes the output of a `model-training-experiment-scaffold`-style
  training run (run ID, metrics, artifact path) as its registration input.
- Feeds `model-drift-monitoring-setup`, which needs the currently-`Production`
  version identifier to know what it is monitoring and what a retrain would
  be promoted against.
