---
name: visual-hierarchy-layered-charts
description: Apply the contrast ladder, stroke hierarchy ladder, and figure-ground dominance techniques when designing multi-series data visualizations with defined importance tiers (reference context / primary subject / focal selection). Use this skill whenever the user works with radar plots, line charts with highlighted series, scatter plots with selected points, dashboards with hover/click-to-focus states, or any overlapping-layer chart where one series is meant to matter more than the others — even if they don't explicitly say "visual hierarchy." Also trigger when the user asks about dimming vs. desaturating non-focus data, semantic color roles, or how to make a selected item "pop" without breaking the rest of the chart.
---

# Visual Hierarchy in Layered Data Visualizations

When a chart renders multiple overlapping layers with different importance (reference cohort < primary subject < focused selection), the viewer's eye should settle on them in that order without thinking. This skill encodes the named techniques that make that happen reliably, regardless of chart type or library.

## The core rule

**Each tier must differ from its neighbors along at least two perceptual dimensions simultaneously.** One dimension is ambiguous; two dimensions produce dominance. The proven pairings are:

- **opacity + stroke weight** (works in any grayscale-compatible rendering)
- **color saturation + stroke weight** (works when color is a reliable channel)
- **hue shift + fill mass** (works best for focal-tier emphasis)

Rationale: Munzner, *Visualization Analysis and Design*, Ch. 6 ("Marks and Channels"). Single-channel differentiation produces scenes where the eye wanders; two-channel differentiation produces scenes where the eye lands.

## Named techniques, in priority order

### 1. Contrast ladder
Assign each importance tier a distinct luminance/opacity step. The steps must be monotonic (background < subject < focus) and perceptually even — doubling opacity from 0.1 → 0.2 → 0.4 feels more like a ladder than 0.1 → 0.15 → 0.2. This is formalized in Radix UI's "subtle / element / solid" semantic roles and in Tailwind's lightness scale.

### 2. Stroke hierarchy ladder
Assign stroke widths that step up with tier: `1px` (background), `2px` (subject), `3px` (focus). This channel survives grayscale conversion, colorblind modes, and low-resolution rendering. If stroke width is your only differentiator, the hierarchy still holds. Tableau design guidelines use this ladder.

### 3. Figure-ground dominance (via hue shift)
The focal-tier element should use a color that is **categorically different** from the cool/warm family of the rest of the chart. If the background and subject tiers are both cool-toned (blues, teals, navies), make the focus warm (yellow, amber, coral). This triggers instant pre-attentive separation before the viewer reads any legend. This is Gestalt figure-ground, modernized.

### 4. Semantic color roles
Map importance tiers to named roles, not raw hex values:
- `reference` / `subtle` / `background` — anchoring context
- `subject` / `element` / `primary` — the thing being analyzed
- `focus` / `solid` / `emphasis` — the selected or focal item
- `interactive` / `hover` — transient attention state (distinct from `focus`)

Route every color choice through the role vocabulary. Design systems that share this vocabulary (Radix, Material, IBM Carbon) do so because it decouples the "what does this mean" layer from the "what hex value" layer.

### 5. Layer order reinforces hierarchy
Background draws first, focus draws last. Occlusion is a perceptual channel all by itself — the topmost layer dominates regardless of color.

## Concrete recipe for a three-tier chart

Given a brand-aligned cool palette (e.g. navy + teal) and a warm accent (e.g. yellow):

| Tier | Fill color | Fill opacity | Stroke color | Stroke width | Stroke opacity |
|---|---|---|---|---|---|
| Reference / background | cool | 0.06–0.10 | cool | 1px | 0.40–0.50 |
| Subject / primary | cool | 0.18–0.25 | cool | 2px | 1.00 |
| Focus / selected | warm | 0.30–0.40 | warm | 3px | 1.00 |

Fine-tuning notes:
- On **dark chart backgrounds**, raise fill opacities by ~0.05 across the board (more fill needed to read as "filled")
- On **light chart backgrounds**, the recipe above works as-is
- If the chart has a **grid**, the grid's color should be at the same opacity tier as "reference" but in a neutral hue so it doesn't compete

## Library-specific constraints to watch for

- **Nivo's `ResponsiveRadar`, `ResponsiveLine`, `ResponsiveBar`** — `fillOpacity` is a single global prop across all series. You cannot set per-series fill opacity natively. Workaround: pass a custom layer via the `layers` prop that renders the filled polygons/areas yourself as raw `<path>` / `<polygon>` SVG elements, while letting Nivo handle axes, grid, legend, and labels. Stroke layers can remain in the default render pipeline since stroke-per-series is supported.
- **d3-shape (`d3.line().curve()`, `d3.area()`)** — full per-series control, no workaround needed. Set opacity on the rendered `<path>` element directly.
- **Recharts** — supports per-series `fillOpacity` on `<Area>` and `<Line>` components natively. Use it.
- **Chart.js** — per-dataset `backgroundColor` with alpha channel (rgba) gives per-series fill opacity; no workaround needed.

## Common pitfalls

- **Equal stroke widths across tiers.** Even with correct opacity values, equal strokes read as "three parallel things" rather than "a hierarchy." The stroke ladder is non-optional.
- **Focus tier uses the same hue as subject tier.** Losing the hue shift drops the biggest perceptual signal. Save the warm/distinct color for focus specifically — do not spend it on the subject tier.
- **Over-fading the background.** Below 0.05 fill opacity with below-40% stroke opacity, the reference layer stops being useful context and starts being invisible. Keep background legible; don't pursue minimalism past utility.
- **Per-series opacity implemented via `opacity` on the group instead of `fillOpacity` on the path.** `opacity` fades both fill AND stroke together. If the intent is to keep the stroke crisp while the fill softens, use `fillOpacity` (SVG) or an rgba fill color.

## When not to apply this

Some charts benefit from the OPPOSITE treatment — where hierarchy would lie. Small-multiples grids, sparkline arrays, and heatmaps typically want every cell to be equal peers. Use this skill only when the data model has a genuine importance ranking and you want the chart to reinforce it.

---

## Acceptance

A layered chart has been done correctly when:
1. A viewer who has never seen the chart before can tell you which layer is the focus within 2 seconds of looking
2. Converting the chart to grayscale does not destroy the hierarchy (stroke ladder holds)
3. Every color in the chart can be named by its semantic role, not just its hex value
4. The focal layer has a distinct hue from the rest of the chart
5. Layer order on the canvas matches importance order (background first, focus last)
