---
name: prompt-regression-testing
description: Use when an existing prompt, system message, or model version is about to change — "tighten up this system prompt," "we're switching models," "add a new instruction to the assistant," or any diff that touches prompt text feeding a shipped LLM feature. Triggers on requests to verify a prompt edit didn't break existing behavior, wire a check into CI, or compare outputs before and after a change using Promptfoo, DeepEval, or a golden dataset.
---

# prompt-regression-testing

## Overview
Verifies that a change to a prompt, system message, few-shot example set,
or underlying model does not silently break behavior that already worked.
Owns "did this edit regress anything," distinct from building the initial
evaluation suite (that is the eval-harness skill) — this skill is the
diff-and-gate step that runs on every subsequent change.

## When to use
- A prompt, system message, or instruction set is being edited and needs a
  before/after comparison before merge.
- A model or model version is being swapped (for example, moving to a
  newer model release) and existing behavior needs to be reverified.
- A task asks to "make sure this prompt change doesn't break anything" or
  to wire a regression check into a CI pipeline.
- A shipped LLM feature regressed after an unrelated-seeming prompt tweak,
  and the task is to find which case broke and why.

## Workflow

1. **Confirm a golden dataset already exists before doing anything else.**
   Prompt regression testing requires a fixed set of representative
   input cases with either expected outputs or expected properties
   (a rubric, not necessarily an exact string match). If none exists,
   hand off to the eval-harness skill to build one first — testing
   regressions against an ad hoc or randomly sampled set of prompts
   produces noisy, non-reproducible results and cannot reliably catch a
   regression twice.

2. **Snapshot current outputs on the golden set before making the prompt
   change.** Run every golden-set case through the current
   prompt/model and store the outputs (and any scoring metadata) as the
   baseline. This step is easy to skip under time pressure and is the
   single most common reason a "regression" surfaces only after the
   change has already merged.

3. **Apply the prompt or model change, then re-run the identical golden
   set.** Keep every other variable fixed — temperature, model version
   (unless the model itself is the change under test), and tool
   configuration — so any output delta is attributable to the change
   being tested.

4. **Diff baseline vs. new output per case, and classify each delta:**
   - **Improvement** — the new output better satisfies the rubric or
     expected behavior than the baseline did.
   - **Neutral** — output text changed but the property being tested
     (correctness, format, tone, safety) is unaffected.
   - **Regression** — a case that previously passed now fails, or a case
     that previously satisfied a safety/format constraint no longer does.

   Do not rely on exact-string diffing for free-text output — score each
   case against its rubric (does it answer the question, does it follow
   the required format, does it avoid a disallowed claim) and diff the
   pass/fail or score, not the raw text.

5. **Block the change on any newly introduced regression**, not merely on
   a lower aggregate score. An aggregate-score check can mask one broken
   case behind several unrelated improvements; report per-case deltas so
   a reviewer can see exactly which case flipped and why.

6. **Wire the check into CI so it runs on every prompt-touching diff**,
   not only when someone remembers to run it manually. A minimal
   Promptfoo config for this pattern:
   ```yaml
   # promptfooconfig.yaml
   prompts:
     - file://prompts/assistant_system_prompt.txt
   providers:
     - id: openai:gpt-4o-mini   # swap for the project's actual provider/model
   tests:
     - file://tests/golden_set.csv
   defaultTest:
     assert:
       - type: llm-rubric
         value: "Answers the user's question using only the provided context"
   ```
   Run `promptfoo eval` in CI on any pull request that touches the prompt
   file or `tests/golden_set.csv`, and fail the build on a regression
   classification from step 4.

7. **Grow the golden set from real regressions.** Every regression caught
   in production or in review is a case that was missing from the golden
   set — add it once fixed, so the same failure mode cannot silently
   reappear on a future change.

## Checklist / quality gate
- [ ] A golden dataset exists and is version-controlled alongside the
      prompt it tests, not recreated ad hoc per run.
- [ ] Baseline outputs were captured before the change, not
      reconstructed or approximated after the fact.
- [ ] Every case is scored against a rubric or expected property, not
      diffed as raw text.
- [ ] Per-case regressions are reported individually — an improved
      aggregate score never waives a specific broken case.
- [ ] The check runs in CI on any diff touching the prompt, system
      message, or model configuration, not only on manual request.
- [ ] A newly discovered production regression gets added to the golden
      set as part of the fix, not just patched in the prompt.

## References
- Promptfoo: https://github.com/AI-App/PromptFoo
- Random prompt sampling vs. golden-dataset regression testing —
  comparison of the two approaches for LLM regression tests:
  https://dev.to/practicaldeveloper/random-prompt-sampling-vs-golden-dataset-which-works-better-for-llm-regression-tests-1ln7

## Composition
- Depends on **eval-harness** for the initial golden dataset, scoring
  rubric, and pass/fail thresholds — this skill reuses that
  infrastructure on every subsequent prompt change rather than rebuilding
  it.
- Feeds back into **rag-pipeline-scaffolding** when a regression traces to
  a generation-prompt change rather than a retrieval change (high
  recall@k, changed answer quality).
- Pairs with **ci-pipeline-authoring** when wiring the regression check
  into a broader CI pipeline alongside code tests.
- Hands off to **llm-cost-latency-optimization** if a prompt change was
  motivated by cost or latency — confirm the regression check passes
  before accepting the optimization.
