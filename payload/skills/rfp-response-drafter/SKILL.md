---
name: rfp-response-drafter
description: Use when an inbound RFP, security questionnaire, or vendor-due-diligence form arrives that mixes boilerplate compliance questions with deal-specific technical ones. Triggers include a spreadsheet or portal export of security-questionnaire questions (for example a CAIQ or SIG Lite), a prospect's procurement team requesting a completed RFP template, or a request to draft answers grounded in an approved answer library rather than free-generated claims. Also use when auditing whether an existing RFP answer library is still accurate against the current product and security posture.
---

# rfp-response-drafter

## Overview
Drafts first-pass answers to RFP and security-questionnaire questions by matching each question against an approved-answer knowledge base, producing a confidence-flagged draft that separates answers grounded in an approved source from ones that need an engineer's judgment call — never inventing an ungrounded claim about security or compliance posture.

## When to use
- An RFP, RFI, or security questionnaire needs first-pass answers before a deadline.
- A sales or solutions-engineering request to "fill this out from our answer library."
- A recurring audit of a canonical answer library against the current product/security state — a periodic refresh, not a one-off deal response.
- A request to speed up a response ("we usually spend hours on this") that does not also ask to skip grounding or confidence flags — it never does, even implicitly.

## Workflow
1. **Ingest the question set.** Normalize into one item per question, keeping the original row/section identifier so the output can be reassembled into the requester's format.
2. **Locate or confirm the approved-answer library.** Search for an existing source: a security whitepaper, trust-center page, prior RFP responses, or compliance certifications. If no organized library exists, stop and flag this as a blocker before drafting — never draft against un-sourced tribal knowledge.
3. **Classify every question:**
   - **Exact match** to an approved source → draft the answer and cite the source (document plus section/date).
   - **Partial match or inference required** → draft with an explicit confidence flag, e.g. `[LOW CONFIDENCE — inferred from <source>, needs review]`.
   - **No match, deal-specific, or a commitment-creating question** (a custom SLA, a contractual carve-out, a non-standard integration) → do not draft; flag for a human subject-matter expert with the question quoted verbatim.
4. **Never answer definitively** on security certifications the organization does not hold, uptime/SLA numbers absent from an approved source, data-residency claims, or anything that creates contractual liability. These always route to a human, regardless of how confident a draft pass seems.
5. **Preserve the requester's format** — reproduce their spreadsheet or template structure and question numbering exactly, so the reviewer can drop the draft straight back in.
6. **Deliver a coverage summary**: N questions answered from the library, N flagged low-confidence, N routed to a human — so the reviewer triages efficiently instead of re-reading every row.
7. **Close the loop on the library.** A repeated question across RFPs is a signal to add or refresh a library entry, not to re-solve the same question ad hoc every time.

## Checklist / quality gate
- Every drafted answer traces to a cited source, or carries an explicit confidence flag.
- Zero answers assert something absent from the approved library (certifications, SLAs, data residency, security controls).
- Deal-specific or contractual questions are separated out, never silently drafted.
- Output preserves the original question numbering and format.
- A coverage summary (answered / flagged / routed-to-human counts) is included.

## References
- Tribble — Security Questionnaire Automation: https://tribble.ai/blog/security-questionnaire-automation/
- Conveyor — Using AI software to respond to Security Questionnaires and RFPs: https://www.conveyor.com/blog/everything-you-need-to-know-using-ai-software-to-respond-to-security-questionnaires-and-rfps

## Composition
Pairs with `discovery-call-question-bank` (deal context that distinguishes boilerplate from deal-specific questions) and hands off to `poc-scoping-doc` when an RFP response leads into a proof-of-concept, carrying forward any commitments already made. The approved-answer library it drafts from is typically authored with `docs-diataxis-authoring` and kept grammatically clean with `prose-style-lint`. It shares its "grounded answer plus confidence flag" pattern with the technical-support-side knowledge-base-matching skill for resolved-ticket lookups, where one exists.
