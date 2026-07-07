---
name: community-feedback-digest
description: Use for producing a weekly or monthly digest of developer-forum, GitHub-issue, Discord, or Stack Overflow themes for product and engineering. Triggers include a request to "summarize this month's community feedback," "what are developers complaining about," a backlog of unread forum/issue threads, or a recurring digest cadence tied to a sprint or release cycle. Clusters raw community noise into a prioritized, themed brief — it does not decide what ships.
---

# community-feedback-digest

## Overview
Clusters raw developer-community signal — forum threads, GitHub issues,
Discord/Slack channels, Stack Overflow tags — into a themed, prioritized
feedback brief for product and engineering. The one job it owns: turn scattered
qualitative noise into a structured artifact a human can act on, while leaving
the actual prioritization call to that human.

## When to use
- A recurring (weekly/monthly) community-feedback digest is due for product or
  engineering.
- A backlog of unread forum posts, GitHub issues, or community-channel messages
  needs a first pass before a planning meeting.
- Someone asks "what's the community been saying about X" ahead of a roadmap or
  triage discussion.
- A release just shipped and early community reaction needs a same-week
  temperature check.

## Workflow
1. **Define the collection window and sources explicitly.** State the date
   range and every source pulled from (specific forum, repo, channel, tag) in
   the digest header — an undated, unscoped digest cannot be trusted or
   repeated.
2. **Pull raw threads, don't summarize from memory.** Fetch actual thread text,
   issue bodies, and message content for the window; never fabricate or infer
   community sentiment without source text in hand.
3. **Cluster by theme, not by source.** Group semantically similar complaints/
   requests across a GitHub issue, a forum post, and a Discord thread into one
   theme if they're the same underlying pain point — a digest organized by
   platform instead of by theme buries the signal.
4. **Tag each theme by product area** so it routes to the right team, and by
   **type**: bug report, feature request, confusion/docs gap, or praise. A
   digest that only surfaces complaints undersells what is working.
5. **Attach a frequency and severity signal to each theme** — how many distinct
   threads/people raised it, and how blocking it sounded (workaround exists vs.
   "I can't ship"). This is the input to prioritization, not the
   prioritization itself.
6. **Quote representative examples, not just counts.** One or two verbatim
   (lightly trimmed) quotes per theme keep the digest grounded in what was
   actually said, and let a reader sanity-check the clustering.
7. **Flag — do not decide — what needs escalation.** Mark themes that look
   urgent (security concern, mass confusion on a new release, a viral
   complaint thread) for human triage rather than silently ranking them as
   "top priority." The clustering and counting are agent-native; the call on
   what the team acts on next is not.
8. **Close with a delta against the last digest**, if one exists — new themes,
   themes that grew, themes that resolved — so the reader sees trend, not just
   a snapshot.

## Checklist / quality gate
- [ ] Collection window and every source are stated explicitly in the header.
- [ ] Every theme is grounded in real pulled thread/message text, with at
      least one verbatim quote.
- [ ] Themes are grouped across sources, not siloed by platform.
- [ ] Each theme carries a frequency count and a severity signal.
- [ ] Praise/positive signal is included alongside complaints, not filtered
      out.
- [ ] Escalation candidates are flagged for human review, not auto-prioritized
      by the digest itself.
- [ ] A trend delta against the prior digest is included when a prior digest
      exists.

## References
- [Google Developers (Medium) — The Core Competencies of Developer Relations](https://medium.com/google-developers/the-core-competencies-of-developer-relations-f3e1c04c0f5b) —
  the developer-feedback loop back to product and engineering as a core
  developer-relations competency.

## Composition
Overlaps with a technical-support `known-issue-matcher`/ticket-theme
clustering skill — when both a support queue and a community forum exist,
reuse the same clustering approach across both. Hands escalated themes to a
`bug-report-escalation-writer` or a `raid-log-maintainer` for tracked
follow-up. Feeds into an `exec-status-report` when community sentiment needs
to roll up to leadership altitude.
