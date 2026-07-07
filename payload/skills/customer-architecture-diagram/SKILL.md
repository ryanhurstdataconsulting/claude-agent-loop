---
name: customer-architecture-diagram
description: Use when a solutions architect or solutions engineer needs a target-state architecture diagram for a customer's environment or integration — showing the customer's current stack, the product's integration points, and the data flow between them. Triggers include a request to draw the integration architecture for a named customer, a proof-of-concept or statement of work that references an architecture diagram not yet created, or a request to visualize how a proposed solution fits into an existing on-prem, cloud, or hybrid customer environment.
---

# customer-architecture-diagram

## Overview
Produces a customer-environment architecture diagram — component boundaries, data flow, and integration points between the customer's existing stack and the proposed or implemented product — as diagram-as-code, so it stays versionable, reviewable, and easy to keep current as the deal or implementation evolves.

## When to use
- A proof-of-concept scoping document or statement of work needs a visual of the target-state integration architecture.
- A prospect's technical evaluator asks how the product actually connects to their environment.
- An existing diagram is stale relative to the current integration plan and needs regeneration rather than a from-scratch redraw.
- A proposal needs a current-state vs. target-state comparison to make the delta legible to a technical reviewer.

## Workflow
1. **Gather the customer's current stack.** The existing systems the integration touches, network topology (on-prem, VPC, hybrid), the auth model, and any stated constraints (no outbound internet, VPN-only access, a data-residency boundary).
2. **Gather the product's integration points.** Which APIs, webhooks, connectors, or agents the customer will run, and what each requires (inbound ports, credentials, data format).
3. **Choose the diagram's altitude to match the audience:**
   - **Executive/procurement view** — component boxes and data-flow arrows only, no protocol detail. Optimized for "do I understand what we're buying."
   - **Technical/implementation view** — protocols, ports, the auth flow, and failure/retry behavior at each integration boundary. Optimized for the customer's engineers who will build against it.
4. **Draft as diagram-as-code** (for example a Mermaid `flowchart` or `sequenceDiagram`, or an Excalidraw JSON file) rather than a one-off flattened image — this keeps the diagram diffable and regenerable as scope changes.
5. **Distinguish existing customer infrastructure from newly introduced components visually** (for example: existing components rendered solid/neutral, new/proposed components rendered with a distinct accent) so the customer sees the actual delta they are adopting, rather than a diagram that reads as a wholesale rip-and-replace when it is not.
6. **Mark trust and network boundaries explicitly** — a labeled boundary box around "customer VPC," "third-party service," or "public internet." Omitting this is the most common way these diagrams mislead a security reviewer.
7. **Validate against the gathered requirements.** Every integration point named in steps 1–2 should appear on the diagram, and every component on the diagram should trace back to a stated requirement — no orphaned boxes.

## Checklist / quality gate
- Every integration point from the requirements appears on the diagram; no orphaned components.
- Existing vs. newly introduced components are visually distinguished.
- Trust and network boundaries are explicitly labeled.
- The diagram's altitude (executive vs. technical) matches its intended audience.
- Delivered as diagram-as-code, not a flattened image with no editable source.

## References
- GitLab Handbook — Solutions Architect: https://handbook.gitlab.com/job-description-library/sales/solutions-architect/

## Composition
Consumes the environment and integration requirements gathered by `poc-scoping-doc` and `discovery-call-question-bank`. Extends a general-purpose diagram-as-code skill (an Excalidraw- or Mermaid-based diagramming skill) with a customer-environment template — the current-state/target-state framing and the trust-boundary convention above are the customer-specific additions layered on top of generic diagramming.
