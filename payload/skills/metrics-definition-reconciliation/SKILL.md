---
name: metrics-definition-reconciliation
description: Use when two reports, dashboards, or stakeholders disagree on what should be the same KPI number — "why does the revenue dashboard say 1.2M and finance says 1.4M for the same month." Triggers include a stakeholder flagging conflicting numbers for what's supposedly one metric, a migration surfacing two divergent definitions of the same term, or an audit finding the same business term computed with different filters, grains, or join paths across models. Traces metric lineage from dashboard back through the semantic layer to source tables to find the exact divergence point.
---

# metrics-definition-reconciliation

## Overview
Traces a disputed metric's lineage backward from the two disagreeing reports through the semantic layer, the dbt (or equivalent) model layer, and down to source tables, to find the exact point where the two definitions diverge. Owns the diagnosis and reconciliation of an existing conflict; it hands off to `semantic-layer-metric-definition` to author the single corrected definition once the divergence is found.

## When to use
- A stakeholder reports that two dashboards, or a dashboard and a report, show different numbers for what is supposedly the same metric.
- A metrics migration (moving dashboard-local SQL into a governed semantic layer) surfaces two pre-existing, silently divergent definitions of the same term.
- An audit or code review finds the same business term (e.g., "active user," "net revenue") computed with different filters, grains, or join paths in different models.
- Leadership asks "which number is right" before a decision gets made on a disputed figure.

## Workflow

1. **Get the exact comparison first — don't start tracing until the disagreement is precisely specified.** Same time period? Same filters (region, segment)? Same grain? A large fraction of "disagreeing" metrics turn out to be correctly computing two different things that share a name — confirm this isn't the case before assuming a bug.

2. **Trace both numbers back through the lineage, one hop at a time, from the top down:**
   - **Dashboard/report layer** — what exact query, semantic-layer metric, or dashboard-native calculated field produced each number? Get the literal SQL or metric reference for both, not a paraphrase.
   - **Semantic layer** — if both go through a semantic layer, are they actually referencing the *same* metric definition, or two similarly named metrics that were never consolidated? A near-duplicate name (`active_users` vs. `monthly_active_users`) is one of the most common causes.
   - **Model layer** — do both metrics ultimately reference the same mart model, or two different models that were each built independently from the same source data (a classic "reinvented in two places" divergence)?
   - **Source layer** — same source table, same extraction/load logic, same freshness? A staleness gap (one report refreshed today, the other last week) produces a "disagreement" that isn't a logic bug at all.

3. **At each hop, check the four classic divergence points** — in practice, nearly every metric disagreement traces to one of these:
   - **Filter mismatch** — one definition excludes test accounts, canceled orders, or a specific segment that the other includes.
   - **Grain mismatch** — one is computed per event, the other per user-day or per session, producing different aggregation results even from identical raw data.
   - **Time-window/timestamp mismatch** — different anchor timestamp (created vs. completed vs. updated) or a different timezone/date-boundary convention.
   - **Stale materialization** — one side reads a table or extract that hasn't refreshed since the other side's cutoff; not a logic difference, a freshness gap.

4. **Once the divergence point is found, determine which definition (if either) is actually correct** against the plain-English intent of the metric — not against whichever one produces the more convenient number. If neither existing definition is fully correct, this becomes a fresh metric-definition task.

5. **Write up the divergence in plain language before proposing a fix:** state which hop the definitions split at, which specific filter/grain/timestamp caused it, and which number (if determinable) reflects the metric's true intent. This write-up is what makes the reconciliation defensible to whichever stakeholder is emotionally attached to the "wrong" number.

6. **Fix by consolidating to one governed definition, not by patching both sides independently.** Route the corrected definition through `semantic-layer-metric-definition` so both consuming dashboards reference the same semantic-layer metric going forward — patching each dashboard's local SQL independently just reintroduces the same class of bug the next time either one is touched.

## Checklist / quality gate
- [ ] The disagreement is precisely scoped (same period, same filters, same grain assumed on both sides) before tracing begins.
- [ ] Both numbers' lineage was traced hop by hop with the literal SQL/metric reference captured at each layer, not paraphrased.
- [ ] The specific divergence point (filter, grain, timestamp, or staleness) is identified and stated in plain language.
- [ ] A determination was made on which definition (if either) reflects the metric's actual intent, not just which is more convenient.
- [ ] The fix consolidates both consumers onto one governed semantic-layer definition rather than patching each side independently.
- [ ] The write-up is understandable to the requesting stakeholder without them needing to read SQL.

## References
- Analytics-engineering metrics-layer and data-quality material — https://www.getdbt.com/blog/building-a-data-quality-framework-with-dbt-and-dbt-cloud

## Composition
Diagnoses conflicts that `semantic-layer-metric-definition` then resolves by authoring (or correcting) the canonical definition. Frequently triggered as a follow-up from `ad-hoc-sql-analysis-to-insight` (a pulled number doesn't match an existing report) or `dashboard-spec-to-buildout` (a new dashboard would otherwise introduce a third, conflicting version of an existing metric).
