---
name: model-drift-monitoring-setup
description: Use when a model is already in production with no monitoring for accuracy degradation — task phrasings like "add drift monitoring to our production model," "the model's been live for six months and we have no idea if it still works," "set up alerts for data drift," or "how do we know when to retrain?" Defines data-drift and concept-drift metrics, wires them into an observability stack (Prometheus/Grafana, Datadog, or a vendor equivalent), sets alert thresholds, and lays out a retrain-trigger checklist. Distinct from an offline eval harness — this skill covers continuous, post-deployment monitoring, not a one-time pre-promotion gate.
---

# model-drift-monitoring-setup

## Overview
Instruments a production model with continuous monitoring for the two ways it
degrades over time — the input data changing shape (data drift) and the
input-output relationship changing (concept drift) — and wires alerting plus
a retrain-trigger checklist on top. It owns detection and alerting; the
retrain itself routes back to a training pipeline.

## When to use
- A model has been in production for a while with no monitoring beyond basic
  uptime/latency checks.
- A team suspects silent degradation — predictions "feel off" but nothing
  alerted.
- A new model is about to ship and the team wants monitoring in place before
  launch rather than reactively after an incident.
- Ground-truth labels arrive with a lag (common in fraud, churn, or credit
  models), so accuracy alone cannot be monitored in real time and a
  drift-based proxy is needed instead.
- A `mlops-ci-cd-pipeline-setup` pipeline needs a `monitor` stage feeding back
  into its `train` trigger.

## Workflow

1. **Separate data drift from concept drift — they need different metrics and
   imply different fixes.**
   - **Data drift**: the distribution of input features shifts (a new
     customer segment starts using the product; a currency starts appearing
     that training data never saw). Detect with:
     - Population Stability Index (PSI) per feature — a common rule of thumb
       is PSI `< 0.1` stable, `0.1–0.2` moderate shift worth watching, `>
       0.2` significant shift.
     - Kolmogorov-Smirnov (KS) test for continuous features, chi-squared for
       categorical features, comparing a rolling production window against
       the training-set distribution.
   - **Concept drift**: the relationship between inputs and the true outcome
     changes even if the input distribution looks stable (fraud patterns
     evolve; a recommendation model's notion of "relevant" shifts with a
     product redesign). Detect via a lagging performance metric (accuracy,
     AUC, calibration) once true labels arrive, or a proxy metric
     (prediction-confidence distribution shift) when labels lag too far
     behind to be actionable.

2. **Do not monitor everything at feature-count granularity by default.**
   Start with the features the model weights most heavily (from feature
   importance) plus any feature with known operational risk (a field sourced
   from an upstream system that changes format without notice). Expanding
   to every feature is a reasonable second pass, not the first.

3. **Wire metrics into the existing observability stack rather than standing
   up a parallel one.** If the team already runs Prometheus/Grafana or
   Datadog for application metrics, emit drift metrics as the same kind of
   time series and reuse the existing alerting/on-call path:

   ```python
   from prometheus_client import Gauge

   psi_gauge = Gauge("model_feature_psi", "Population Stability Index", ["feature", "model_version"])
   psi_gauge.labels(feature="transaction_amount", model_version="7").set(psi_value)
   ```

   Only introduce a dedicated ML-monitoring vendor (Evidently, Arize,
   WhyLabs, or similar) when the team needs drift-specific tooling
   (automated report generation, slice-based drift breakdowns) that a
   general observability stack does not provide out of the box.

4. **Set alert thresholds as a two-tier system, not a single trip-wire.**
   - *Warning* tier (for example, PSI `0.1–0.2`, or a 2-percentage-point
     metric drop): logged and visible on a dashboard, no page.
   - *Critical* tier (PSI `> 0.2`, or a metric drop past the eval gate's
     original promotion threshold): pages on-call and opens the
     retrain-trigger checklist below.

   Thresholds are business-judgment calls, not a fixed constant this skill
   can prescribe — confirm the acceptable-degradation tolerance with whoever
   owns the model's business outcome before finalizing numbers.

5. **Retrain-trigger checklist** — run this when a critical alert fires,
   before kicking off an automatic retrain:
   - [ ] Confirm the alert is real drift, not a pipeline bug (a broken
         upstream feature join often masquerades as drift).
   - [ ] Identify which features or segments are driving the shift — a
         model-wide metric drop caused by one broken feature needs a fix,
         not a retrain.
   - [ ] Check whether fresh labeled data covering the drifted period is
         available; retraining on stale data will not fix drift that
         happened after the training cutoff.
   - [ ] If retraining is warranted, kick off the `mlops-ci-cd-pipeline-setup`
         `train` stage rather than hand-rolling a one-off training run —
         keep the retrain inside the same eval-gated, versioned path as
         every other model update.

## Checklist / quality gate
- [ ] Data-drift and concept-drift metrics are tracked separately, not
      collapsed into a single "model health" number.
- [ ] Monitored features are prioritized by importance and known operational
      risk, not an unreviewed full sweep.
- [ ] Metrics land in the team's existing observability stack unless a
      dedicated ML-monitoring tool is explicitly justified.
- [ ] Alert thresholds have two tiers (warning, critical) with the critical
      tier's numeric value signed off by the model's business owner.
- [ ] A documented retrain-trigger checklist exists and routes back into the
      standard training pipeline rather than an ad hoc script.

## References
- ml-ops.org, "MLOps Principles" — https://ml-ops.org/content/mlops-principles
- devopsschool.com, "MLOps Engineer Role Blueprint" — https://www.devopsschool.com/blog/mlops-engineer-role-blueprint-responsibilities-skills-kpis-and-career-path/

## Composition
- Reads the currently-`Production` model version from
  `model-registry-and-versioning-setup` to know what it is monitoring.
- Its retrain trigger feeds back into the `train` stage of
  `mlops-ci-cd-pipeline-setup`, closing the loop from detection to a
  re-evaluated, re-gated model.
- Shares its threshold-and-alerting shape with the general
  `capacity-planning-forecast` and `add-structured-logging-and-tracing`
  skills for the underlying observability-stack wiring, distinct from the
  drift-specific metric definitions this skill owns.
