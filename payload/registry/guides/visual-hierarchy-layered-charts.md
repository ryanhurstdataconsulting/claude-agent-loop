# Guide — visual-hierarchy-layered-charts

**Category:** skill
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Encodes the contrast-ladder, stroke-hierarchy, and figure-ground techniques
for multi-series charts with defined importance tiers.

## When to deploy (triggers)
Radar plots, line charts with a highlighted series, scatter plots with
selected points, or any hover/click-to-focus dashboard where one series
must "pop" over reference context.

## Interface (how to invoke)
`Skill(visual-hierarchy-layered-charts)`.

## Composition (pairs with / hands off to)
Layers on top of `sports-analyst` and `data-visualization`; invoke after
the chart type is chosen, to decide dimming/desaturation and focus
treatment.

## Build & maintenance notes
Lives at `~/.claude/skills/visual-hierarchy-layered-charts/`.
