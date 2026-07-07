---
name: causal-inference-analysis
description: Use when a task asks whether a treatment or intervention caused an observed outcome using non-randomized, observational data — no A/B test was run, but a policy change, feature rollout, price change, or natural experiment gives some quasi-random variation to exploit. Triggers include "did X cause Y", "estimate the causal effect of", "we can't randomize this, but", difference-in-differences, propensity score matching, instrumental variables, regression discontinuity, and confound or selection-bias review requests.
---

# causal-inference-analysis

## Overview
Estimates the causal effect of a treatment on an outcome from observational data, where
randomization was never possible. It owns method selection (matching the identification
strategy to the data's actual structure), the assumption checks each method depends on,
and a write-up that states confound risk explicitly rather than implying causation from
correlation. It does not replace `ab-test-design-and-power-analysis` when randomization
is available — a randomized experiment is always the stronger design; reach for this
skill only when randomization is not possible or already happened in the past.

## When to use
- A stakeholder asks "did X cause Y" about something that already happened and cannot
  be re-run as an experiment.
- A policy, price, or feature change rolled out to one group (region, cohort, account
  tier) but not another, without random assignment.
- A running variable (score, date, threshold) determined who got treated — a natural
  experiment.
- A task explicitly asks to control for confounders or assess selection bias before
  trusting an observed association.

## Workflow

1. **Ask first: was there any randomization at all?** If yes, this is an A/B test —
   route to `ab-test-design-and-power-analysis` or a straightforward significance test
   instead. Causal-inference methods exist specifically to substitute for
   randomization that did not happen; do not reach for them when it did.

2. **Select the identification strategy from the actual shape of the data — not from
   familiarity.** Decision tree:
   - **Panel/repeated-measures data with a treatment that switched on for one group at
     a known time, and a comparable untreated group** → **difference-in-differences
     (DiD)**. Requires the parallel-trends assumption: treatment and control groups
     would have moved together absent treatment. Check it with a pre-treatment trend
     plot and, where possible, a placebo test (fake treatment date before the real
     one, expect no effect).
   - **Treatment assignment is a deterministic (or near-deterministic) function of a
     running variable crossing a cutoff** (e.g., a score ≥ threshold triggers
     eligibility) → **regression discontinuity design (RDD)**. Check for manipulation
     of the running variable near the cutoff (density/McCrary test) and report
     sensitivity to bandwidth choice.
   - **Rich covariates observed pre-treatment, no natural experiment, treatment
     assignment plausibly explained by those covariates** → **propensity score
     matching (PSM) or inverse probability weighting (IPW)**. Requires
     unconfoundedness (no *unmeasured* confounders) — inherently untestable directly;
     argue it qualitatively from domain knowledge and support it with a sensitivity
     analysis (Rosenbaum bounds or an E-value). Check post-matching covariate balance
     (standardized mean difference < 0.1 per covariate) and common support/overlap
     before trusting the estimate.
   - **A variable exists that plausibly moves treatment but has no path to the outcome
     except through treatment** → **instrumental variables (IV / 2SLS)**. Check
     instrument relevance with a first-stage F-statistic (> 10 is the traditional rule
     of thumb for "not weak"); the exclusion restriction cannot be tested statistically
     — argue it explicitly and flag it as the analysis's biggest assumption.
   - **Staggered treatment timing across many units/periods** → avoid naive two-way
     fixed-effects regression, which is known to be biased under staggered adoption
     with heterogeneous effects; use a modern estimator designed for this case
     (Callaway–Sant'Anna, Sun–Abraham) instead.

3. **State every identifying assumption in writing, and check what can be checked.**
   Untestable assumptions (unconfoundedness, the exclusion restriction) still need an
   explicit qualitative argument in the write-up — silence on them is a red flag a
   reviewer should catch, not a shortcut.

4. **Run at least one falsification or placebo test.** Options: a fake treatment date
   or fake cutoff where no effect should exist, an outcome that should not respond to
   treatment (a negative-control outcome), or a pre-treatment "effect" check that
   should come back null. A method that fails its own placebo test is not ready to
   report.

5. **Report the effect size with a confidence interval, not a p-value alone.**
   Causal estimates are frequently over-interpreted when only significance is shown;
   pair the point estimate with its interval and with the assumption strength required
   to believe it.

6. **Write the confound-risk section explicitly — do not omit it.** Name the
   confounders that were controlled for, the ones that plausibly remain, and how
   sensitive the conclusion is to their presence. State whether the result should
   inform a decision on its own or should be treated as one input pending a proper
   experiment.

7. **Watch the language.** Use "associated with" for anything short of a defensible
   identification strategy; reserve "caused" for a result whose assumptions were
   stated and checked. Overclaiming causation from a correlational read is the most
   common failure mode this skill exists to prevent.

## Checklist / quality gate
- [ ] Confirmed no randomization existed (otherwise this is the wrong skill).
- [ ] Identification strategy chosen to match the data's actual structure, with the
      alternative methods considered and rejected named explicitly.
- [ ] Every identifying assumption stated; testable ones checked (parallel trends,
      covariate balance, instrument strength, running-variable continuity).
- [ ] At least one placebo/falsification test run and reported, pass or fail.
- [ ] Effect size reported with a confidence interval.
- [ ] A confound-risk paragraph is present in the write-up, not skipped.
- [ ] Causal language ("caused") used only where the method and checks support it;
      otherwise "associated with."

## References
- Angrist and Pischke, *Mostly Harmless Econometrics* (Princeton University Press,
  2009) — the standard applied-econometrics treatment of DiD, IV, and RDD.
- Cunningham, *Causal Inference: The Mixtape* — https://mixtape.scunning.com/
- Facure, *Causal Inference for the Brave and True* (Python-focused open handbook) —
  https://matheusfacure.github.io/python-causality-handbook/
- Callaway and Sant'Anna, "Difference-in-Differences with Multiple Time Periods,"
  *Journal of Econometrics* (2021) — the modern staggered-adoption DiD estimator.

## Composition
Sits alongside `ab-test-design-and-power-analysis` as the observational-data
counterpart to a randomized experiment — route to the experiment-design skill first
whenever randomization is actually possible. Consumes a profiled dataset from
`exploratory-data-analysis-to-hypothesis` (confounder candidates and data-quality
issues surface there before the causal analysis begins). Hands a validated causal
driver off to `predictive-model-baseline-to-iterate` when the next step is to build a
model that targets or ranks by the causal driver rather than merely the correlation.
