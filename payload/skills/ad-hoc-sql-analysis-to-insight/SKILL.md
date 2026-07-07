---
name: ad-hoc-sql-analysis-to-insight
description: Use when a stakeholder asks a one-off business question answerable by querying a warehouse or database — "how many users churned last quarter," "which region had the biggest drop in signups," "did the promotion move conversion." Triggers include a Slack/email question with no existing dashboard to answer it, a request framed as "can you pull a number," an exploratory SQL session with no pre-defined output shape, or any ask that needs an intake pass (grain, time window, filters, exact metric definition) before a query gets written.
---

# ad-hoc-sql-analysis-to-insight

## Overview
Turns a loosely worded business question into a scoped SQL query, a sanity-checked result, and a short written insight — the full path from "can you pull a number" to an answer a stakeholder can act on. Owns the intake-to-insight loop for one-off analysis; it hands off to `dashboard-spec-to-buildout` when the question turns out to need a recurring, not one-off, answer.

## When to use
- A stakeholder asks a business question with no existing dashboard or report already answering it.
- The request is vague enough that two reasonable people could write two different queries and get two different numbers ("how many active users do we have" — active over what window, by what definition?).
- An exploratory data-pull is needed to validate a hypothesis before committing to build a permanent dashboard or metric.
- A prior ad hoc answer is being revisited and needs to be reproduced or extended.

## Workflow

1. **Run intake before writing a single line of SQL.** Vague questions are the number-one source of wrong or re-litigated answers. Pin down, explicitly:
   - **Grain** — what does one row of the answer represent (one user, one order, one user-month)?
   - **Time window** — exact start/end dates, and which timestamp column defines "when" (an event's creation date vs. its completion date are rarely interchangeable).
   - **Filters** — what's excluded (test accounts, canceled orders, internal traffic) and is that exclusion something the stakeholder assumed without saying so?
   - **The metric's exact definition** — if the question uses a term like "active" or "churned," get (or propose) a one-sentence operational definition before querying. If a semantic-layer definition already exists for this term, use it rather than re-deriving it (see `semantic-layer-metric-definition`).
   - If the requester is unavailable to clarify, state the assumed answers to each of the above explicitly in the final response — never bury an assumption inside SQL where it's invisible to the reader.

2. **Write exploratory SQL incrementally, not as one large final query.** Start by counting rows and inspecting a small sample from each source table involved — catches join-cardinality surprises (a `LEFT JOIN` that fans out one row into ten) before they corrupt an aggregate silently.

3. **Sanity-check the result before treating it as an answer:**
   - Compare the result's order of magnitude against something known (total user count, last period's number, a related metric) — a number that's off by 100x from a plausible range usually means a join fanned out or a filter didn't apply.
   - Check for `NULL`s silently dropped out of an aggregate (`COUNT(column)` vs. `COUNT(*)` is a classic silent-undercount bug).
   - Re-read the time-window filter literally against the intake answer from step 1 — an off-by-one on an inclusive/exclusive date boundary is a common, easy-to-miss error.
   - If the query touches a live production database, confirm read-only access is enforced (a wrapping read-only transaction and statement timeout) before running anything.

4. **Write the insight, not just the number.** A raw SELECT result is not a deliverable. Produce 3–5 bullets that:
   - State the headline number with its exact scope (grain, window, filters) restated in plain English — never hand over a bare number with the scope only implicit in the SQL.
   - Compare it to a relevant baseline (prior period, a related segment, a target) so the stakeholder knows if it's good, bad, or expected.
   - Flag anything surprising found along the way (a data-quality issue, an unexpected concentration in one segment) even if it wasn't explicitly asked for.
   - Avoid overclaiming causality from a single correlational pull — flag it as a candidate for a proper causal-inference pass if the stakeholder's next question is "did X cause Y."

5. **Decide if this becomes a one-off or a recurring artifact.** If the same question is likely to be asked again next month, say so and route to `dashboard-spec-to-buildout` (recurring dashboard) or `semantic-layer-metric-definition` (recurring, reusable metric) rather than re-answering the same ad hoc question from scratch every time.

## Checklist / quality gate
- [ ] Grain, time window, filters, and the metric's exact definition are stated explicitly — either confirmed with the requester or written out as an assumption.
- [ ] Query was checked incrementally (row counts, sample rows) before trusting the final aggregate.
- [ ] Result passed a sanity check against a known baseline or order-of-magnitude expectation.
- [ ] `NULL` handling and date-boundary inclusivity were verified, not assumed.
- [ ] The deliverable is a short written insight with the number's scope restated in plain English, not a bare SQL result.
- [ ] If the query hit a live/production database, read-only enforcement was confirmed before execution.

## References
- roadmap.sh data-analyst competency guide — https://roadmap.sh/data-analyst
- SQL fundamentals for analysis (joins, subqueries, aggregations, window functions) as the core analyst toolkit — industry role-roadmap material (secondary source)

## Composition
Consumes metric definitions from `semantic-layer-metric-definition` when one exists rather than re-deriving the metric ad hoc. Hands off to `dashboard-spec-to-buildout` when the question recurs, and to `metrics-definition-reconciliation` if the pulled number conflicts with an existing report. Pairs with the general `sql-query-optimization` skill if the exploratory query is too slow to iterate on.
