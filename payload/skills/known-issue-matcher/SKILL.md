---
name: known-issue-matcher
description: Use when an incoming support ticket's symptoms need to be checked against a known-issues list, knowledge base, or history of resolved tickets before triage or reply. Triggers include a new ticket with a recognizable error message or stack trace, a support agent asking "has this been reported before," a ticket about to be escalated that has not yet been checked against existing documentation, or a request for a canned-response draft grounded in a prior resolution. Searches the knowledge base and past resolved tickets for a match, then proposes a response citing the specific match with a stated confidence level — never a fabricated or unstated-confidence answer.
---

# known-issue-matcher

## Overview
Checks an incoming ticket's symptoms against a known-issues database, knowledge
base, and history of resolved tickets before anyone drafts a reply from
scratch. It owns one job: produce a grounded, cited answer with an honest
confidence flag, or say plainly that no match exists — never a
confident-sounding answer that is not backed by a real source.

## When to use
- A new ticket contains a specific error message, error code, or stack trace
  that might already be documented.
- A support agent is about to draft a reply and wants to check whether the
  issue has a known resolution first.
- A ticket is being considered for escalation and needs a "has this been seen
  before" check before it consumes engineering time.
- A canned response needs to be drafted that cites a specific KB article or
  prior resolved ticket rather than a paraphrase from memory.

## Workflow

1. **Extract and normalize the error signature.** Pull the exact error text,
   error code, stack-trace fingerprint, and reproduction steps from the
   ticket. Strip variable data that will not match across occurrences —
   timestamps, request IDs, user-specific file paths, account identifiers —
   so the signature generalizes to "this class of problem," not just this one
   report.
2. **Search in order of authority, not convenience:**
   - The known-issues database first (curated, highest confidence by
     definition).
   - The knowledge base (published articles) second.
   - Past resolved tickets with a matching or closely related signature
     third.
   - Recent release notes or changelogs fourth — useful for catching
     "this is a new regression from last week's release" before it is
     formally documented anywhere.
3. **Score the match confidence explicitly** — do not present any match as
   certain unless it is:
   - **High** — same error code/signature and same reproduction path as the
     matched source.
   - **Medium** — same error signature, but reproduction steps or
     environment differ somewhat.
   - **Low** — thematically similar only (same symptom area, different
     underlying signature). Treat as a lead for the investigating human, not
     an answer to send.
4. **Draft the canned response only for high- or medium-confidence matches,**
   and cite the specific source (KB article ID/link, or the ticket ID it was
   resolved in) inline. State the confidence level in the internal note even
   when the customer-facing text reads as a normal answer.
5. **Do not fabricate a resolution when no match is found.** State plainly
   that no known issue matches, and route the ticket to full diagnostic
   investigation or escalation instead of stretching a low-confidence,
   thematically-adjacent match into a false "here's your fix." A wrong
   confident answer costs more support time than an honest "still
   investigating."
6. **Flag the search-came-up-empty case as a candidate for new
   documentation.** A ticket that resolves without a known-issue match is
   exactly the signal that should trigger a new knowledge-base article once
   resolved, so the next occurrence gets a high-confidence match.

**Common gotchas:**
- Matching on a generic error string ("connection failed," "unauthorized")
  without checking that the surrounding context (endpoint, product area,
  customer environment) actually lines up — generic errors have many
  distinct root causes.
- Citing a KB article that is stale (references a version or UI that has
  since changed) as if it were current — check the article's last-updated
  date and flag if it looks out of date rather than sending it as-is.
- Treating "no exact match found" as license to guess based on general
  product knowledge — the whole point of this skill is a grounded answer;
  an ungrounded guess belongs in a different, clearly-labeled response path.

## Checklist / quality gate
- [ ] The error signature was normalized (variable data stripped) before
      searching, not matched on raw, unedited ticket text.
- [ ] The search covered known-issues, knowledge base, resolved tickets, and
      recent release notes, in that order.
- [ ] Every proposed match carries an explicit confidence level (high/
      medium/low) and a citation (article ID, ticket ID, or changelog
      entry).
- [ ] No canned response was sent on a low-confidence or no-match result
      without being routed to further investigation instead.
- [ ] A no-match result was flagged as a candidate for new knowledge-base
      content.
- [ ] Customer-facing response text passes a grammar check before it ships.

## References
- Jam.dev — [The Rise of Technical Support Engineers](https://jam.dev/blog/the-rise-of-technical-support-engineers/) — cites roughly two-thirds of tickets resolved at first tier once structured knowledge bases and decision trees are in place.

## Composition
Consumes the error signature and product-area tag produced by
`ticket-triage-classifier`. Feeds a decision point: a confirmed match closes
the loop with a grounded reply; a confirmed non-match routes to full
diagnostic work and, on eventual resolution, to
`kb-article-from-resolved-ticket` so the gap gets filled. Shares its
"grounded answer with a stated confidence flag against an approved source"
pattern with an `rfp-response-drafter` skill used in a sales-engineering
context.
