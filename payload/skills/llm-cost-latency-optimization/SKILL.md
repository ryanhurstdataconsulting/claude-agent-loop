---
name: llm-cost-latency-optimization
description: Use when a GenAI feature is too slow or too expensive in production — "the chatbot takes 8 seconds to respond," "our token spend doubled last month," "reduce API cost for this feature," or a request to profile and cut per-request cost or time-to-first-token. Covers model right-sizing, caching, batching, streaming, prompt compression, and context-window trimming, with a before/after measurement step.
---

# llm-cost-latency-optimization

## Overview
Diagnoses and reduces the cost or latency of a production LLM feature
without silently degrading output quality. Owns the "make this cheaper or
faster" problem specifically — treats correctness as a hard constraint
carried in from prompt-regression-testing or eval-harness, not something
this skill is free to trade away.

## When to use
- A GenAI feature's latency (time-to-first-token or total response time)
  is failing a user-facing SLO.
- Token spend for an LLM feature has grown unexpectedly or exceeds
  budget.
- A task asks to reduce cost or latency for a specific LLM call path
  without changing what it does.
- A feature works but a scale-up (more users, more requests) makes its
  current cost or latency profile unsustainable.

## Workflow

1. **Measure before optimizing — establish a per-request baseline.**
   Capture, per request: input tokens, output tokens, total tokens,
   dollar cost, time-to-first-token, and total latency. Without this
   baseline, "did the optimization work" cannot be answered, and a
   change that helps one metric while quietly hurting another (for
   example, caching that improves average latency but adds tail-latency
   variance) will go unnoticed.

2. **Work the levers in this order — cheapest and safest first:**

   | Lever | What it does | When it applies | Risk |
   |---|---|---|---|
   | Prompt compression / context trimming | Removes redundant instructions, examples, or stale context from the prompt | Almost always worth checking first — verbose system prompts and unbounded conversation history are the most common silent cost driver | Low, if trimmed content genuinely wasn't needed |
   | Caching | Reuses a previous response or a cached prompt prefix for repeated or similar requests | High-repetition workloads (FAQ-style queries, a stable system prompt reused across many calls) | Low-to-medium — stale cache on time-sensitive content |
   | Model right-sizing | Swaps to a smaller/cheaper model for the same task | The task doesn't need the largest model's reasoning depth (classification, extraction, short-form generation) | Medium — requires re-running the eval suite, not just spot checks |
   | Batching | Groups multiple independent requests into fewer calls or routes non-interactive work through a batch API | Non-interactive, non-latency-sensitive workloads (nightly summarization, bulk classification) | Low, but not usable for interactive/real-time paths |
   | Streaming | Streams tokens to the client as generated rather than waiting for the full response | Any user-facing feature where perceived latency (time-to-first-token) matters more than total completion time | Low — a UX and infrastructure change, not a quality change |
   | Prompt-structure rewrite | Restructures the prompt to reduce required output length (for example, requesting structured output instead of prose to parse) | Output token count dominates cost/latency for the call | Medium — output-format changes need downstream-parser updates |

   Reach for model right-sizing only after prompt-level levers are
   exhausted — swapping models is the change most likely to shift output
   quality and therefore carries the highest regression-testing burden.

3. **Separate cost levers from latency levers — they don't always move
   together.** Caching helps both. Batching helps cost but can hurt
   latency for anything routed through it. Streaming helps perceived
   latency but does nothing for total token cost. Model right-sizing
   helps both but is the riskiest change to quality. Pick the lever that
   matches which metric is actually failing its target, not whichever
   lever is best-known.

4. **Right-size the model deliberately, not by default to the cheapest
   option.** Compare candidate models against the task's actual
   requirements:
   - Does the task require multi-step reasoning, or is it
     classification/extraction/short-form generation that a smaller
     model handles reliably?
   - What is the accuracy delta on the golden set (hand off to
     eval-harness / prompt-regression-testing to measure this — never
     ship a model swap on a cost basis alone without rerunning the eval
     suite)?
   - Does the smaller model's context window still fit the actual prompt
     after compression?

5. **Trim context deliberately — cut what's unused, not what's
   convenient.** For a conversational feature, decide an explicit
   history-retention policy (last N turns, a rolling summary, or
   retrieval-based context selection) rather than sending the entire
   conversation history on every turn by default. For a RAG-backed
   feature, confirm the reranked top-k (from rag-pipeline-scaffolding)
   is not larger than the generation prompt actually needs.

6. **Re-measure against the same baseline metrics and report the delta
   per metric, not just cost or just latency.** A change is only a real
   win if it improves the metric that was failing without regressing
   quality (verified via prompt-regression-testing) or the other cost/
   latency metric past an acceptable threshold. Report as a table:
   baseline vs. optimized, for tokens, cost, time-to-first-token, and
   total latency, alongside the eval-suite pass rate before and after.

## Checklist / quality gate
- [ ] A per-request baseline (tokens, cost, time-to-first-token, total
      latency) was captured before any change was made.
- [ ] Levers were applied cheapest-and-safest first — prompt trimming and
      caching considered before a model swap.
- [ ] Any model right-sizing change was verified against the eval suite
      or golden set, not shipped on a cost basis alone.
- [ ] Cost and latency are reported as separate metrics, not conflated
      into one "it's faster and cheaper now" claim.
- [ ] The optimization's effect on output quality was checked via
      prompt-regression-testing, not assumed to be neutral.
- [ ] The before/after comparison uses the same request set or
      distribution, not a favorable cherry-picked sample.

## References
- Cost and latency optimization for LLM-backed features is documented as
  a combined, required skill in current GenAI-engineering role profiles,
  spanning model selection, caching, batching, and prompt-level
  efficiency.
- Batch processing for non-interactive workloads is available through
  major LLM provider batch APIs at a substantial cost discount relative
  to synchronous calls.
- Prompt caching (reusing a cached prompt prefix across repeated calls)
  is supported by major LLM provider APIs for stable, frequently reused
  system prompts and context.

## Composition
- Depends on **prompt-regression-testing** to verify any optimization
  (especially model right-sizing or prompt rewriting) didn't silently
  degrade output quality — never ship a cost/latency win without this
  check.
- Depends on **eval-harness** when a model swap is significant enough to
  need a full re-evaluation against golden-set thresholds rather than a
  spot check.
- Pairs with **rag-pipeline-scaffolding** when the cost/latency driver is
  an oversized retrieved-context window rather than the generation call
  itself.
- Pairs with **observability-instrumentation** to get the per-request
  token/cost/latency telemetry this skill's baseline step depends on, if
  it doesn't already exist.
