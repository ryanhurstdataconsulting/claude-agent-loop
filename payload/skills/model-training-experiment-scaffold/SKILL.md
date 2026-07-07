---
name: model-training-experiment-scaffold
description: Use when a task asks to stand up or extend a model-training run with experiment tracking — scaffolding a training script wired to MLflow or Weights & Biases, config-driven hyperparameters, checkpointing, and a reproducibility discipline. Triggers on requests like "set up a training pipeline," "add experiment tracking to this script," "make this run reproducible," or "compare these two training runs," and on symptoms like an unreproducible result, a lost hyperparameter configuration, or an untracked one-off training script.
---

# model-training-experiment-scaffold

## Overview
Scaffolds a training run so every run is reproducible, comparable, and
recoverable: config-driven hyperparameters instead of hardcoded values,
experiment tracking wired in from the first run, checkpointing, and a fixed
reproducibility contract (seed, data version, code version). Owns "make this
training run trustworthy and repeatable," distinct from choosing the model
architecture or the features it trains on.

## When to use
- A task asks to build a training script or pipeline for a new model.
- An existing training script hardcodes hyperparameters or lacks any run
  history — a request to "make runs comparable" or "add tracking."
- Two training runs produced different results from what looked like the
  same configuration, and the difference can't be explained.
- A model needs to resume from a checkpoint after an interrupted run.

## Workflow

1. **Move every hyperparameter and data reference into config, not code.**
   A YAML or structured config file (not command-line flags scattered
   across scripts) is the source of truth for a run:
   ```yaml
   seed: 42
   data_version: "2026-06-30"
   model:
     architecture: gradient_boosted_trees
     learning_rate: 0.05
     max_depth: 6
     n_estimators: 500
   training:
     batch_size: 256
     epochs: 50
     early_stopping_patience: 5
   ```
   The training script reads this config and logs it verbatim to the
   tracking system — never reconstruct the config from memory after the
   fact.

2. **Wire experiment tracking in before the first real run, not after
   results look promising.** Log, at minimum: the full config, code
   version (git commit SHA), data version, environment/dependency
   fingerprint, all metrics per epoch or step, and any produced artifacts
   (model weights, plots). MLflow and Weights & Biases both support this
   with a few lines:
   ```python
   import mlflow

   with mlflow.start_run():
       mlflow.log_params(config)
       mlflow.set_tag("git_sha", get_git_sha())
       mlflow.set_tag("data_version", config["data_version"])
       for epoch, metrics in train():
           mlflow.log_metrics(metrics, step=epoch)
       mlflow.log_artifact("model.pkl")
   ```

3. **Fix the reproducibility contract: seed, data version, code version.**
   All three must be captured for a run to be re-derivable:
   - Seed every source of randomness (framework, data shuffling, any
     stochastic layer) from the single config seed value.
   - Pin the data version (a snapshot ID, a partition date, or a content
     hash) — never train against a mutable "latest" view without recording
     which "latest" it was.
   - Record the code version as a git commit SHA, and refuse to log a run
     from a dirty working tree without flagging it in the tracked metadata.

4. **Checkpoint on a cadence that matches run cost, not a fixed default.**
   A cheap five-minute run may not need checkpointing at all; a multi-hour
   or multi-day run needs periodic checkpoints (by step or by wall-clock
   interval) plus a documented resume path that reloads optimizer state,
   not just model weights, so a resumed run is equivalent to an
   uninterrupted one.

5. **Make runs comparable, not just recorded.** Use a consistent metric
   naming scheme across runs so the tracking UI's comparison view is
   actually useful (`val_loss`, not `loss_val` in one run and
   `validation_loss` in another), and tag runs with a short description of
   what changed from the baseline.

## Checklist / quality gate
- [ ] Every hyperparameter and data reference lives in a versioned config
      file, not hardcoded in the training script.
- [ ] The tracking system logs config, git SHA, data version, and an
      environment fingerprint for every run — not just final metrics.
- [ ] A fixed seed is threaded through every source of randomness in the
      run.
- [ ] Checkpointing exists and has been exercised: a resumed run reaches
      equivalent results to an uninterrupted one.
- [ ] Metric names are consistent across runs so cross-run comparison in
      the tracking UI works without manual reconciliation.
- [ ] A run from a dirty (uncommitted-changes) working tree is flagged, not
      silently logged as if reproducible.

## References
- MLflow tracking documentation: https://mlflow.org/docs/latest/tracking.html
- Weights & Biases experiment-tracking documentation: https://docs.wandb.ai/
- "Machine Learning Engineer Skills" (MLflow/W&B for tracking and drift):
  https://doit.software/blog/machine-learning-engineer-skills

## Composition
- Consumes the output of **feature-engineering-pipeline** as its training
  input; version the feature set alongside the training config so a run is
  fully reproducible end to end.
- Hands off to **model-packaging-and-serving** once a tracked run produces
  a model worth promoting — carry the tracked run ID and artifact path
  forward into the packaging step.
- Feeds **eval-harness** — a completed training run's held-out evaluation
  should be logged back into the same tracking system as the run's
  promotion gate.
- Hands off to an MLOps model-registry-and-versioning practice when a
  tracked run is ready to move from experiment tracking into a governed
  registry with stage transitions (staging → production → archived).
