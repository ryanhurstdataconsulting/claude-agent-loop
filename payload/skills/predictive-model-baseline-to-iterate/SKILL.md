---
name: predictive-model-baseline-to-iterate
description: Use when a task asks for a first predictive model — classification or regression — on tabular data, or when an existing model needs a proper baseline comparison, metric selection, or error analysis. Triggers include "build a model to predict X", "what accuracy should we expect", a leaderboard/notebook missing a naive baseline, class-imbalance handling questions, feature-importance or SHAP requests, and "the model looks great offline but underperforms in production" (frequently a leakage or split-strategy bug).
---

# predictive-model-baseline-to-iterate

## Overview
Takes a modeling task from "we want to predict X" to a working baseline model with a
sound train/validation/test split, the right metric for the problem, an error-analysis
pass, and a feature-importance sanity check — then defines what "iterate" means next.
It owns getting a trustworthy first result end to end before any hyperparameter tuning
or model-complexity increase is justified.

## When to use
- A task asks for a first classification or regression model on tabular data and no
  baseline exists yet.
- A notebook or pipeline reports a metric (accuracy, RMSE) with no naive-baseline
  comparison to show whether the model actually beats "guess the majority class" or
  "predict the mean."
- A model performs well offline but degrades in production — frequently a symptom of
  a split-strategy leak or a leaked feature, both covered below.
- A team wants a feature-importance or SHAP readout to sanity-check what the model is
  actually keying off of.

## Workflow

1. **Split the data to match its actual structure — never a plain random split when
   structure exists.**
   - Rows sharing a group (the same customer, the same account) that leaks across
     train/test if split randomly → **grouped k-fold**, splitting by group ID.
   - Time-ordered data → **time-based split** (train on the past, validate/test on the
     future); a random split on time-series data leaks future information into
     training and silently inflates every offline metric.
   - Otherwise → a stratified random split (stratified on the target for
     classification) is fine. Typical starting ratios: 60/20/20 or 70/15/15
     train/validation/test; use k-fold cross-validation instead of a single split when
     the dataset is small enough that a held-out slice is noisy.

2. **Always compute and report a naive baseline first.**
   - Classification: predict the majority class every time; report that accuracy (or,
     better, that it is *not* a meaningful metric under imbalance — see step 3).
   - Regression: predict the training mean (or median) for every row; report the
     resulting RMSE/MAE.
   - Every subsequent model result gets reported *relative to this baseline*. A model
     that barely beats the naive baseline is a signal to revisit features or the
     problem framing, not to reach for a more complex algorithm.

3. **Pick the metric to match the problem type and class balance — do not default to
   accuracy.**
   - Binary classification with a rare positive class: prefer **PR-AUC** over ROC-AUC
     (ROC-AUC can look deceptively good under severe imbalance because it is driven by
     the abundant negative class); also report precision/recall/F1 at the actual
     operating threshold the business will use, not just the metric's threshold-free
     summary.
   - Multi-class: macro-F1 when all classes matter equally, micro-F1/weighted-F1 when
     class frequency should drive the weighting.
   - Regression: RMSE and MAE together (RMSE penalizes large errors more; MAE is more
     interpretable), R² for variance explained, and a residual plot to check for
     heteroscedasticity or a systematic bias at particular prediction ranges.

4. **Start with a simple, fast model before anything complex.** Logistic/linear
   regression or a shallow gradient-boosted tree with near-default hyperparameters is
   enough to validate the full pipeline end to end (data loading → features → split →
   train → evaluate) before investing in tuning. A complex model built before the
   pipeline is proven only compounds debugging time when something looks wrong.

5. **Cross-validate with a strategy that matches step 1**, not a default k-fold that
   ignores grouping or time order. Report the metric's mean and spread (std or a
   confidence interval) across folds, not a single-fold number.

6. **Diagnose bias vs. variance before deciding what to iterate on.** Compare the
   training-set metric to the validation-set metric:
   - Both bad, close together → underfitting (bias-limited) → add features, reduce
     regularization, or try a more expressive model.
   - Training much better than validation → overfitting (variance-limited) → add
     regularization, reduce model complexity, get more data, or simplify features.
   - This diagnosis, not intuition, should drive the next iteration.

7. **Run error analysis on the validation set, not just the aggregate metric.**
   - Classification: build a confusion matrix, look at the largest-error examples
     individually, and check whether errors concentrate in a particular segment
     (a specific category, a time window, a customer tier) — a systematic segment
     failure often points to a missing feature or a data-quality issue in that
     segment specifically.
   - Regression: plot residuals against predicted value and against key features to
     spot a range where the model is systematically over- or under-predicting.

8. **Compute feature importance and sanity-check it against domain knowledge** —
   permutation importance or SHAP values, either works. Any feature that dominates
   importance unexpectedly is the first place to re-check for leakage (was this value
   actually available at prediction time?) before trusting the model's performance.

9. **Only after baseline + diagnosis, iterate.** Feature engineering, hyperparameter
   tuning, and model-complexity increases are justified by what step 6 and step 7
   revealed — not applied speculatively "to see if it helps," which burns time without
   a hypothesis to test.

## Checklist / quality gate
- [ ] Split strategy matches the data's structure (grouped, time-based, or i.i.d.
      random) — no leakage across the split.
- [ ] Naive baseline computed and reported alongside every subsequent model result.
- [ ] Metric chosen for the problem type and class balance, not defaulted to accuracy.
- [ ] Cross-validation (or a held-out test set) reports spread, not a single number.
- [ ] Bias-vs-variance diagnosis (train vs. validation gap) stated explicitly before
      any tuning work is proposed.
- [ ] Error analysis performed on the validation set at the row/segment level, not
      just the aggregate metric.
- [ ] Feature importance reviewed and any surprising top feature re-checked for
      leakage.

## References
- scikit-learn documentation — `train_test_split`, `GroupKFold`,
  `TimeSeriesSplit`, and the model-evaluation metrics guide:
  https://scikit-learn.org/stable/modules/cross_validation.html,
  https://scikit-learn.org/stable/modules/model_evaluation.html
- SHAP documentation (feature-importance and explainability) —
  https://shap.readthedocs.io/
- Kuhn and Johnson, *Applied Predictive Modeling* (Springer, 2013) — the standard
  applied reference for baseline comparison, resampling strategy, and metric choice.
- Coursera, Data Scientist skills overview —
  https://www.coursera.org/articles/data-scientist-skills

## Composition
Consumes the output of `exploratory-data-analysis-to-hypothesis` directly — the
leakage review, target-balance findings, and split-relevant structure discovered
there determine step 1 and step 3 here. Hands off to an ML-engineering feature or
model-serving skill once a baseline is validated and the team wants to move from
notebook to a repeatable training pipeline. When the modeling question is really "did
this factor cause the outcome" rather than "predict the outcome," route to
`causal-inference-analysis` instead — prediction and causal attribution are different
problems that call for different methods.
