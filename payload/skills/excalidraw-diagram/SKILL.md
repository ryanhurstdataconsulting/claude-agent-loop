---
name: excalidraw-diagram
description: >
  Generate Excalidraw diagrams that document a project's architecture, data flow,
  and component relationships. Use this skill whenever the user asks to visualize
  a project's structure, create onboarding diagrams, document data pipelines,
  generate client-facing architecture overviews, or produce any diagram that
  shows how components connect and data flows from input to output. Also trigger
  when the user mentions "project diagram", "architecture visualization",
  "data flow diagram", "onboarding map", "component diagram", or asks to
  "diagram this project". This skill produces two diagram variants: a developer
  onboarding diagram (technical, showing all components) and a client-facing
  diagram (simplified, showing value flow).
---

# Excalidraw Project Diagram Skill

## Purpose

Generate `.excalidraw` JSON files that visualize a project's structure for two
audiences: (1) developers onboarding to the project, and (2) non-technical
clients who need to understand what the project does and why it matters.

## When to Generate Diagrams

- At project kickoff (initial architecture)
- After significant structural changes (new data sources, new output channels)
- Before client presentations or board meetings
- When onboarding a new developer to the project
- When the project README or docs are being updated

## Diagram Requirements

### Every diagram MUST include:

1. **Title node** — project name, diagram type (Developer / Client), version date
2. **Input nodes** — all data sources entering the system
3. **Process nodes** — transformations, models, analyses performed on data
4. **Output nodes** — deliverables, dashboards, reports, APIs produced
5. **Flow arrows** — directed edges showing data movement with labels
6. **Legend** — node shape/color meanings

### Developer Diagram (Case A) additionally includes:

- Technology labels on each node (language, framework, database)
- File/directory references for each component
- Dependency arrows (which components depend on which)
- Environment requirements (API keys, credentials, external services)
- Build/deploy steps as a separate swim lane

### Client Diagram (Case B) additionally includes:

- Value annotations ("This step produces the competitive analysis")
- Simplified grouping (multiple technical steps collapsed into one business step)
- Cost/time indicators where relevant
- Plain-language labels (no jargon)

## Node Type Conventions

| Shape | Meaning | Color |
|-------|---------|-------|
| Rectangle | Process / Transformation | Blue (#4A90D9) |
| Rounded Rectangle | Service / External System | Green (#27AE60) |
| Diamond | Decision / Branch | Orange (#F39C12) |
| Cylinder | Database / Data Store | Purple (#8E44AD) |
| Parallelogram | Input / Output Data | Gray (#7F8C8D) |
| Hexagon | Manual Step / Human Action | Red (#E74C3C) |
| Cloud shape | External API / Third-party | Light Blue (#85C1E9) |
| Document shape | Report / Deliverable | Gold (#F4D03F) |

## Excalidraw JSON Structure

The output file must be valid Excalidraw JSON. Key structure:

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "excalidraw-diagram-skill",
  "elements": [
    {
      "type": "rectangle",
      "id": "node-001",
      "x": 100,
      "y": 200,
      "width": 200,
      "height": 80,
      "strokeColor": "#1e1e1e",
      "backgroundColor": "#a5d8ff",
      "fillStyle": "solid",
      "label": { "text": "Data Ingestion" }
    }
  ],
  "appState": {
    "viewBackgroundColor": "#ffffff",
    "gridSize": 20
  }
}
```

## Layout Rules

- Flow direction: LEFT → RIGHT for data pipelines, TOP → BOTTOM for hierarchies
- Minimum 40px spacing between nodes
- Group related nodes visually with a light background rectangle (container)
- Arrows should not cross other nodes; route around if necessary
- Maximum 15 nodes in a client diagram; no limit for developer diagrams
- Label every arrow with what data/artifact is flowing

## Step Documentation Pairing

Every node in the diagram must have a corresponding entry in the project's
documentation file (`PROJECT_DIAGRAM_GUIDE.md`). The entry must include:

- **Node ID** — matches the diagram element ID
- **Node Label** — human-readable name
- **What This Step Does** — 2-3 sentence plain-language description
- **Inputs** — what data/artifacts enter this step
- **Outputs** — what data/artifacts leave this step
- **For Developers** — technical implementation details, file paths, dependencies
- **For Clients** — business value explanation, why this step matters

See `references/node-types.md` for the full node-shape catalog with examples.

## Companion Files

- `references/node-types.md` — node shape catalog with semantic meaning
- `references/color-palette.md` — default diagram color palette and usage rules
- `references/layout-patterns.md` — layout rules for developer vs. client variants
- `templates/developer-onboarding.excalidraw` — starter JSON for Case A
- `templates/client-overview.excalidraw` — starter JSON for Case B
- `scripts/validate-diagram.sh` — validates a diagram against required structure
