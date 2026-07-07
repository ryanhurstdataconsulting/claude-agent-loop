---
name: design-a-survey
description: Use when a research question calls for quantitative or attitudinal data at scale rather than a small qualitative sample — drafting unbiased survey items, choosing scale types (Likert, NPS, semantic differential), and sequencing questions to avoid priming. Triggers include requests to "write a survey," "design an NPS/CSAT survey," "review these survey questions for bias," or "how many responses do I need," and file/artifact patterns like a draft questionnaire, a Likert-scale item list, or a survey-tool export awaiting review.
---

# design-a-survey

## Overview
Translates research questions into unbiased, well-sequenced survey items:
picks the right scale type per question, orders items to avoid priming
effects, and flags leading or double-barreled phrasing before the survey
goes to respondents. It owns quantitative-at-scale data collection, the
counterpart to the small-sample qualitative methods covered elsewhere.

## When to use
- A research question needs a large-N answer (attitudes, satisfaction,
  prioritization) rather than a small sample of deep qualitative interviews.
- An existing draft survey needs a bias review before it goes out — leading
  questions, double-barreled items, or an unbalanced scale.
- A team wants to track a recurring metric (NPS, CSAT, CES) and needs the
  instrument designed once, consistently, for repeated use.
- A survey's response rate or data quality is suspect and the instrument
  itself (not the recruiting) is the likely cause.

## Workflow
1. **Confirm quantitative-at-scale is the right method before drafting
   items.** A survey answers "how many/how much/how often," and "do people
   agree with X" — it does not answer "why," which needs a qualitative
   method. If the underlying research question is a "why," redirect to an
   interview or usability-test plan instead of forcing it into survey form.
2. **Pick the scale type to match the question:**
   - **Likert (5- or 7-point agreement/frequency)** — attitudes and
     perceptions ("I found this easy to use").
   - **NPS (0-10 likelihood to recommend)** — overall relationship health,
     tracked longitudinally; not a substitute for feature-level feedback.
   - **CSAT (satisfaction with a specific interaction)** — point-in-time,
     transactional ("How satisfied were you with support today?").
   - **CES (customer effort score)** — friction in completing a specific task.
   - **Semantic differential (bipolar adjective pairs)** — brand or product
     perception along named dimensions (e.g., "confusing — clear").
   Do not mix scale directions within one survey (some items 1=best, others
   5=best) — it silently corrupts analysis and confuses respondents.
3. **Write each item as one variable.** A double-barreled item ("how easy and
   fast was checkout?") cannot be answered or analyzed cleanly if the
   respondent's experience of the two differs — split into two items.
4. **Eliminate leading language.** Avoid framing that presupposes an answer
   ("How much did you enjoy our fast checkout?" presupposes it was fast).
   Prefer neutral framing: "How would you rate the checkout speed?"
5. **Sequence to avoid priming.** Put general/unprompted questions before
   specific ones on the same topic (ask overall satisfaction before asking
   about individual features) so early items do not anchor answers to later
   ones. Group by topic, and put sensitive or demographic questions last.
6. **Balance and label scale points fully.** A 5-point Likert scale needs a
   true neutral midpoint and symmetric labels ("strongly disagree" through
   "strongly agree") — an unbalanced scale (e.g., four positive options, one
   negative) biases the distribution before a single response comes in.
7. **Keep the survey short enough to finish.** Budget roughly 1 minute per
   5-7 simple items; surveys over 10-15 minutes see sharply rising abandonment
   — cut items that do not map to a specific research question or decision.
8. **State the target sample size and its rationale.** For attitudinal
   surveys intended to support cross-tabs or segmentation, a rough floor is
   ~100 responses per segment to be analyzed; a survey intended only for a
   single topline number needs less. Use a formal power analysis if the
   survey will drive a statistical test.
9. **Pilot with 3-5 respondents before full send**, checking for
   misinterpreted items, technical issues, and completion time — a piloted
   survey catches ambiguous wording no amount of internal review does.

## Checklist / quality gate
- [ ] Every item is single-barreled (one variable per question).
- [ ] No leading or presupposing language survives a final read-through.
- [ ] Scale direction is consistent across the entire instrument.
- [ ] Item order runs general-to-specific per topic, with sensitive/
      demographic questions last.
- [ ] Scale points are balanced and fully labeled, with a genuine neutral
      midpoint where appropriate.
- [ ] Estimated completion time and target sample size (with rationale) are
      both stated before the survey is sent.
- [ ] The survey was piloted with a small group before the full send, if the
      stakes or audience size justify it.

## References
- Survey-design best practice is broadly documented across UX research
  literature; no single canonical source was confirmed during the research
  pass that produced this skill — validate scale-type and sample-size
  guidance against current practice before relying on it for
  high-stakes instruments.

## Composition
Alternative method to interview/usability-test-based studies scoped by
`write-a-research-plan` — use this skill when the plan's method selection
lands on "survey." Free-text/open-ended responses from the resulting survey
feed into `synthesize-with-affinity-mapping` for thematic analysis; the
closed-ended results and the instrument itself are candidates for
`maintain-research-repository` so a recurring metric (NPS, CSAT) stays
consistent across waves.
