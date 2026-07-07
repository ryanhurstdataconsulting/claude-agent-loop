---
name: feature-engineering-pipeline
description: Use when a task asks to build, extend, or debug a reusable feature set for a machine-learning model — turning raw or warehouse data into point-in-time-correct model inputs. Triggers on requests like "build a feature pipeline," "add a feature to the training set," "why do train and serve disagree," feature-store integration (Feast, Tecton), and train/serve skew symptoms such as a model that performs well offline but degrades in production.
---

# feature-engineering-pipeline

## Overview
Scaffolds a reusable, point-in-time-correct feature transformation from raw
or warehouse data, and gives it a naming convention, a versioning scheme, and
a train/serve-skew checklist. Owns "turn data into trustworthy model input,"
distinct from choosing a model architecture or training a model.

## When to use
- A task asks to build a new feature set or feature-store transformation for
  a model, in training or at serving time.
- A model performs well in offline evaluation but degrades once it is
  serving live traffic — a classic train/serve-skew symptom.
- A feature needs to move from an ad hoc notebook computation into a
  pipeline other models can reuse.
- A task asks to integrate with a feature store (Feast, Tecton, or a
  vendor-managed equivalent) or to justify using a plain warehouse table
  instead.

## Workflow

1. **Decide feature-store vs. plain warehouse table before writing any
   transformation code.** A feature store earns its complexity when two or
   more models share the feature, when online (low-latency) serving is
   required, or when point-in-time correctness across many features is hard
   to hand-roll. A single model reading from a batch job is usually served
   fine by a plain versioned table.

2. **Design for point-in-time correctness from the start.** The single most
   common feature-pipeline bug is leaking future information into a
   historical training row. For any feature computed from an event stream,
   join on `event_timestamp <= feature_timestamp` (an as-of join), never a
   plain equi-join on entity key alone:
   ```sql
   -- as-of join: only use feature values known at or before the label's timestamp
   select
     l.entity_id,
     l.label_timestamp,
     f.feature_value
   from labels l
   left join features f
     on f.entity_id = l.entity_id
     and f.feature_timestamp <= l.label_timestamp
   qualify row_number() over (
     partition by l.entity_id, l.label_timestamp
     order by f.feature_timestamp desc
   ) = 1
   ```

3. **Name and version features so drift is traceable.** A convention like
   `<entity>_<aggregation>_<window>` (e.g., `user_purchase_count_7d`) plus an
   explicit version suffix when logic changes (`_v2`) lets a later
   investigation trace which feature definition produced which prediction.
   Never silently redefine a feature under the same name — bump the version.

4. **Write the train/serve-skew checklist into the pipeline, not just a
   doc:**
   - Same transformation code path (or a shared library) computes the
     feature both offline (training) and online (serving) — no
     reimplementation in two languages/systems without a parity test.
   - Null-handling and default values match between training and serving.
   - Feature freshness at serving time is bounded and known (a feature
     computed nightly should not silently serve 3-day-old values without
     the model being trained on that same staleness).
   - A canary comparison periodically diffs offline-computed vs.
     online-computed values for the same entity and flags divergence past a
     tolerance.

5. **Validate before handoff to training.** Run a data-quality pass (nulls,
   distribution shift vs. the last known-good version, cardinality for
   categorical features) before the feature is available for a training
   run — catching a broken feature after a model trains on it wastes an
   entire training cycle.

## Checklist / quality gate
- [ ] Feature-store-vs-table decision is explicit and justified, not
      defaulted.
- [ ] Every time-windowed feature uses a point-in-time (as-of) join, not a
      plain equi-join.
- [ ] Naming convention is consistent and any redefinition bumps a version
      suffix rather than mutating a name in place.
- [ ] The same transformation logic (or a tested-equivalent pair) computes
      the feature for both training and serving.
- [ ] A freshness bound and null-handling policy is documented and matches
      between training and serving.
- [ ] A data-quality check runs on the feature output before it is consumed
      by a training pipeline.

## References
- Feast documentation (open-source feature store): https://docs.feast.dev/
- Tecton feature-platform documentation: https://docs.tecton.ai/
- "Machine Learning Engineer Skills" (SQL for feature sets, feature-store
  integration): https://doit.software/blog/machine-learning-engineer-skills

## Composition
- Feeds **model-training-experiment-scaffold** — the feature pipeline's
  output is the training script's input; version both together.
- Shares its point-in-time-join and data-quality discipline with
  `data-quality-check-suite` and with a warehouse team's dbt-model-authoring
  practice when features live in a plain warehouse table rather than a
  dedicated feature store.
- Hands off to an MLOps feature-store-operationalization practice when a
  feature needs low-latency online serving shared across multiple models.
