---
name: data-quality-check-suite
description: Use when a new or changed pipeline, dataset, or dbt model needs validation coverage before merge or before downstream consumers trust it — requests like "add data quality checks," "validate this dataset before we ship it," or "why does this table look wrong." Triggers on null/uniqueness/referential-integrity failures, freshness-SLA breaches, sudden row-count or distribution shifts, and questions about which tool (dbt tests, dbt-expectations, Great Expectations, Soda) fits a given check.
---

# data-quality-check-suite

## Overview
Builds a repeatable validation suite for a dataset or pipeline — nulls,
uniqueness, referential integrity, freshness, and distribution/outlier
checks — and picks the right tool for each check type. Owns "is this data
trustworthy before something downstream consumes it," distinct from
one-off exploratory profiling.

## When to use
- A new pipeline or dbt model needs test coverage before it merges.
- A dataset is suspected of quality problems (unexplained nulls, duplicate
  keys, broken joins, a metric that suddenly jumped).
- A recurring report or dashboard needs an upstream freshness/completeness
  gate so it fails loudly instead of silently serving stale or wrong data.
- A task asks to choose between dbt tests, `dbt-expectations`, Great
  Expectations, or Soda for a given validation need.

## Workflow

1. **Classify what needs checking — the check type drives the tool
   choice, not the other way around:**

   | Check type | What it catches | Typical tool |
   |---|---|---|
   | Not-null | Missing required values | dbt generic test (`not_null`) |
   | Uniqueness | Duplicate primary keys | dbt generic test (`unique`) |
   | Referential integrity | Orphaned foreign keys | dbt generic test (`relationships`) |
   | Accepted values | Enum drift, bad category codes | dbt generic test (`accepted_values`) |
   | Freshness | Stale source data | dbt `sources.yml` freshness block |
   | Distribution / range | Outliers, out-of-bounds values | `dbt-expectations` or Great Expectations |
   | Row-count delta | Silent data loss or duplication | `dbt-expectations` or a singular test comparing counts run-over-run |
   | Cross-field contract | Logical invariants (e.g., `end_date >= start_date`) | `dbt-expectations` or a singular test |
   | Schema/shape drift | Unexpected new/missing/retyped columns | Great Expectations or Soda (schema-level checks) |

   A project already standardized on dbt should default to dbt-native
   tests and `dbt-expectations` before reaching for a separate framework
   (Great Expectations, Soda) — introducing a second tool has real
   maintenance cost and should be justified by a check type dbt genuinely
   can't express.

2. **Cover the five baseline dimensions on every dataset**, even before
   anything looks wrong:
   - **Completeness** — are required fields populated? (`not_null`)
   - **Uniqueness** — is the intended key actually unique? (`unique`)
   - **Validity** — do values fall within an expected domain?
     (`accepted_values`, range checks)
   - **Consistency** — do related fields/tables agree with each other?
     (`relationships`, cross-field contracts)
   - **Timeliness** — did new data arrive when expected? (source freshness)

3. **Set severity deliberately, not uniformly to `error`.** A test that
   fails a pull-request build should be a genuine blocker; a test that's
   informative but noisy (a distribution check with natural variance)
   should `warn` rather than fail the build outright:
   ```yaml
   tests:
     - not_null:
         config:
           severity: error
     - dbt_expectations.expect_column_values_to_be_between:
         min_value: 0
         max_value: 1000000
         config:
           severity: warn
   ```

4. **Write freshness checks that match the pipeline's actual SLA**, not a
   generic default:
   ```yaml
   sources:
     - name: raw_events
       tables:
         - name: orders
           loaded_at_field: _loaded_at
           freshness:
             warn_after: {count: 6, period: hour}
             error_after: {count: 24, period: hour}
   ```
   A freshness window looser than the pipeline's actual schedule hides
   real staleness; a window tighter than the schedule produces alert
   fatigue from expected lag.

5. **Add a row-count / distribution sanity check for silent data loss.**
   Nulls and uniqueness tests catch corruption; they do not catch a
   pipeline that silently drops 40% of rows while producing perfectly
   valid-looking output. A run-over-run row-count comparison (flag any
   swing beyond a set threshold) closes that gap.

6. **For exploratory/ad hoc datasets that aren't dbt-managed**, use Great
   Expectations or Soda's profiling step to auto-generate a baseline
   expectation suite from the current data, then prune it down to the
   checks that actually matter rather than shipping every
   auto-generated expectation unreviewed.

7. **Make failures actionable.** Every check should fail with enough
   context to triage without re-running the query by hand — which rows,
   what the expected vs. actual value was, and (for a `relationships`
   failure) which side of the join is missing the row.

## Checklist / quality gate
- [ ] All five baseline dimensions — completeness, uniqueness, validity,
      consistency, timeliness — are covered for the dataset in scope.
- [ ] Check severity (`error` vs. `warn`) matches whether a failure should
      genuinely block downstream consumption.
- [ ] Freshness thresholds match the pipeline's real schedule, not a
      copy-pasted default.
- [ ] A row-count or distribution check exists to catch silent data loss,
      not just corrupted rows.
- [ ] The tool choice per check type is deliberate (dbt-native first;
      Great Expectations/Soda only where dbt genuinely can't express the
      check).
- [ ] Every failing check produces enough detail to triage without manual
      re-querying.

## References
- dbt data-quality framework:
  https://www.getdbt.com/blog/building-a-data-quality-framework-with-dbt-and-dbt-cloud
- dbt-expectations package:
  https://github.com/calogica/dbt-expectations
- Comparison of dbt tests, Great Expectations, and Soda:
  https://cybersierra.co/blog/best-data-quality-tools/
- dbt data-quality testing guide:
  https://www.datadoghq.com/blog/dbt-data-quality-testing/

## Composition
- Builds directly on **dbt-model-and-test-authoring** — that skill covers
  per-model generic tests; this skill covers the full validation suite
  across a pipeline or dataset, including freshness and cross-tool
  decisions.
- Runs as a gate at the end of an **airflow-dag-authoring** pipeline or a
  **streaming-pipeline-scaffolding** sink before downstream consumers read
  the output.
- Feeds **exploratory-data-analysis-to-hypothesis** when profiling a
  brand-new dataset before modeling — the profiling checklist there and
  the validation suite here share the same completeness/validity checks
  at different stages of a dataset's life.
