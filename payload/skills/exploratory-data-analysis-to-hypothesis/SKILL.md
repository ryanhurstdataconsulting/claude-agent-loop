---
name: exploratory-data-analysis-to-hypothesis
description: Use when a new or unfamiliar tabular dataset needs profiling before it is trusted for modeling, reporting, or an experiment — checking nulls, distributions, outliers, duplicate rows, class balance, and leakage risk, then turning the findings into two or three concrete, testable hypotheses. Triggers include "here's a new dataset, what's in it", "profile this table before we model it", a new CSV or warehouse table with no data dictionary, and "why does this feature look off" before trusting a column for modeling.
---

# exploratory-data-analysis-to-hypothesis

## Overview
Profiles a new dataset end to end — shape, missingness, distributions, outliers,
duplicates, target balance, and leakage risk — and converts the findings into a short
list of specific, testable hypotheses instead of a wall of summary statistics. It owns
the "do I understand and trust this data yet" stage that has to happen before anyone
builds a model, ships a dashboard, or designs an experiment on top of it.

## When to use
- A dataset just landed (new export, new table, new API response) with no existing
  data dictionary or profile.
- A model or dashboard is producing results that seem off, and the root cause has not
  been isolated to a specific column or row subset yet.
- A task asks for hypotheses or "interesting findings" from a dataset before any
  formal analysis has been scoped.
- Before handing data to `predictive-model-baseline-to-iterate` — an un-profiled
  dataset is exactly where target leakage and class-imbalance surprises hide.

## Workflow

1. **Shape and type check first.** Row count, column count, dtypes per column, memory
   footprint, and a raw sample of rows. Confirm the dtype pandas or the warehouse
   inferred actually matches the semantic type (a numeric-looking ID column should
   usually be treated as categorical, not continuous).

2. **Missingness, per column and as a pattern.**
   - Null percentage per column; flag anything above roughly 30–40% as needing an
     explicit decision (drop, impute, or treat "missing" itself as a signal).
   - Check whether missingness correlates with other columns or with the target — if
     a value is missing not-at-random (MNAR), imputing it naively can inject bias
     rather than remove noise. A quick heuristic: compare the target distribution for
     rows where a column is null vs. not-null; a meaningful difference signals MNAR.

3. **Distributions, per column.**
   - Numeric: summary statistics (mean, median, std, min/max, skew), histogram shape.
     Heavy right skew is common in count/dollar data — flag as a log-transform
     candidate for later modeling, not a data-quality bug on its own.
   - Categorical: cardinality (a categorical column with near-row-count cardinality is
     effectively an ID, not a feature), and the top-N category frequency table to
     catch a dominant "long tail" or an unexpected `"unknown"`/`""`/`NULL`-as-string
     category.

4. **Outliers.** Flag values beyond roughly 1.5×IQR (or 3 standard deviations for
   roughly normal columns) and inspect a sample of the flagged rows individually — an
   outlier is sometimes a data-entry bug (a negative age, a timestamp in the future)
   and sometimes a legitimate extreme case that should stay in the dataset. Decide and
   record which, per column; do not silently cap or drop without noting the decision.

5. **Duplicate and near-duplicate rows.** Exact duplicate check on the full row and on
   the presumed natural key; a nonzero exact-duplicate count on the natural key usually
   means an upstream join fan-out, not a legitimate repeat.

6. **Target variable, if one exists.**
   - Classification: class balance table and the majority-class baseline rate (this
     becomes the naive baseline `predictive-model-baseline-to-iterate` compares
     against). Flag severe imbalance (for example, under roughly 5–10% minority class)
     since it changes metric choice downstream.
   - Regression: distribution shape and skew of the target itself — a heavily skewed
     target is itself a log-transform candidate, and extreme target outliers deserve
     the same per-row inspection as feature outliers.

7. **Leakage risk — reviewed column by column, not skimmed.** For every candidate
   feature, ask: was this value actually available at the moment a prediction would be
   made, or does it encode information from after the outcome (a "resolved date" field,
   a status that only gets set once the outcome is known, an aggregate that includes
   the target period)? This is the single highest-value check in the whole workflow —
   a leaked feature produces a model that looks excellent offline and fails in
   production.

8. **Correlation / multicollinearity scan** across numeric features (a correlation
   matrix or variance inflation factor pass) to flag redundant features before they
   distort a downstream linear model or a feature-importance readout.

9. **Turn the findings into two or three hypotheses, not a dump of statistics.** Each
   hypothesis should be a specific, falsifiable statement paired with the test that
   would confirm or refute it — for example: "Conversion rate is materially lower for
   the mobile-web channel than app or desktop; test with a chi-square test of
   conversion by channel, controlling for acquisition cohort." Vague findings
   ("some columns have nulls") are not hypotheses.

10. **Save the profile as a reusable artifact**, not just chat output — a notebook,
    an `ydata-profiling`/`sweetviz` HTML report, or a markdown summary checked in
    alongside the dataset — so the next person (or the next pipeline stage) does not
    redo this pass from scratch.

## Checklist / quality gate
- [ ] Row/column shape and dtypes documented; semantic type mismatches flagged.
- [ ] Missingness reported per column, including whether it looks MNAR.
- [ ] Distribution shape (skew, cardinality) reported per column, with transform
      candidates flagged.
- [ ] Outliers inspected at the row level, not just counted, with a keep/cap/drop
      decision recorded per affected column.
- [ ] Duplicate rows checked against the natural key, not just the full row.
- [ ] Target class balance or distribution reported, with the naive baseline stated.
- [ ] Every feature reviewed individually for leakage risk — not skipped as "probably
      fine."
- [ ] Two or three specific, falsifiable hypotheses produced, each with its
      confirming test named.
- [ ] Profile saved as a reusable artifact with a path, not left only in chat output.

## References
- roadmap.sh, AI and Data Scientist skills roadmap —
  https://roadmap.sh/ai-data-scientist/skills
- ydata-profiling documentation (automated dataset profiling reports) —
  https://docs.profiling.ydata.ai/
- Great Expectations documentation (data-quality assertion suites) —
  https://docs.greatexpectations.io/

## Composition
Feeds directly into `predictive-model-baseline-to-iterate` (the leakage review and
target-balance findings become the model's baseline and split strategy) and into
`causal-inference-analysis` (confounder candidates and data-quality caveats surface
here first). Overlaps with `data-quality-check-suite` for the mechanical
nulls/uniqueness/freshness checks — reuse that suite's test definitions rather than
re-deriving them by hand. When the dataset lives in a warehouse and the exploration is
SQL-first rather than notebook-first, pair with `ad-hoc-sql-analysis-to-insight`.
