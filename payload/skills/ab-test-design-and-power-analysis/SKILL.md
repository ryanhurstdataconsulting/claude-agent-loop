---
name: ab-test-design-and-power-analysis
description: Use when a task asks to design, size, or pre-register an A/B test or online controlled experiment — choosing a randomization unit, computing a minimum detectable effect (MDE) and required sample size, setting guardrail metrics, or deciding between a fixed-horizon and sequential stopping rule. Triggers include "how many users do we need for this test", "what's our power", "design an experiment for this feature", sample-size or MDE calculator requests, and sample-ratio-mismatch (SRM) debugging on a live test.
---

# ab-test-design-and-power-analysis

## Overview
Designs a randomized controlled experiment before any traffic is exposed: it turns a
business question into a pre-registered hypothesis, a randomization plan, a sample-size
calculation, and a stopping rule. It owns the *design* stage — sizing and guardrails —
not the post-hoc statistical read-out of a test already in flight (that is the write-up
step at the end of this skill's workflow, but the deep causal read of observational data
belongs to `causal-inference-analysis`).

## When to use
- A stakeholder wants to test a change ("does the new checkout flow lift conversion?")
  and no sample-size or duration plan exists yet.
- A task asks "how long do we need to run this test" or "how many users until we can
  detect a 2% lift."
- An experiment is already running and shows a sample-ratio mismatch (actual traffic
  split diverges from the configured split) or unexpectedly wide confidence intervals.
- A team wants to add a new metric or segment cut to an experiment already live — this
  triggers the multiple-comparison and pre-registration checks below.

## Workflow

1. **Pin down the causal question and primary metric before anything else.** One
   sentence: "Does `<treatment>` change `<primary metric>` for `<population>`?" A test
   with two "primary" metrics is a test with no primary metric — pick one, demote the
   rest to guardrails.

2. **Choose the randomization unit to match the unit of business action.**
   - User-level for most product changes (default).
   - Session-level only when the treatment has no memory across sessions and
     cross-session contamination is acceptable.
   - Account/organization-level for B2B features where individual users in the same
     account would otherwise see inconsistent experiences (network effects, admin
     settings).
   - Mismatch here (randomizing at session level while measuring a user-level outcome
     like retention) is the single most common design bug — it inflates variance and
     invalidates the independence assumption behind the standard-error formula.

3. **Run the power analysis before launch, not after.** For a two-proportion test
   (the common conversion-rate case):

   ```
   n_per_arm = 2 * (z_(α/2) + z_β)^2 * p̄(1 - p̄) / δ^2
   ```

   where `p̄` is the baseline conversion rate, `δ` is the minimum detectable effect
   (absolute), `α` is typically 0.05 (two-sided → z = 1.96), and power `1 - β` is
   typically 0.80 (z_β = 0.84) or 0.90 (z_β = 1.28). For continuous metrics, substitute
   the standard two-sample t-test formula using the metric's variance instead of
   `p̄(1-p̄)`.
   - Report the MDE the available traffic and duration can actually detect, not just
     "we ran the calculator." If the achievable MDE is larger than any effect the
     business would care about, say so before launch — do not let the team discover
     an underpowered test after the fact.
   - Prefer expressing MDE as a relative lift (for example, "a 5% relative lift on a
     20% baseline") since that is what stakeholders reason in.

4. **Decide the stopping rule up front and write it down.**
   - **Fixed-horizon**: pick a sample size/duration from step 3, do not look at
     significance until it is reached, do not stop early on a favorable p-value
     ("peeking" inflates the false-positive rate far above the nominal alpha).
   - **Sequential/always-valid testing** (mSPRT, group sequential designs): choose this
     when the team needs to monitor continuously and stop early on strong signal. It
     trades a larger expected sample size for a valid anytime-stopping guarantee — use
     a library or platform that implements it correctly rather than hand-rolling
     repeated significance tests.
   - Never mix the two: repeated peeking under a fixed-horizon plan without a
     sequential correction is the most common way a team accidentally p-hacks itself.

5. **Set guardrail metrics before launch.** Pick 2–4 metrics that must not regress
   (latency, error rate, revenue, unsubscribe rate) even if the primary metric
   improves. Guardrails get a one-sided "did this get meaningfully worse" test, not a
   full power analysis.

6. **Plan for novelty effects and cold start.** If the treatment is visually or
   behaviorally novel, expect a short-term effect that decays — consider a longer
   minimum run time (covering at least one full business cycle, e.g., a full week to
   capture weekday/weekend variation) or a held-out "new user" cohort analyzed
   separately from returning users who experience the novelty bump.

7. **Pre-register the analysis, including any segment cuts.** Any metric or segment
   examined that was not declared before launch is exploratory, not confirmatory —
   label it as such in the write-up and correct for multiple comparisons (Bonferroni
   or Benjamini–Hochberg) if more than a handful of cuts are tested.

8. **At read-out time, check sample-ratio mismatch (SRM) first.** A chi-square
   goodness-of-fit test comparing observed vs. configured allocation (e.g., expect
   50/50, observed 51.8/48.2 at large n) should not be significant at a conservative
   threshold (p < 0.001, since SRM checks are run routinely and a stricter bar avoids
   false alarms). An SRM failure invalidates the read-out regardless of what the
   primary metric shows — find and fix the imbalance (bucketing bug, bot traffic,
   redirect leakage) before trusting any other number from the test.

9. **Scaffold the analysis** as a versioned script or notebook, not an ad hoc query:
   load raw exposure + outcome events, compute the SRM check, compute the primary
   metric with its confidence interval, compute guardrails, and render a short
   go/no-go summary. Keep the script re-runnable so a stakeholder can re-verify the
   number.

## Checklist / quality gate
- [ ] Hypothesis and single primary metric stated before any sample-size work.
- [ ] Randomization unit matches the unit the outcome is measured on.
- [ ] Sample size / MDE computed and documented before launch; achievable MDE is
      actually meaningful to the business.
- [ ] Stopping rule (fixed-horizon or sequential) chosen explicitly and stated in the
      design doc — no undocumented peeking.
- [ ] Guardrail metrics defined with their own pass/fail bar.
- [ ] Novelty/cold-start handling addressed (minimum run length or held-out cohort).
- [ ] SRM check is the first thing computed at read-out, before the primary metric.
- [ ] Any non-pre-registered metric or segment cut is labeled exploratory and
      multiple-comparison corrected.

## References
- Kohavi, Tang, and Xu, *Trustworthy Online Controlled Experiments* (Cambridge
  University Press, 2020) — the standard reference for sample-ratio mismatch,
  novelty effects, and pitfalls in online experimentation.
- Evan Miller, sample-size and A/B test statistics calculators —
  https://www.evanmiller.org/ab-testing/sample-size.html
- Statsig, experimentation and sequential-testing documentation —
  https://docs.statsig.com/
- Optimizely, Stats Engine methodology documentation —
  https://www.optimizely.com/insights/blog/stats-engine/

## Composition
Feeds a confirmed positive result into `predictive-model-baseline-to-iterate` when the
next step is to model who responds to the treatment (heterogeneous treatment effects).
When randomization is not possible and the question must be answered from observational
data instead, hand off to `causal-inference-analysis`. Pairs with
`exploratory-data-analysis-to-hypothesis` upstream, when the experiment idea itself
comes out of a data-profiling pass rather than a pre-formed hypothesis. Use
`data-quality-check-suite` to validate the exposure and outcome event logs before
trusting any number in the read-out.
