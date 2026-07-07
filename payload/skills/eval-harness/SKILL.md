---
name: eval-harness
description: Use when a machine-learning model or a GenAI feature (RAG, agent, chat, prompt) needs a repeatable, automated evaluation before it ships or before a change to it merges. Triggers on requests like "build an eval harness for this model," "add a golden dataset," "gate this prompt change on eval results," "how do we know this model is better than the last one," and on symptoms like a promoted model regressing in production, a prompt edit silently breaking a downstream behavior, or a subjective "looks better to me" standing in for a measured comparison.
---

# eval-harness

## Overview
Builds a repeatable, automated evaluation gate for a model or a GenAI
feature: a held-out or golden dataset, metric thresholds appropriate to the
artifact type, slice-based breakdowns, and a pass/fail promotion gate. Owns
"prove this artifact is good enough to ship or change," for both classical
ML models and LLM-powered features — the same shape, two artifact types.

## When to use
- A classical ML model (classification, regression, ranking) needs an
  offline evaluation before promotion to production.
- A GenAI feature — RAG pipeline, agent, chat assistant, or a single
  prompt — needs a quality gate before shipping or before an existing
  prompt/model/retrieval change merges.
- A model or prompt regressed in production and there was no automated
  comparison that would have caught it pre-merge.
- A task asks to define pass/fail thresholds, build a golden dataset, or
  wire eval results into CI as a merge gate.

## Workflow

1. **Build the golden/held-out dataset first — the eval is only as good as
   this set.** For a classical model: a held-out split that never touched
   training, stratified so rare classes/segments are represented. For a
   GenAI feature: a golden dataset of real or carefully constructed
   synthetic cases covering the feature's actual use distribution, plus
   deliberately adversarial and edge cases (ambiguous queries, out-of-scope
   asks, prompt-injection attempts for anything that ingests untrusted
   text). In both cases, keep this set under version control and treat
   changes to it as reviewable — silently editing the eval set to make a
   result look better defeats the entire point.

2. **Pick metrics by artifact type, not by convention:**

   | Artifact type | Core metrics | Notes |
   |---|---|---|
   | Classification | Precision, recall, F1, ROC-AUC, calibration | Pick the metric the business cost function actually cares about — accuracy alone hides class imbalance |
   | Regression | RMSE, MAE, R², residual distribution | Check residuals for structure, not just the aggregate number |
   | Ranking/recommendation | NDCG, MRR, recall@k | Evaluate at the k that matches real usage (e.g., top-3 shown to a user) |
   | RAG / retrieval | Faithfulness, answer relevance, context precision/recall, recall@k | Faithfulness (is the answer grounded in retrieved context) catches hallucination directly |
   | Agent / tool-use | Task success rate, tool-call correctness, step efficiency | Measure whether the right tool was called with the right arguments, not just final-answer quality |
   | Chat / open-ended generation | Helpfulness, relevance, safety/harmlessness, format adherence | Often needs an LLM-as-judge in addition to deterministic checks |

3. **Run slice-based evaluation, not just an aggregate score.** Break
   results out by the segments that matter for this artifact — customer
   tier, geography, input length, query category, demographic group where
   fairness is a concern. An aggregate metric can look healthy while a
   meaningful slice silently fails; the slice breakdown is what promotion
   review should actually look at.

4. **Set explicit, pre-committed pass/fail thresholds before the run, not
   after seeing the number.** A threshold decided after looking at the
   result is not a gate — it's a rationalization. For a GenAI feature,
   thresholds are typically per-metric (for example: faithfulness ≥ 0.9,
   safety violations = 0) rather than one blended score, so a strong
   relevance score can't paper over a safety regression.

5. **Wire the harness into CI as a merge gate for the artifact's inputs** —
   a new model version, a changed prompt, a changed retrieval
   configuration, or a changed system message. Diff the new run's
   per-case results against the previous baseline run on the same golden
   set and flag any case that flipped from pass to fail, not just the
   aggregate delta — a regression hiding inside an improved aggregate score
   is still a regression.
   ```yaml
   # CI gate sketch
   - run: python run_eval.py --golden-set golden_v3.jsonl --candidate $NEW_MODEL
   - run: python compare_to_baseline.py --baseline last_promoted.json --candidate results.json --fail-on-regression
   ```

6. **Choose the eval framework by artifact type**, defaulting to the
   established tool for that ecosystem rather than hand-rolling: classical
   ML typically stays inside the existing training/tracking stack
   (scikit-learn metrics, MLflow evaluation); GenAI features reach for a
   purpose-built framework (Promptfoo, DeepEval, Ragas, or a LangSmith-style
   evaluation pipeline) rather than ad hoc string matching, which breaks
   silently on harmless output variation.

## Checklist / quality gate
- [ ] The golden/held-out set is version-controlled, covers the real usage
      distribution, and includes adversarial/edge cases for GenAI
      features.
- [ ] Metrics match the artifact type (see the table above), not a generic
      accuracy-only check.
- [ ] Results are broken out by slice, not reported as a single aggregate
      number.
- [ ] Pass/fail thresholds were committed before the run, per-metric where
      it matters (e.g., safety cannot be traded off against relevance).
- [ ] The harness runs in CI and gates merges/promotions on the artifact's
      actual input surface (model version, prompt, retrieval config).
- [ ] A case-level diff against the last promoted baseline exists, so a
      regression hidden inside an improved aggregate is still caught.

## References
- ML-Ops principles (evaluation and monitoring as a production
  requirement): https://ml-ops.org/content/mlops-principles
- Confident AI 2026 comparison of GenAI evaluation tools:
  https://www.confident-ai.com/knowledge-base/compare/best-ai-evaluation-tools-for-prompt-experimentation-2026
- LangSmith evaluation documentation: https://www.langchain.com/evaluation
- Promptfoo (open-source LLM eval/regression-testing tool):
  https://github.com/promptfoo/promptfoo
- awesome-ai-eval curated list of evaluation tools and methods:
  https://github.com/Vvkmnn/awesome-ai-eval

## Composition
- Gates **model-packaging-and-serving** and **model-training-experiment-scaffold**
  for classical ML — a trained run should clear this harness's thresholds
  before packaging begins.
- Gates a RAG-pipeline-scaffolding or agent-tool-use-design build for GenAI
  features — retrieval and agent changes should run through this harness
  before merging, using the RAG- or agent-specific metric row above.
- Pairs with a prompt-regression-testing practice: this skill defines the
  golden set and thresholds once; regression testing re-runs them on every
  subsequent prompt or system-message change.
- Hands off to an MLOps CI/CD or model-drift-monitoring practice once a
  gate passes — this skill proves the artifact is good enough to promote;
  monitoring proves it stays that way in production.
