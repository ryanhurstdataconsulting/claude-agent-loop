---
name: semantic-layer-metric-definition
description: Use when a business metric (revenue, active users, churn rate, conversion rate) needs a canonical, reusable definition in a semantic layer such as dbt Semantic Layer/MetricFlow, LookML, or Cube — rather than being redefined ad hoc in every dashboard query. Triggers include "define this metric once," a request to add a metric YAML file, a new KPI that multiple dashboards will consume, or a review turning up two models computing "the same" number with different filters, grains, or join paths. Also load this before writing a `metrics.yml` / `semantic_model` block, or when asked to standardize a metric that already has inconsistent SQL definitions scattered across models.
---

# semantic-layer-metric-definition

## Overview
Authors a single, canonical metric definition — name, expression, grain, dimensions, and filters — inside a semantic layer, so every downstream dashboard and ad hoc query pulls from the same logic instead of re-deriving it. Owns the definition step; it hands off to `dbt-model-and-test-authoring`-style work for the underlying model and to `metrics-definition-reconciliation` when two existing numbers already disagree.

## When to use
- A stakeholder or PRD names a new KPI ("monthly active users," "gross margin," "trial-to-paid conversion") that more than one report will need.
- A request to add or edit a `semantic_models:` / `metrics:` block in a dbt project, a LookML `measure`, or a Cube `measures` definition.
- A code review or audit turns up the same business term computed with different `WHERE` clauses, joins, or date grains in different models.
- Migrating a metric out of ad hoc dashboard-layer SQL into a governed, warehouse-native definition.
- Before a metric is exposed through a BI tool's semantic layer integration (Looker, Tableau, Power BI via the dbt Semantic Layer, etc.).

## Workflow

1. **Capture the metric's plain-English intent first.** Write one sentence: "what business question does this number answer?" A metric without a stated intent tends to accumulate silent scope creep (filters added by whoever touched it last).

2. **Pin down five things before writing any YAML** — each is a common divergence point when two dashboards disagree later:
   - **Grain** — the lowest level of detail the metric is computed at (per order, per user-day, per session). Get this wrong and aggregations silently double-count or under-count.
   - **Time dimension** — which timestamp column defines "when" the event happened (created_at vs. completed_at vs. updated_at are rarely interchangeable).
   - **Filters baked into the metric vs. left to the dashboard** — e.g., does "active user" already exclude internal test accounts, or is that a downstream filter? Bake in filters that are part of the *definition*; leave slicing filters (region, plan tier) as free dimensions.
   - **Aggregation type** — sum, count distinct, average, ratio-of-two-aggregates (ratio metrics need their numerator and denominator to share a grain, or the ratio is meaningless at other grains).
   - **Null/zero handling** — does a missing value mean zero, or should the row be excluded? State it explicitly; don't leave it to whatever the engine defaults to.

3. **Check for an existing definition before creating a new one.** Search the semantic layer and any legacy dashboard SQL for the metric name or a close synonym. If one exists but disagrees with the stated intent, this is a reconciliation problem — flag it and route to `metrics-definition-reconciliation` rather than quietly adding a second, conflicting metric with the same name or a near-duplicate name.

4. **Author the definition in the project's semantic layer, following its conventions:**
   - **dbt Semantic Layer / MetricFlow** — define a `semantic_model` pointing at a mart-layer model (never a raw or staging model), declare `entities`, `dimensions`, and `measures`, then a `metrics:` block referencing the measure with `type: simple | ratio | derived | cumulative` as appropriate.
   - **LookML** — a `measure` inside the relevant `view`, with `type:`, `sql:`, and a `description:` that states the grain and any baked-in filters in plain English.
   - **Cube** — a `measures` entry on the relevant cube, with `type`, `sql`, and `filters` for any baked-in exclusions.
   - In every case, add a human-readable `description`/`meta.label` field — the next person reading the semantic layer should not have to reverse-engineer the SQL to know what the number means.

5. **Name it so a duplicate is hard to create by accident.** Prefer a name that encodes the grain or scope when ambiguity is likely (`monthly_active_users` rather than `active_users`, `net_revenue_after_refunds` rather than `revenue`). Vague names are the number-one cause of the "two dashboards disagree" incident this skill exists to prevent.

6. **Validate before handing off:**
   - Compile/run the semantic layer locally (`mf query`, `dbt sl query`, a LookML validator, or the Cube playground) against a known period and sanity-check the result by eye or against a hand-computed spot check.
   - Confirm the metric resolves correctly when sliced by at least two different dimensions — a broken join or fan-out often only shows up once you add a dimension.

## Checklist / quality gate
- [ ] Plain-English intent statement exists alongside the technical definition.
- [ ] Grain, time dimension, baked-in filters, aggregation type, and null handling are all explicit — none left to implicit engine defaults.
- [ ] Searched for and did not find (or explicitly reconciled) a pre-existing definition of the same or a confusingly similar name.
- [ ] Metric is built on a mart/model layer, not directly on raw or staging tables.
- [ ] Human-readable description/label field is present.
- [ ] Compiled and spot-checked against a known period, including at least one dimensional slice.

## References
- dbt Semantic Layer and MetricFlow documentation (metric types: simple, ratio, derived, cumulative) — https://docs.getdbt.com/docs/build/metrics-overview
- Analytics-engineering role expectations on metric governance and data integrity — industry role-description material (secondary source)
- LookML measures reference (Looker)
- Cube measures and semantic-layer documentation

## Composition
Pairs with `dbt-model-and-test-authoring` (the underlying mart model the metric is built on must exist and be tested first) and `sql-refactor-to-dbt-layering` (when the source SQL is still a monolithic script). Hands off to `metrics-definition-reconciliation` when a conflicting definition is discovered rather than a clean slate. Feeds `dashboard-spec-to-buildout` and `executive-report-narrative-draft`, which should consume the semantic-layer metric rather than re-deriving it in dashboard- or report-level SQL.
