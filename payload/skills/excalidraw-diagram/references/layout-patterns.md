# Layout Patterns

Rules for arranging nodes in project diagrams. Apply these mechanically — don't improvise layout.

## Flow direction

| Diagram type | Default direction | Why |
|---|---|---|
| Data pipeline | LEFT → RIGHT | Mirrors how readers parse "input → process → output" left-to-right. |
| Hierarchy / org chart | TOP → BOTTOM | Hierarchies are read top-down; root at top. |
| Decision tree | TOP → BOTTOM | Question at top, branches descend. |
| Feedback loop | LEFT → RIGHT with a return arrow at the bottom | The forward path dominates; the return path is visually subordinate. |

## Spacing

- Minimum **40 px** between adjacent node edges (horizontal or vertical)
- Minimum **80 px** between distinct stages (group-to-group)
- Title node sits **120 px** above the first row of content

## Grouping

Wrap related nodes in a translucent container rectangle when:
- Three or more nodes share a stage (e.g., three different ingestion sources)
- A subsystem belongs to one team or one external service
- The reader benefits from collapsing detail mentally

Containers should be at least 20 px larger than their contents on each side, and labeled in the upper-left in muted gray.

## Arrow routing

- Arrows must not cross other nodes — route around if necessary
- Right-angle (orthogonal) routing for pipelines; straight diagonals only for short hops
- Every arrow is labeled with what data/artifact is flowing
- Labels sit on a white background rectangle for legibility against any fill

## Complexity limits

| Diagram type | Max nodes | Max arrows | Max nesting depth |
|---|---|---|---|
| Developer onboarding | No hard limit (aim ≤ 25) | No limit | 2 levels (groups within groups) |
| Client overview | 15 | 20 | 1 level (top-level groups only) |

When a developer diagram exceeds 25 nodes, split into a top-level overview and one or more sub-diagrams (each with its own .excalidraw file and guide section).

## Title node placement

- Always at the top, spanning the full diagram width or centered
- Includes: project name, diagram type (Developer / Client), version date
- Format example: `Acme Market Analysis — Developer Onboarding — v1.0, 2026-05-09`

## Legend placement

- Bottom-left corner, inside a thin-bordered rectangle
- Lists every node shape used in the diagram with one-line meaning
- Required even on small diagrams — readers need it to decode shape semantics
