---
name: dashboard-spec-to-buildout
description: Use when a stakeholder ask needs to become a built dashboard in a BI tool — Power BI, Tableau, Looker Studio, or an equivalent — rather than a one-off answer. Triggers include "build a dashboard for X," "add a filter/drill-down to this report," a vague request like "can we track this over time" that implies a recurring view, or a review of an existing dashboard's filter behavior, chart-type choices, or accessibility. Complements the general chart-and-visualization skill by owning the BI-tool-specific spec-to-buildout path: translating a stakeholder ask into a concrete dashboard spec before any chart gets built.
---

# dashboard-spec-to-buildout

## Overview
Translates a stakeholder request into a concrete dashboard specification — which metrics, which filters, which drill-downs, which chart type per metric — then builds it out in the target BI tool. Owns the requirements-to-spec step that a general charting skill assumes is already done; defers to that general skill's chart-selection and design-system guidance for the actual visual construction.

## When to use
- A request to build or substantially modify a Power BI, Tableau, Looker Studio, or comparable dashboard.
- The ask is a recurring monitoring need ("can we track this over time"), not a one-off question — the signal to route here instead of `ad-hoc-sql-analysis-to-insight`.
- An existing dashboard needs new filters, a drill-down path, or a consistency/accessibility review.
- A stakeholder's request names outcomes ("I want to see how we're doing by region") rather than a specific chart — the spec step exists precisely to turn that into concrete chart and filter decisions before anything gets built.

## Workflow

1. **Write the dashboard spec before opening the BI tool.** A spec that answers the following prevents rework later, when a half-built dashboard turns out to answer the wrong question:
   - **Primary audience and their decision** — who looks at this, and what decision or action does it inform? A dashboard for an executive skim differs from one for an analyst's deep dive.
   - **One metric per row of the spec**, each with: its exact definition (pull from the semantic layer if one exists — see `semantic-layer-metric-definition` — rather than inventing a dashboard-local definition), its default time grain, and whether it needs a trend view, a snapshot, or both.
   - **Filters and drill-downs** — which dimensions does the audience need to slice by (region, product, time period), and which of those need a drill-down path (summary → detail) versus a flat filter.
   - **Refresh cadence** — real-time, daily, or on a schedule; this determines the underlying data-source and caching strategy, not just the visual layer.

2. **Choose chart type per metric with a decision tree, not by habit:**
   - Trend over time → line chart (multiple series only if comparing a small, fixed set — beyond five or six lines, split into small multiples).
   - Part-to-whole at a single point in time → stacked bar or a simple ranked bar chart; avoid pie/donut charts once there are more than four or five categories.
   - Comparison across categories → horizontal or vertical bar chart, sorted by value rather than alphabetically unless alphabetical order is itself meaningful to the audience.
   - Distribution → histogram or box plot, not a bar chart with a misleading continuous x-axis.
   - Correlation between two metrics → scatter plot; add a trend line only when the correlation is real and worth calling out, not by default.
   - A single headline KPI → a stat tile with a period-over-period delta, not a chart for a single number.

3. **Design the filter and drill-down interaction explicitly.** Decide, per filter: does it apply globally across the whole dashboard or scope to one visual? Does a drill-down replace the current view or open a detail panel? Undefined filter scope is one of the most common sources of "the dashboard looks broken" bug reports — a filter silently not applying to one chart because it was built before the filter existed.

4. **Build the dashboard, then run the consistency and accessibility pass:**
   - Consistent color encoding for the same dimension across every chart on the dashboard (a region colored blue in one chart must be blue everywhere on the page).
   - Sufficient contrast for text and for any color-encoded categorical data; don't rely on color alone to distinguish categories that also need to be distinguishable by colorblind viewers — pair color with position, labels, or pattern.
   - Consistent number formatting (decimal places, currency symbols, percentage vs. raw count) across every tile.
   - Every chart has an explicit title stating what it shows, not just an axis label.
   - Verify filter and drill-down interactions actually work end to end — click through each one rather than assuming the BI tool's default wiring is correct.

5. **Route, don't rebuild, when the ask is actually something else.** If the request turns out to be a one-off question, it belongs in `ad-hoc-sql-analysis-to-insight` instead. If two existing dashboards already disagree on a number this dashboard would also show, stop and route to `metrics-definition-reconciliation` before adding a third, possibly also-wrong, version.

## Checklist / quality gate
- [ ] Spec exists (audience, per-metric definitions, filters/drill-downs, refresh cadence) and was reviewed before buildout started.
- [ ] Each metric traces to a semantic-layer definition or has one written down, not silently invented at the dashboard layer.
- [ ] Chart type per metric follows the decision tree above, not an arbitrary or habitual choice.
- [ ] Filter scope (global vs. per-visual) and drill-down behavior are explicit and tested by clicking through, not assumed.
- [ ] Color encoding, contrast, and number formatting are consistent across every tile on the dashboard.
- [ ] A human reviewer has signed off on final visual/design judgment — this skill scaffolds the buildout; it does not replace a design review.

## References
- Self-service BI and dashboard-design trend material — industry role-roadmap sources (secondary)
- General chart-selection and visual-design guidance (see the companion data-visualization skill for the deeper design-system treatment)

## Composition
Consumes metric definitions from `semantic-layer-metric-definition` and routes conflicting numbers to `metrics-definition-reconciliation`. Defers to the general `data-visualization` skill (and any domain-specific analyst skill, when the dashboard is for a specific competitive/sports/scouting domain) for chart-construction craft and visual-hierarchy technique once the spec is set. Receives handoffs from `ad-hoc-sql-analysis-to-insight` when a one-off question turns out to need a recurring view.
