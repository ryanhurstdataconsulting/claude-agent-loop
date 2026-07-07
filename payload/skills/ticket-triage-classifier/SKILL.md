---
name: ticket-triage-classifier
description: Use when a new inbound support ticket needs categorization, severity, and product-area tagging before it reaches an engineer's queue. Triggers include a raw ticket dropping into an unsorted inbox, a request to "triage this," a queue backlog needing a first pass, an unlabeled bug report, or a support tool asking for a category/severity/priority field before it will accept the ticket. Extracts key fields from ticket text and attached logs, matches them against a product taxonomy, and assigns severity per a documented rubric — flagging anything ambiguous for human review instead of guessing.
---

# ticket-triage-classifier

## Overview
Turns a raw inbound support ticket into a categorized, severity-tagged, routable
item before it reaches an engineer's queue. It owns one job: extract the
structured fields a queue needs (product area, error signature, customer
impact, severity) from unstructured ticket text and logs, and route with a
stated confidence rather than a silent guess.

## When to use
- A new ticket lands with no category, severity, or product-area tag set.
- A backlog of unsorted tickets needs a first triage pass before a queue
  review.
- A support tool or workflow requires a category/severity field populated
  before the ticket can be assigned or routed.
- A ticket's initial tag looks wrong after more information (logs, a reply)
  comes in and needs re-triage.

## Workflow

1. **Extract structured fields from the raw ticket.** Pull the subject, body,
   any attached logs or screenshots, and available customer metadata (plan
   tier, environment, product version, account age). Do not rely on the
   subject line alone — the real symptom is often only in the body or an
   attached log.
2. **Match against the product-area taxonomy.** Compare the extracted error
   signature and described behavior against a maintained list of product
   areas/components. If no taxonomy entry fits cleanly, do not force the
   closest-sounding tag — flag it `needs-taxonomy-review` and route to a
   human rather than mis-filing it into the wrong team's queue.
3. **Assign severity from a documented rubric**, not intuition. A typical
   four-tier rubric:

   | Tier | Definition | Example |
   |---|---|---|
   | P0 / Sev1 | Production down, data loss, or security exposure, no workaround | Login is broken for every customer |
   | P1 | Major feature broken, no workaround | Checkout fails for one payment method |
   | P2 | Feature degraded, workaround exists | Export is slow but completes |
   | P3 | Cosmetic, question, or feature request | Button label is misspelled |

   Weight the tier by customer impact — number of users affected, plan tier,
   and any contractual SLA — as a multiplier, not a separate free-floating
   field. A P2-shaped bug affecting an entire enterprise account's production
   environment can warrant a P1 escalation; state the reasoning when it does.
4. **Check for duplicates or related open tickets before filing a new one.**
   Search recent tickets with a similar error signature or from the same
   account/incident. Link related tickets instead of creating parallel,
   disconnected threads for what is one underlying problem.
5. **Route to the correct queue or team** based on the resolved product-area
   tag, honoring any team-specific routing rules (e.g., security-flagged
   tickets always route through a security review step regardless of
   severity).
6. **State a confidence level and rationale with every classification.** A
   ticket triaged with low confidence should say so explicitly (category,
   severity, and the specific ambiguity) so a human reviewer can correct it
   quickly instead of re-deriving the triage from scratch.
7. **Log the classification decision** — category, severity, rationale,
   duplicate links — so it is auditable and reusable as input to downstream
   metrics and to a known-issue match on the next similar ticket.

**Common gotchas:**
- Treating the loudest word in the subject line ("URGENT," "CRITICAL") as the
  severity signal — customer-asserted urgency is an input to the rubric, not
  a substitute for it.
- Under-triaging a security-adjacent symptom (auth failure, data visible to
  the wrong account) because it "sounds like" a minor bug — route anything
  with a plausible security angle through the security-review path even at
  low confidence.
- Silently merging two tickets that share an error message but have different
  root causes — link them for investigation, do not assume they are the same
  issue until confirmed.

## Checklist / quality gate
- [ ] Product-area tag is set from the taxonomy, or explicitly flagged
      `needs-taxonomy-review`.
- [ ] Severity is assigned from the documented rubric, with customer-impact
      weighting applied and stated, not asserted without reasoning.
- [ ] Duplicate/related-ticket search was performed and any matches linked.
- [ ] Every classification carries a confidence level; low-confidence
      classifications are flagged for human review rather than filed
      silently.
- [ ] The classification decision and rationale are logged for audit and
      reuse.
- [ ] Any customer-facing summary text passes a grammar check before it
      ships.

## References
- Jam.dev — [The Technical Customer Support Skills That Will Define 2026](https://jam.dev/blog/the-technical-customer-support-skills-that-will-define-2026/) — cites LLM-driven ticket categorization and severity assignment as an established 2026 support-engineering practice.

## Composition
Feeds `known-issue-matcher`, which takes the extracted error signature and
searches for a resolution before a human ever picks the ticket up. Feeds
`bug-report-escalation-writer` once a ticket is confirmed as a genuine
product bug — the severity and affected-customer data gathered here carries
straight into that report. Shares its clustering pattern with a
community-feedback-digest skill when both a support queue and a public
forum need consistent theme tagging.
