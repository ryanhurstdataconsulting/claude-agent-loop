# Diagram Color Palette

Single source of truth for all color choices in project diagrams. Use these hex values exactly — do not approximate.

## Fill colors (node backgrounds)

| Use | Hex | When |
|-----|-----|------|
| Input nodes | `#D5E8D4` | Data sources and external inputs |
| Process nodes | `#DAE8FC` | Transformation and analysis steps |
| Model nodes | `#E1D5E7` | Statistical models and projections |
| Output nodes | `#FFF2CC` | Reports, dashboards, deliverables |
| External services | `#F8CECC` | APIs, third-party tools |
| Manual steps | `#FFE6CC` | Human actions, reviews, decisions |
| Containers / groups | `#F5F5F5` | Visual grouping of related nodes |

## Stroke colors

- Default node stroke: `#1e1e1e`
- Container stroke: `#BDBDBD` (lighter, dashed if Excalidraw supports it)
- Arrow stroke: `#333333`

## Text colors

- Node label text: `#1e1e1e` on light fills
- Container label text: `#7F8C8D` (muted gray, smaller font size)
- Arrow label text: `#333333` on a white background rectangle for legibility

## Title node

- Fill: `#1e1e1e` (dark)
- Text: `#FFFFFF` (white)
- Font size: 1.5× standard

## Reserved — do not use as a node fill

- Pure black `#000000` and pure white `#FFFFFF` outside the title node
- Saturated red `#FF0000` (reserved for error/blocked states only)

## Editing this palette

If a project requires brand-specific overrides (a client's house colors), copy this file into the project's `docs/` and edit the copy. Do **not** edit this skill-level palette — it is the default.
