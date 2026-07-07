---
name: dbt-model-and-test-authoring
description: Use when adding or modifying a dbt model, source definition, or schema test — new staging/intermediate/mart SQL files, `schema.yml` edits, `sources.yml` wiring, or a request to "add tests to this model" or "build a mart on top of these staging models." Triggers on `dbt build`/`dbt test` failures, `not_null`/`unique`/`relationships` test failures, missing `ref()`/`source()` macros, and requests to add data-quality coverage to a dbt project.
---

# dbt-model-and-test-authoring

## Overview
Authors dbt models that follow standard staging → intermediate → mart
layering, wires their sources and tests correctly, and validates the result
with `dbt build`/`dbt test`. Owns model authorship and test coverage for a
single dbt project — not warehouse-wide orchestration (see
`airflow-dag-authoring`) or cross-report metric reconciliation.

## When to use
- A task asks to add a new dbt model (staging, intermediate, or mart).
- A task asks to add or update tests on an existing model.
- A raw source table needs to be registered in `sources.yml` and referenced
  from a model.
- `dbt build` or `dbt test` is failing and the failure needs diagnosis.
- A legacy SQL view or script needs to be rebuilt as a proper dbt model.

## Workflow

1. **Place the model in the correct layer.** dbt's standard layering exists
   to keep transformation logic traceable and testable at each step:
   - **Staging (`stg_*`)** — one model per source table, 1:1 renaming and
     light typecasting only. No joins, no business logic.
   - **Intermediate (`int_*`)** — reusable joins, aggregations, and business
     logic that more than one mart consumes. Not exposed to BI tools
     directly.
   - **Marts (`fct_*`/`dim_*` or a domain-named folder)** — the
     analytics-ready, wide, denormalized tables that dashboards and
     analysts query.

   Never let a mart model read directly from a raw source — always route
   through a staging model first, even for a "quick" one-off.

2. **Wire sources, not hard-coded table names.**
   ```yaml
   # sources.yml
   sources:
     - name: raw_app_db
       database: raw
       schema: app_db
       tables:
         - name: orders
           loaded_at_field: _loaded_at
           freshness:
             warn_after: {count: 12, period: hour}
             error_after: {count: 24, period: hour}
   ```
   Every model references upstream data with `{{ source('raw_app_db',
   'orders') }}` or `{{ ref('stg_orders') }}` — never a literal
   `schema.table` string. This is what makes `dbt docs generate`'s lineage
   graph and `dbt build --select state:modified+` (slim CI) work at all.

3. **Add tests as part of the same change, not as an afterthought.** At
   minimum, every model gets:
   - `unique` + `not_null` on its primary key.
   - `not_null` on any column a downstream join or `WHERE` clause depends
     on.
   - `relationships` on every foreign key, pointing at the parent model's
     primary key.
   - `accepted_values` on any enum-like column (status, type, tier).

   ```yaml
   # schema.yml
   models:
     - name: fct_orders
       columns:
         - name: order_id
           tests: [unique, not_null]
         - name: customer_id
           tests:
             - not_null
             - relationships:
                 to: ref('dim_customers')
                 field: customer_id
         - name: status
           tests:
             - accepted_values:
                 values: ['pending', 'shipped', 'cancelled', 'refunded']
   ```

4. **Reach for `dbt-expectations` or a custom singular test when generic
   tests aren't enough** — freshness windows, distribution/range checks
   (`expect_column_values_to_be_between`), row-count deltas versus the
   prior run, or cross-field contracts (e.g., `ship_date >= order_date`).
   A singular test is a plain SQL file under `tests/` that should return
   zero rows on success.

5. **Document non-obvious columns.** A `description:` on any column whose
   meaning isn't self-evident from its name (a status code, a derived
   metric, a business-specific flag) — this is what turns `dbt docs
   generate` into a usable data dictionary instead of a bare schema dump.

6. **Run and read the results, don't assume green:**
   ```bash
   dbt build --select <model>+     # build the model and everything downstream
   dbt test --select <model>       # run just its tests
   ```
   A `not_null` or `unique` failure on a freshly added test is often
   revealing a real data-quality problem in the source — do not silently
   loosen the test to make it pass; flag the underlying issue instead.

## Checklist / quality gate
- [ ] The model sits in the correct layer (staging/intermediate/mart) and
      does not skip a layer.
- [ ] Every upstream reference uses `ref()`/`source()` — zero hard-coded
      table names.
- [ ] The model's primary key has `unique` + `not_null` tests.
- [ ] Every foreign key has a `relationships` test to its parent.
- [ ] Enum-like columns have `accepted_values` tests.
- [ ] Non-obvious columns have a `description:`.
- [ ] `dbt build --select <model>+` and `dbt test --select <model>` both
      pass, and any failure was diagnosed as a real data issue, not
      test-relaxed away.
- [ ] `sources.yml` freshness is set for any new source the model depends
      on.

## References
- dbt Labs — model layering and project structure conventions:
  https://docs.getdbt.com/best-practices/how-we-structure/1-guide-overview
- dbt Labs — testing documentation (generic and singular tests):
  https://docs.getdbt.com/docs/build/data-tests
- dbt-expectations package:
  https://github.com/calogica/dbt-expectations
- Building a data-quality framework with dbt:
  https://www.getdbt.com/blog/building-a-data-quality-framework-with-dbt-and-dbt-cloud

## Composition
- Feeds **data-quality-check-suite** when test coverage needs to expand
  beyond per-model generic tests into a full validation suite (freshness,
  distribution, outlier checks) across a pipeline.
- Hands off to **sql-refactor-to-dbt-layering** when the starting point is
  a legacy monolithic script rather than a clean new model.
- Pairs with **dbt-ci-cd-pipeline-setup** for wiring `dbt build --select
  state:modified+` into pull-request checks.
