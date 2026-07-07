---
name: poc-scoping-doc
description: Use when a prospect has greenlit a proof-of-concept or pilot and needs a scoping document before the trial's engineering work starts. Triggers include a request to scope the POC, to write trial success criteria, to draft a pilot agreement, or any case where environment/data requirements, timeline, and win/no-win exit criteria for a customer trial have not yet been written down. Also use when an in-flight POC is drifting in scope and needs to be re-anchored to a written document.
---

# poc-scoping-doc

## Overview
Templates a proof-of-concept scoping document — success criteria, environment and data requirements, timeline, stakeholder responsibilities, and explicit win/no-win exit criteria — so both sides agree on what "the POC succeeded" means before any engineering work starts.

## When to use
- A prospect has agreed to run a POC, pilot, or trial and no scoping document exists yet.
- An existing POC is drifting — scope creep, an unclear success bar — and needs to be re-anchored to a written document.
- A deal is stalled in an extended, open-ended trial and needs an explicit exit-criteria conversation forced by a document.

## Workflow
1. **Gather inputs before drafting.** Do not scaffold from a blank template with guessed values. Pull:
   - The stated business problem — not just the feature request — and who owns it on the customer side.
   - Any prior discovery or RFP notes for candidate success criteria (see `discovery-call-question-bank` / `rfp-response-drafter` outputs).
   - Technical constraints: environment (sandbox vs. production-adjacent), data volume/sensitivity, integration points, and access the customer will and will not grant.
2. **Draft the sections in order** — each section constrains the next:
   - **Business problem and success definition** — the outcome that, if achieved, moves the customer toward a purchase decision. Push for a *measurable* criterion (e.g., "reduce processing time by 30%" or "successfully ingest 10,000 records of type X"), never a vague "see if it works."
   - **Scope boundaries** — an explicit in-scope and out-of-scope list. A POC without an out-of-scope list quietly becomes an unpaid implementation.
   - **Environment and data requirements** — the access, test data, and infrastructure the customer must provide, and by when.
   - **Timeline** — start date, checkpoint(s), and a hard end date. A POC without a hard end date does not end.
   - **RACI** — an owner for every deliverable on both sides: the customer's technical contact, executive sponsor, the solutions engineer, and any implementation partner.
   - **Win/no-win exit criteria** — the explicit conditions under which the POC is declared successful (triggers a purchase conversation) versus unsuccessful (triggers a wrap-up, not an indefinite extension).
3. **Flag every missing or assumed input** rather than silently filling in a plausible-sounding default. Success criteria and exit criteria in particular are a customer negotiation, not a drafting decision — surface the gap instead of guessing.
4. **Keep it short.** A POC scoping document that both a technical and an executive stakeholder will actually read beats a thorough one that requires a meeting to summarize.

## Checklist / quality gate
- Success criteria are measurable, not vague.
- An explicit out-of-scope list exists.
- A hard end date and checkpoint cadence are both stated.
- Win and no-win exit conditions are both written down, not just the win path.
- A RACI names an owner for every deliverable on both sides.
- Every assumed or missing input is flagged, not silently defaulted.

## References
- Puppydog — Sales Engineer Demo Workflow: https://www.puppydog.io/blog/sales-engineer-demo-workflow
- Steerlab — What Is a Solution Engineer?: https://www.steerlab.ai/blog/what-is-solution-engineer

## Composition
Consumes `discovery-call-question-bank` output (business-problem framing) and `rfp-response-drafter` output (deal-specific commitments already made) as inputs. Hands off to `customer-architecture-diagram` once environment and integration requirements are scoped, and to `adr-authoring` if the POC's outcome drives a build-vs-buy or architecture decision.
