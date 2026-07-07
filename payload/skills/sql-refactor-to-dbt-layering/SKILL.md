---
name: sql-refactor-to-dbt-layering
description: Use when a legacy monolithic SQL script, a sprawling view, or a copy-pasted query needs decomposition into a proper dbt staging/intermediate/mart model structure. Triggers include "this 400-line query needs to become dbt models," hardcoded table names that should become `ref()`/`source()` calls, duplicated CTEs copy-pasted across multiple queries, a view chain with no test coverage, or a request to bring an ungoverned SQL script under dbt's naming and layering conventions.
---

# sql-refactor-to-dbt-layering

## Overview
Decomposes a monolithic SQL script or view into dbt's staging → intermediate → mart layering, replacing hardcoded table references with `ref()`/`source()` macros and extracting repeated logic into reusable intermediate models. Owns the refactor step — turning ungoverned SQL into governed, testable, DAG-aware dbt models — not the initial model-authoring of a brand-new pipeline (that is `dbt-model-and-test-authoring`'s job).

## When to use
- A long, single-file SQL script (or a chain of nested views) needs to become dbt models with lineage, tests, and documentation.
- The same CTE or subquery logic is copy-pasted across multiple queries or dashboards — a sign it belongs in a shared intermediate model.
- A query hardcodes schema-qualified table names (`prod.raw.orders`) instead of using `source()`/`ref()`, making it break silently across environments.
- A legacy BI-tool custom SQL block needs to move into the warehouse as a governed model so multiple dashboards can share it.
- A review or audit flags a script with zero test coverage that several downstream reports quietly depend on.

## Workflow

1. **Map the existing query's stages before writing any dbt YAML.** Read the monolith and identify its natural seams: raw source references, per-source cleanup logic (renaming, casting, deduplication), business-logic joins, and final aggregation/presentation. These seams become the staging/intermediate/mart boundaries — don't invent new boundaries that don't match how the logic actually flows.

2. **Staging layer — one model per source table, thin transformations only:**
   - Name `stg_<source>__<entity>` (e.g., `stg_stripe__charges`).
   - Replace every hardcoded table reference with `{{ source('stripe', 'charges') }}`, declared in a `sources.yml`.
   - Allowed here: renaming columns to a consistent convention, type casting, light `NULL`/boolean normalization. Not allowed here: joins across sources, business-logic filtering, aggregation — push those downstream.
   - Add a `sources.yml` freshness block if the source has a staleness SLA worth enforcing.

3. **Intermediate layer — extract reusable joins and business logic:**
   - Name `int_<entity>s_<verb>` (e.g., `int_orders_joined_to_customers`).
   - This is where copy-pasted CTEs from the original monolith belong — if three dashboards each reimplemented "orders joined to their latest customer status," that becomes one `int_` model all three `ref()`.
   - Intermediate models are not meant to be queried directly by BI tools; they exist to keep mart models readable and DRY.

4. **Mart layer — the query surface BI tools and analysts actually hit:**
   - Name by business area, not by source system (`fct_orders`, `dim_customers`), following the project's existing mart-layer naming convention if one exists — don't introduce a second convention.
   - Every hardcoded table name from the original script should now be a `ref()` call to a staging or intermediate model — zero raw table names remaining in the mart layer is the completion signal for this step.

5. **Add tests as part of the refactor, not as a follow-up.** At minimum: `not_null`/`unique` on primary keys in every layer, `relationships` tests on foreign keys introduced by the newly extracted joins, and a row-count sanity check comparing the new layered output against the original monolith's output for a fixed time window — this is the step that actually proves the refactor preserved behavior.

6. **Verify equivalence before deleting the original script.** Run both the old query and the new mart model against the same environment and diff the results (row counts, key aggregates, a sample of individual rows). A refactor that "looks right" but silently changes a join cardinality or a filter is the most common failure mode here — don't skip this check even under time pressure.

7. **Common gotchas:**
   - Fan-out from a join that used to be implicit in a single query but becomes an explicit (and easy to get wrong) join across two or three new models — verify row counts don't balloon.
   - Losing a `WHERE` clause's exact semantics when it gets moved from the original script into a staging model's filter — re-read the original clause literally, don't paraphrase it.
   - Reusing a mart-layer name that collides with an existing model elsewhere in the project.

## Checklist / quality gate
- [ ] Zero hardcoded table names remain — every reference is `ref()` or `source()`.
- [ ] Staging models contain only thin, single-source transformations; joins and business logic live in intermediate or mart models.
- [ ] Previously copy-pasted CTEs are consolidated into a shared intermediate model referenced by all former duplicates.
- [ ] Primary-key `not_null`/`unique` tests and foreign-key `relationships` tests exist at each layer touched.
- [ ] Output of the new layered models matches the original script's output for a known time window (row counts and key aggregates verified, not assumed).
- [ ] Naming follows the project's existing convention (or, if none exists, a documented new one — not an ad hoc third pattern alongside two existing ones).

## References
- dbt style-guide layering conventions (staging/intermediate/marts) — referenced across dbt Labs and community material
- dbt `ref()` and `source()` documentation
- DataCamp dbt testing tutorial — https://www.datacamp.com/tutorial/dbt-tests

## Composition
Feeds `dbt-model-and-test-authoring` for any net-new test coverage beyond the equivalence check, and `dbt-ci-cd-pipeline-setup` once the refactored models need a CI gate. Often a prerequisite for `semantic-layer-metric-definition` — a metric cannot be built cleanly on a mart model until the mart model exists in proper dbt layering. Shares its "extract reusable logic, verify behavior preserved" shape with the general `sql-query-optimization` skill when the refactor is also a performance fix.
