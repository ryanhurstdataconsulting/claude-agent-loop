---
name: write-a-prd
description: Use when a feature idea, one-line brief, or chat thread needs to become a structured product requirements document (PRD) before engineering can scope or estimate it. Triggers include "write a PRD for...", "turn this into a spec", a ticket that says "needs requirements", or a request to define user stories, acceptance criteria, and success metrics for a new feature. Also fires when reviewing a thin or ambiguous PRD that engineering has bounced back for clarification.
---

# write-a-prd

## Overview
Converts a problem statement, target user, and goal into a structured product
requirements document that engineering, design, and stakeholders can align
around before work is scoped. The one job it owns: turning an underspecified
ask into a complete, reviewable requirements artifact — not writing the
feature's implementation plan, and not making the prioritization call on
whether the feature should be built at all.

## When to use
- A feature idea, ticket, or one-paragraph brief needs to become a document
  engineering can size and design can pick up.
- A stakeholder asks "can you write this up properly" after a hallway or
  chat conversation about a feature.
- An existing PRD is thin — missing acceptance criteria, scope boundaries, or
  success metrics — and needs to be filled out before a planning meeting.
- A request explicitly asks for user stories, non-functional requirements, or
  "what does done look like" for a piece of work.

## Workflow
1. **Intake the problem, not the solution.** Extract (or ask for, if
   missing): the problem being solved, the target user/persona, the business
   or user goal, and any stated constraints (deadline, platform, dependency).
   If the request jumps straight to a solution ("add a button that..."),
   work backward one level to confirm the underlying problem before drafting.
2. **Fill the template, section by section:**
   - **Context / problem statement** — why this matters now, who is affected,
     what happens if nothing ships.
   - **Goal and success metrics** — the outcome the feature should produce,
     stated as a measurable metric (not "improve engagement" — "increase
     7-day retention from X% to Y%"). Flag metrics that can't be measured
     with instrumentation the team actually has.
   - **User stories** — "As a `<persona>`, I want `<capability>`, so that
     `<benefit>`," one per distinct user need, not one per UI element.
   - **In-scope / out-of-scope** — an explicit boundary list. Out-of-scope is
     as important as in-scope; write it down even when it seems obvious.
   - **Acceptance criteria** — testable, binary pass/fail statements per user
     story (Given/When/Then works well). If a criterion can't be verified by
     a test or a manual check, rewrite it until it can.
   - **Non-functional requirements** — performance, accessibility, security,
     localization, and platform constraints that don't show up in a user
     story but block release.
   - **Open questions** — anything still ambiguous, called out explicitly
     rather than silently resolved with an assumption.
3. **Flag gaps back to the requester instead of inventing them.** Missing
   target user, no success metric, or an ambiguous scope boundary are the
   three most common holes — surface them as explicit questions rather than
   guessing a plausible answer and moving on.
4. **Keep the strategic judgment out of the document's structure.** The PRD
   records what "done" means for a decision that's already been made to
   pursue; it is not the venue for re-litigating whether the feature should
   exist (that's a roadmap or prioritization call — see Composition).

## Checklist / quality gate
- [ ] Every user story has at least one testable acceptance criterion.
- [ ] Success metrics are measurable with existing or planned
      instrumentation, not aspirational language.
- [ ] Out-of-scope section exists and is non-empty for any feature with real
      boundary risk.
- [ ] No unresolved ambiguity was silently assumed — check the open-questions
      section is either filled in or genuinely empty.
- [ ] Non-functional requirements (performance, accessibility, security) were
      considered even if the answer is "none apply."

## References
- Atlassian PRD template — https://www.atlassian.com/software/confluence/templates/product-requirements
- Atlassian, "What is a PRD" — https://www.atlassian.com/agile/product-management/requirements

## Composition
- Upstream of `prioritize-with-rice` and `build-a-roadmap` — a PRD documents
  a feature that's already been chosen; prioritization and roadmap sequencing
  happen before or alongside it, not inside it.
- Pairs with `draft-okrs` when the PRD's success metric should trace back to
  a team or company key result.
- Hands off to sprint-planning or ticket-breakdown work once acceptance
  criteria are locked.
