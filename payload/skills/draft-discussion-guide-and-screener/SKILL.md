---
name: draft-discussion-guide-and-screener
description: Use when an interview or usability study needs a moderator discussion guide and a participant screener drafted from an existing research plan. Triggers include requests to "write an interview guide," "draft a screener," "build a usability-test script," or "write recruiting criteria," and file/artifact patterns like a moderator guide, a screening survey, or a task-based usability script.
---

# draft-discussion-guide-and-screener

## Overview
Turns a research plan's objectives into two working documents: a moderator
discussion guide (interview questions or usability-test tasks, sequenced) and
a participant screener (qualifying and disqualifying questions that hit the
target sample). It owns the "what do we actually say and ask" step between
having a plan and running the first session.

## When to use
- A research plan exists and the study needs a moderator-ready guide before
  recruiting or scheduling sessions.
- A study needs a screener survey to filter respondents down to the target
  participant profile.
- An existing guide feels unfocused or too long for the session length
  allotted and needs restructuring.
- A screener is over- or under-qualifying respondents (too few pass, or
  clearly wrong people are getting through) and needs its logic tightened.

## Workflow
1. **Pull the research questions and participant criteria from the research
   plan.** Do not draft a guide or screener from scratch without this input —
   if no plan exists, the questions and criteria need to be established first
   (see `write-a-research-plan`).
2. **Sequence the discussion guide broad to specific.** Open with warm-up,
   low-stakes context questions (role, current workflow) before narrowing to
   the specific behaviors or attitudes the study needs to probe. Save the most
   sensitive or leading-adjacent questions for the middle-to-end, once
   rapport is established.
3. **Write questions that elicit stories, not opinions.** Prefer "walk me
   through the last time you did X" over "do you like X?" Behavioral,
   past-tense framing produces concrete, checkable data; opinion questions
   produce unreliable stated preference.
4. **For usability tests, write tasks, not questions.** A task gives the
   participant a goal ("find and book a flight to Chicago for next Friday")
   without revealing the interface path — never coach them toward the
   feature being tested.
5. **Avoid leading and double-barreled phrasing** in both the guide and the
   screener: no "don't you think X is confusing," and no single question
   bundling two variables ("how easy and how fast was checkout?").
6. **Build the screener's disqualifying logic explicitly.** State the target
   profile (role, tool usage frequency, industry, etc.) as a set of
   qualifying answers, and write terminate logic for every disqualifying
   answer — including a competitor-employment or research-industry screen-out
   if the study is sensitive.
7. **Cap the guide to the session length.** Budget roughly 2 minutes per
   short question and 5-8 minutes per open-ended or task-based section; a
   60-minute interview supports about 8-10 core questions or 4-6 usability
   tasks, not more — trim before the session, not during it.
8. **Add moderator notes**, not just questions: probes to use if an answer is
   too shallow ("tell me more," "what happened next"), and a reminder of what
   NOT to say (don't confirm whether an action was "correct" mid-task).

## Checklist / quality gate
- [ ] Every guide question or task traces back to a research question in the
      plan — no orphan questions added out of curiosity.
- [ ] Question order runs broad to specific, with sensitive questions placed
      after rapport is built.
- [ ] No leading or double-barreled phrasing survives a final read-through.
- [ ] Usability tasks state a goal, not a UI path, and do not name the
      feature being tested.
- [ ] The screener has explicit terminate logic for every disqualifying
      answer, not just qualifying logic.
- [ ] The guide fits the allotted session time at the stated pace budget.

## References
- UX Army, "User Research Cheat Sheet" — https://uxarmy.com/blog/user-research-cheat-sheet-2-a-series/

## Composition
Consumes the output of `write-a-research-plan` (objectives and participant
criteria feed directly into the guide and screener). Sessions run from this
guide produce the raw notes that `synthesize-with-affinity-mapping` clusters
into themes; the finished guide and screener themselves are candidates for
storage via `maintain-research-repository` so a future study does not start
from zero.
