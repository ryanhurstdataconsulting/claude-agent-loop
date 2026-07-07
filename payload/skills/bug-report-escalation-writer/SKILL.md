---
name: bug-report-escalation-writer
description: Use when a support ticket is confirmed as a genuine product bug and needs to go to engineering as a structured report rather than a forwarded conversation thread. Triggers include a support agent deciding "this is not a known issue and not user error," a request to "file this as a bug," an escalation that needs repro steps and logs assembled before it can be handed to engineering, or an engineering team rejecting an escalation for missing environment/repro information. Assembles reproduction steps, environment details, logs or API traces, expected-versus-actual behavior, severity, and affected-customer count into the engineering team's bug-report template, checking for duplicates before filing.
---

# bug-report-escalation-writer

## Overview
Turns a confirmed product bug into a structured report engineering can act on
without a round trip back to support for missing information. It owns one
job: the transformation from diagnostic notes and customer conversation into
a complete, minimal, duplicate-checked bug-report filing.

## When to use
- A ticket has been ruled out as a known issue (see `known-issue-matcher`) and
  ruled out as user error or misconfiguration — it is a genuine, undocumented
  product bug.
- A support agent or lead decides an issue needs to be filed for engineering
  rather than resolved at the support tier.
- An escalation was bounced back by engineering for missing repro steps,
  environment details, or logs.
- Multiple tickets are converging on what looks like the same underlying bug
  and need to be consolidated into one filing.

## Workflow

1. **Confirm the gate before writing anything.** This skill assumes the bug
   determination has already been made — it is not the tool for deciding
   whether something is a bug. If that determination has not happened yet,
   route back through triage and known-issue matching first.
2. **Assemble the required fields; do not file with gaps silently left
   blank:**
   - **Title** — a concise, symptom-based summary (what breaks, not the
     ticket number).
   - **Environment** — OS/browser, app or API version, deployment
     environment (production/staging), and any relevant configuration.
   - **Reproduction steps** — numbered, minimal, and specific. Trim to the
     smallest reliable sequence that still reproduces the bug; a report with
     twelve steps when four suffice slows down the engineer reading it.
   - **Expected vs. actual behavior** — stated as two short, separate
     statements, not folded into the reproduction narrative.
   - **Logs, stack traces, or API traces** — attached or excerpted, with any
     customer PII, credentials, or tokens redacted before attaching.
   - **Severity** — assigned using the same rubric as ticket triage, so
     severity is comparable across the queue rather than re-invented per
     report.
   - **Affected-customer scope** — an aggregate count and, where relevant,
     account tier/segment, rather than a bare unlabeled list of names.
   - **First-seen date** and any related ticket IDs.
3. **Note reproducibility honestly.** If the bug is intermittent, state the
   observed frequency ("reproduces roughly 1 in 5 attempts") rather than
   presenting a flaky repro as deterministic — this materially changes how
   engineering triages and debugs it.
4. **Check for an existing bug report before filing a new one.** Search the
   engineering tracker for a matching or closely related open issue. If one
   exists, link the ticket to it and add any new information (a new
   environment, a tighter repro) as a comment instead of creating a
   duplicate filing.
5. **Redact before attaching, not after.** Strip customer PII, secrets, and
   tokens from logs and traces before they leave the support system — this
   is a one-way gate, not a step to circle back to later.
6. **File using the engineering team's actual template and component/owner
   tags**, so the report lands in the right queue without a manual re-route.
7. **Link the filed bug report back to the originating support ticket(s)**,
   so support can follow up with affected customers once it is resolved,
   and so `raid-log-maintainer` (or the equivalent tracked-item system) has a
   single source of truth for the item's status.

## Checklist / quality gate
- [ ] The bug determination gate was already passed — this was not used to
      decide whether something is a bug.
- [ ] Every required field is populated, or explicitly marked unknown rather
      than left blank or guessed.
- [ ] Reproduction steps are minimized and verified, with intermittent
      frequency stated if the bug is not deterministic.
- [ ] All logs, traces, and attachments are redacted of PII, secrets, and
      tokens before filing.
- [ ] A duplicate-issue search was performed; any match is linked, not
      re-filed.
- [ ] Severity was assigned from the shared rubric, and affected-customer
      scope is stated as an aggregate.
- [ ] The filed report links back to the originating ticket(s).
- [ ] Report prose passes a grammar check before it ships to engineering.

## References
- Jam.dev — [The Technical Customer Support Skills That Will Define 2026](https://jam.dev/blog/the-technical-customer-support-skills-that-will-define-2026/) — cites structured bug documentation as a top support-engineering competency.

## Composition
Consumes the severity rubric and product-area tag from
`ticket-triage-classifier`, and is typically invoked only after
`known-issue-matcher` confirms no existing resolution applies. Hands off to
`raid-log-maintainer` (or an equivalent tracked-item system) so the escalated
bug becomes an owned, tracked item rather than a one-time report that goes
quiet. Once fixed, feeds `kb-article-from-resolved-ticket` if the fix or a
workaround is worth documenting for future occurrences.
