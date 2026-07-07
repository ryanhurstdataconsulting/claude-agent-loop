---
name: feature-store-operationalization
description: Use when multiple models need the same engineered features computed consistently, or when a model's online (serving-time) predictions do not match its offline (training-time) results — task phrasings like "set up a feature store," "we're recomputing the same features in three different pipelines," "our online predictions don't match training," or "add Feast/Tecton to the platform." Provides a decision guide for online versus offline feature stores, a setup scaffold, and a point-in-time join-correctness checklist. Distinct from a single model's feature-engineering pipeline — this skill covers the shared, multi-consumer feature layer.
---

# feature-store-operationalization

## Overview
Operationalizes a feature store — a shared layer that computes features once
and serves them consistently to both training (offline, historical) and
inference (online, low-latency) consumers. It owns the online/offline store
decision, the point-in-time correctness guarantee, and the setup scaffold; it
does not own any single model's feature-transformation logic.

## When to use
- Two or more models or teams independently recompute the same or near-same
  features, and the definitions have started to drift.
- A model's live predictions diverge from what training data suggested they
  should be (classic train/serve skew), traced back to features computed
  differently at training time versus request time.
- A new low-latency serving path needs features that today only exist as
  slow batch/warehouse tables.
- A platform team is asked to "add Feast" or "add Tecton" without an existing
  feature store in place.

## Workflow

1. **Decide online versus offline store need — most projects need both, not
   one.**
   - **Offline store**: historical feature values for training, typically
     the existing warehouse/lakehouse (BigQuery, Snowflake, Parquet on
     object storage). If training-set construction already works
     acceptably, do not replace this — a feature store's offline side is
     often "the warehouse plus a registration layer," not a new database.
   - **Online store**: low-latency (single-digit-millisecond to low
     double-digit) key-value lookups at inference time — Redis, DynamoDB,
     or a feature-store vendor's managed equivalent. Only needed when a
     model serves synchronous, latency-sensitive requests; a batch-scored
     model has no online-store requirement at all.
   - Skip the online store entirely for batch-only inference — standing one
     up unused is wasted operational surface.

2. **Pick a feature-store framework by team size and existing infrastructure,
   not by feature list.**
   - Small team, already on a warehouse, wants a lightweight open-source
     layer → Feast (open-source, warehouse-native offline store, pluggable
     online store).
   - Larger org wanting a managed, opinionated platform with built-in
     monitoring and transformation orchestration → a managed vendor
     (Tecton or a cloud-native equivalent).
   - Do not adopt a heavyweight managed platform to serve two features for
     one model — the operational overhead outweighs the benefit until there
     are several models sharing a real feature surface.

3. **Define entities and feature views before writing transformation code.**
   Feast example:

   ```python
   from feast import Entity, FeatureView, Field, FileSource
   from feast.types import Float32, Int64
   from datetime import timedelta

   customer = Entity(name="customer_id", join_keys=["customer_id"])

   customer_source = FileSource(
       path="s3://feature-data/customer_features.parquet",
       timestamp_field="event_timestamp",
   )

   customer_features = FeatureView(
       name="customer_features",
       entities=[customer],
       ttl=timedelta(days=90),
       schema=[
           Field(name="avg_order_value_30d", dtype=Float32),
           Field(name="days_since_last_order", dtype=Int64),
       ],
       source=customer_source,
   )
   ```

   Name features with an explicit aggregation window in the name
   (`avg_order_value_30d`, not `avg_order_value`) — an ambiguous name is the
   single most common source of duplicate, silently-diverging feature
   definitions.

4. **Point-in-time join correctness is the load-bearing guarantee — verify it
   explicitly, do not assume the framework handles it silently.** When
   building a training set, every feature value must reflect what was known
   *as of* the label's timestamp, not the feature's current value —
   otherwise the model trains on information it would not have had at
   prediction time (label leakage). Checklist:
   - [ ] The training-set builder does a time-travel / point-in-time join
         (Feast's `get_historical_features`, or an equivalent `AS OF`
         join), not a naive join against the latest feature snapshot.
   - [ ] Feature TTLs are set to reflect real staleness tolerance — a `ttl`
         too long silently serves stale features at inference time; a `ttl`
         too short serves nulls for infrequently-updated entities.
   - [ ] A spot-check compares a handful of training-set rows' feature
         values against what the online store would have returned at that
         historical timestamp — this catches skew that unit tests on the
         transformation code alone will miss.

5. **Decide feature ownership and change-review process.** A shared feature
   store without an owner per feature view becomes exactly the "who broke
   this feature" problem it exists to prevent — assign each feature view an
   owning team and require review before a schema or transformation change
   ships, since downstream models will not always notice a silent
   definition change.

## Checklist / quality gate
- [ ] The online-store decision was made deliberately (needed for
      synchronous low-latency serving) rather than defaulted to "yes" for
      every project.
- [ ] Feature names encode their aggregation window or computation logic
      unambiguously.
- [ ] Training-set construction uses a verified point-in-time join, not a
      latest-snapshot join.
- [ ] TTLs are set per feature view based on real staleness tolerance, not
      left at a framework default.
- [ ] Every feature view has a documented owner and a change-review step.

## References
- Interview Kickstart, "MLOps Engineer Skills" — https://interviewkickstart.com/skills/mlops-engineer
- Feast documentation — https://docs.feast.dev/

## Composition
- Consumes the transformation logic a single model's
  `feature-engineering-pipeline` produces and promotes it into the shared,
  multi-consumer layer this skill operates.
- Feeds `model-training-experiment-scaffold`-style training runs with a
  point-in-time-correct training set, and feeds the online store to whatever
  serves the model at inference time.
- Shares its point-in-time-correctness discipline with the general
  `idempotent-backfill-authoring` skill's checkpoint-and-dry-run pattern when
  backfilling historical feature values.
