---
name: executive-report-narrative-draft
description: Use when a recurring leadership or board report needs a written narrative alongside its charts and tables — not just the numbers, but the "what happened and why it matters" prose. Triggers include "draft the narrative for this month's leadership report," a request to summarize period-over-period deltas in plain English, a board deck that needs bullet commentary next to each chart, or any generated report where machine-produced prose will reach a non-technical executive audience and must be proofread before delivery.
---

# executive-report-narrative-draft

## Overview
Pulls period-over-period deltas from the underlying data, drafts narrative bullets that flag anomalies and explain the "why" behind the numbers, and runs the draft through a grammar/prose-quality check before it reaches a leadership or board audience. Owns the numbers-to-narrative step for recurring executive reporting; it does not build the charts themselves.

## When to use
- A recurring leadership, executive, or board report needs a written narrative section alongside its charts and tables.
- The ask is specifically for commentary — "what happened this period and why" — not just a refreshed set of visuals.
- Machine-generated prose is about to reach a non-technical executive audience, where a grammar or clarity slip reads as a real quality defect, not a minor nit.
- A report is produced on a cadence (monthly, quarterly) and the narrative needs to stay consistent in structure and tone period over period.

## Workflow

1. **Pull the period-over-period deltas first, as data, before drafting a single sentence.** For every metric the narrative will cover: current-period value, prior-period value, absolute and percentage change, and — where available — the same comparison against plan/target and against the same period last year. Do this as a structured data pull, not from memory or a prior draft.

2. **Rank deltas by what's worth narrating, not by dashboard order.** A metric that moved 0.3% is rarely worth a sentence; a metric that moved 30%, crossed a threshold, or reversed a multi-period trend is. Lead the narrative with the two or three most decision-relevant changes, not with whatever appears first on the dashboard.

3. **For each notable delta, draft a bullet with three parts:**
   - **What moved** — the metric, the direction, and the magnitude, stated in plain numbers an executive can act on without needing to open the underlying dashboard.
   - **Likely why** — a data-grounded explanation (a specific campaign, a known seasonal pattern, a one-time event) if one is identifiable from the available data; if the cause is not clear from the data, say so explicitly rather than inventing a plausible-sounding story. Never assert causality the data doesn't support — flag genuinely ambiguous or surprising moves as open questions rather than papering over them with a guess.
   - **So what** — why this matters to the reader's decisions this period, if that's determinable; omit this clause rather than force a strained "implication" onto a routine, expected fluctuation.

4. **Flag anomalies even if no one asked about them.** If a metric outside the report's usual focus moved sharply, or a data-quality issue was noticed while pulling the deltas, say so in a short callout — a leadership report that only narrates the metrics it was told to narrate can miss the thing leadership most needed to know.

5. **Keep tense and structure consistent period over period.** A recurring report read by the same audience every cycle should not switch between past and present tense, or reorder its sections, without a reason — inconsistency reads as sloppiness even when every individual sentence is correct.

6. **Proofread before delivery — this is a required step, not optional polish.** Machine-generated prose reaching a leadership or board audience gets the same scrutiny as any client-facing deliverable. Before sending:
   - Run the draft through a grammar/prose-quality check if the environment provides one, or do a careful manual pass otherwise.
   - Watch specifically for: *a/an* matching the spoken sound of the next word, including before numbers ("an 8% increase," "a 12-month trend," "an ROI," "a 99th-percentile"); subject–verb agreement; its/it's and their/there/they're; consistent tense throughout; no double spaces; no leftover placeholder text or unresolved template variables.
   - Re-read every generated number against its source pull — a transposed digit in leadership prose is a worse defect than the same error in a raw data table, because the audience has no way to catch it themselves.

## Checklist / quality gate
- [ ] Period-over-period deltas were pulled as structured data before any prose was drafted.
- [ ] Narrative leads with the most decision-relevant deltas, not dashboard order.
- [ ] Each notable bullet states what moved, a data-grounded "why" (or an explicit "cause unclear"), and — when genuinely applicable — the "so what."
- [ ] No causal claim is asserted beyond what the data supports.
- [ ] Anomalies outside the report's usual focus are flagged, not silently omitted.
- [ ] Tense and structure are consistent with prior editions of the same recurring report.
- [ ] The draft has been proofread (grammar/prose-quality check or careful manual pass) and every number cross-checked against its source pull before delivery.

## References
- Internal reporting-practice pattern; no external citation. Pairs conceptually with any project-level prose-quality/grammar-linting tooling available in the environment — run it on the draft before delivery rather than shipping unreviewed generated text.

## Composition
Consumes the metric deltas and, where possible, dashboard structure from `dashboard-spec-to-buildout`, and metric definitions from `semantic-layer-metric-definition` so the narrative's numbers match what the audience sees on the dashboard exactly. If the narrative surfaces a conflicting number, route to `metrics-definition-reconciliation` before publishing rather than narrating a disputed figure as settled fact.
