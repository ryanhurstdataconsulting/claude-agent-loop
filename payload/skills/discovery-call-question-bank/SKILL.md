---
name: discovery-call-question-bank
description: Use when preparing for a discovery call with a new prospect, especially in an unfamiliar vertical or use case, and a tailored set of questions is needed to surface the real business problem behind the stated request. Triggers include a request to prep for a call with a named prospect, a request for a discovery question bank or call-prep sheet, or any pre-call research task that should map technical constraints and the procurement/decision-maker landscape before the conversation happens.
---

# discovery-call-question-bank

## Overview
Generates a tailored discovery-call question bank that probes past a prospect's stated request to the underlying business problem, technical constraints, and buying-process context — organized so the human running the call can adapt on the fly rather than read a script.

## When to use
- A discovery call is scheduled with a new prospect and no structured prep exists yet.
- The prospect is in an unfamiliar vertical, where generic discovery questions risk missing domain-specific constraints.
- A stated request (for example, "we need an X integration") needs to be interrogated for the underlying business driver before a solution gets proposed.
- Prior call notes exist and need to become a sharper, more targeted follow-up question set.

## Workflow
1. **Gather available context first.** The prospect's industry/vertical, company size, the inbound request as stated, and any notes from a prior touchpoint (sales, marketing, support). Never generate generic questions when specific context is already available and unused.
2. **Organize the question bank into layers, in the order a discovery call actually flows:**
   - **Business problem** — what breaks or costs money today, and what triggered the prospect to look now. A "why now" question surfaces urgency and budget-cycle timing.
   - **Stated request vs. underlying need** — questions that test whether the inbound request is the actual fix or a symptom-level ask. "Walk me through what happens today when X occurs" surfaces more than "do you need feature Y."
   - **Technical constraints** — current stack, integration points, data volume/sensitivity, compliance requirements, and anything that would block adoption regardless of feature fit.
   - **Procurement and decision landscape** — who else is involved in the decision, what the buying process and timeline typically look like at a company of this size and vertical, budget ownership, and competing initiatives for the same budget.
3. **For an unfamiliar vertical, front-load a short domain-context brief** (a few sentences on how the vertical typically operates, its regulatory environment, and common terminology) so the question bank uses the prospect's own vocabulary instead of generic language.
4. **Mark must-ask questions versus nice-to-have ones.** Must-ask items block a viable proposal without an answer; nice-to-have items sharpen the pitch but are not blocking. A short call cannot cover everything, so the human running it needs a priority order, not a flat list.
5. **Keep it a bank, not a script.** Group by theme with two or three phrasing options per theme so the caller can pick whichever fits how the conversation is actually going.

## Checklist / quality gate
- Questions are organized business-problem-first, not feature-request-first.
- At least one question tests the stated request against the underlying need.
- Technical-constraint and procurement/decision-maker questions are both present.
- Must-ask items are distinguished from nice-to-have items.
- Vertical-specific context and vocabulary are reflected when the prospect's industry was known going in.

## References
- Walnut — What Are Solutions Engineers and Why Are They Vital in SaaS Sales?: https://www.walnut.io/blog/sales-tips/what-are-solutions-engineers/

## Composition
Feeds business-problem and technical-constraint context forward into `poc-scoping-doc` (success criteria) and `rfp-response-drafter` (deal-specific-question triage). Upstream of `customer-architecture-diagram` once the technical-constraints layer surfaces integration requirements.
