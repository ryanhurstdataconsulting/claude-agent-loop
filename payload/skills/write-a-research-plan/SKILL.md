---
name: write-a-research-plan
description: Use when a user-research study is being scoped and needs its objectives, method, and timeline locked down before recruiting starts — turning a vague business question ("do users understand our onboarding?") into a concrete research plan. Triggers include requests to "scope a study," "write a research plan," "decide interviews vs. survey," or "plan a usability test," and file/artifact patterns like a research-plan doc, a discovery-phase brief, or a study kickoff outline.
---

# write-a-research-plan

## Overview
Turns a business or product question into a scoped, method-matched research
plan: research questions, method selection, participant criteria, timeline,
and analysis approach. It owns the "what are we even asking, and how will we
find out" step that has to happen before any recruiting, screening, or field
work begins.

## When to use
- A stakeholder poses a fuzzy question ("why are users dropping off at
  checkout?") that needs to become answerable research questions.
- A study needs its method chosen — interview, usability test, survey, diary
  study, or field study — before recruiting can start.
- A team is about to commission research and needs a lightweight plan
  document to align stakeholders before spending recruiting budget.
- A researcher needs to justify sample size, timeline, or method trade-offs to
  a skeptical stakeholder ("why not just send a survey?").

## Workflow
1. **Extract the decision the research must inform.** Every study plan starts
   from a decision, not a topic. "Understand onboarding" is a topic; "decide
   whether to redesign step 2 of onboarding before next release" is a
   decision. Push back on vague asks until you can name the decision.
2. **Convert the decision into 2-4 research questions.** Each should be
   answerable, not leading, and scoped to what this study — not some future
   one — can actually resolve.
3. **Select the method using the attitudinal/behavioral × qualitative/
   quantitative matrix:**
   - *Attitudinal + qualitative* — interviews, focus groups: what people say
     they think or want.
   - *Attitudinal + quantitative* — surveys: what people say, at scale.
   - *Behavioral + qualitative* — usability tests, field studies: what people
     actually do, observed closely.
   - *Behavioral + quantitative* — analytics, A/B tests: what people actually
     do, at scale.
   Match the cell to the research question type. A question about *why* users
   abandon a flow needs a qualitative, usually behavioral, method (usability
   test) — not a survey, which only captures stated attitudes.
4. **Check constraints before finalizing the method.** Timeline, budget,
   access to the target population, and whether a prototype or live product
   exists all narrow the field faster than theory does. A generative,
   early-stage question with no prototype pushes toward interviews or field
   studies; a comparative, late-stage question with a working prototype
   pushes toward usability testing or a survey.
5. **Draft the plan** with these sections: background and decision it
   informs, research questions, method and rationale, participant criteria
   (who, how many, screening logic pointer), timeline (recruit → field →
   synthesize → report, with dates), and planned analysis approach (thematic
   coding, statistical test, etc.).
6. **Size the sample to the method**, not to a fixed rule of thumb: small
   qualitative studies (5-8 participants per segment) are standard for
   usability testing and interviews because they reach thematic saturation;
   quantitative studies need power-analysis-driven or convention-driven
   minimums (roughly 100+ for a survey intended to segment or cross-tabulate).
7. **Name what this study will NOT answer.** An explicit out-of-scope line
   prevents scope creep once findings start coming in and stakeholders start
   asking follow-up questions the study was never built to answer.

## Checklist / quality gate
- [ ] Every research question traces back to a named decision, not just a topic.
- [ ] The chosen method matches the attitudinal/behavioral ×
      qualitative/quantitative cell the research questions actually live in.
- [ ] Participant criteria and target sample size are stated, with a
      rationale (saturation for qualitative, power/segmentation for
      quantitative).
- [ ] Timeline has explicit phase dates (recruit, field, synthesize, report),
      not just a single due date.
- [ ] An out-of-scope section names what the study will not resolve.
- [ ] The plan does not silently assume a screener or discussion guide exists —
      flag those as follow-on deliverables if the study needs one.

## References
- NN/g, "15 User Research Methods Beyond Usability Testing" — https://www.nngroup.com/videos/15-user-research-methods-beyond-usability-testing/
- UX research plan template guide — https://www.roastmyweb.com/blog/ux-research-plan-template

## Composition
Feeds `draft-discussion-guide-and-screener` (the plan's objectives and
participant criteria become the guide's question flow and the screener's
disqualifying logic) and `design-a-survey` (when the method chosen is a
survey). Findings from the resulting study flow into
`synthesize-with-affinity-mapping` for analysis and, once written up, into
`maintain-research-repository` for long-term reuse. Overlaps with a
prototype-testing plan (Product Design) and a validation-planning step
(Product Management) — reuse this skill for the plan itself in either case.
