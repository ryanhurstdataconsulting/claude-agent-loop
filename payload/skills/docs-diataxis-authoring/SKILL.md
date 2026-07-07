---
name: docs-diataxis-authoring
description: Use when a new feature, API, or product surface needs documentation and it is unclear whether the result should be a tutorial, a how-to guide, a reference page, or an explanation. Triggers include "write docs for," "document this feature," a documentation ticket with no specified format, a draft that mixes step-by-step instructions with background theory, or a reviewer comment like "this reads like three different documents at once." Classifies the request into a Diátaxis quadrant, drafts an outline for approval, then writes the page in that quadrant's voice and checks it for quadrant-purity before it ships.
---

# docs-diataxis-authoring

## Overview
Turns an ambiguous "write docs for X" request into a document of a known, correct
shape. It owns the classification step (which of the four Diátaxis quadrants this
content belongs in), the outline-before-prose step, and a quadrant-purity check
that catches the most common documentation defect: one page quietly trying to be
two kinds of document at once.

## When to use
- A new feature, endpoint, or product surface ships and needs documentation, with
  no format specified up front.
- A documentation ticket says "write a guide" or "document this" without saying
  whether the reader is learning, doing, looking something up, or trying to
  understand why something works the way it does.
- An existing draft feels bloated or hard to navigate — a common symptom of
  quadrant-mixing (a tutorial that stops to explain architecture, a reference page
  padded with narrative).
- A style or docs-platform migration needs existing content re-sorted into a
  consistent information architecture.
- A reviewer flags a doc as unclear on "who this is for" or "what it wants me to
  do with it."

## Workflow

**1. Classify before drafting — ask which quadrant, not what to write.** Diátaxis
sorts documentation along two axes: whether the reader is **acquiring** skill or
**applying** it, and whether the content is **practical** (action) or
**theoretical** (understanding). That produces four quadrants:

| | Practical (doing) | Theoretical (knowing) |
|---|---|---|
| **Study** (learning) | **Tutorial** — a guided lesson, output secondary to the learning | **Explanation** — background, context, the "why" |
| **Work** (applying) | **How-to guide** — a recipe for a specific goal a competent reader already has | **Reference** — accurate, complete, neutral facts to look up |

Ask (or infer from the request) two things: *Is the reader learning or already
capable?* and *Do they want to act, or to understand?* If the answer is unclear,
ask the requester directly rather than guessing — a misclassified doc is expensive
to untangle later.

**2. Confirm audience, goal, and scope before outlining.**
- Audience: first-time user, integrating developer, or an experienced operator
  debugging a specific problem?
- Goal: what should the reader be able to do, or know, once they finish?
- Scope: one feature/endpoint, or a whole subsystem? A too-broad scope is the
  second most common cause of quadrant-mixing — split it into multiple documents
  instead of one document trying to cover everything.

**3. Propose an outline before writing prose.** For any document beyond a few
paragraphs, draft a heading-level outline and get it approved (by the requester,
or by explicit self-check against the quadrant's purpose) before writing full
prose. This is cheap to redirect and expensive to redo after a full draft.

**4. Write in the quadrant's voice.** Each quadrant has a distinct register —
writing a reference page in tutorial voice (or vice versa) is the defect this
skill exists to prevent:
- **Tutorial** — second person, imperative, one path only ("Now run..."). No
  branching, no "you could also." Concrete, reproducible steps with a stated
  outcome at the end. Skip explaining *why* mid-lesson; link out instead.
- **How-to guide** — assumes competence. States the goal up front, then the
  steps to reach it, covering realistic variations. No teaching, no theory.
- **Reference** — structured, exhaustive, neutral. Describes what *is* — every
  parameter, every field, every return code — not what to do with it. Consistent
  structure across entries so readers can scan, not read linearly.
- **Explanation** — prose, discursive, no steps required. Provides context,
  trade-offs, design rationale, and connects concepts. The only quadrant where
  wandering off the immediate task is appropriate.

**5. Check quadrant-purity before calling it done.** Re-read the draft looking
specifically for content that belongs in a different quadrant:
- A tutorial that stops to explain *why* the architecture is shaped this way →
  move that to an Explanation page and link it.
- A how-to guide padded with conceptual background → trim to the steps, link an
  Explanation page for the "why."
- A reference page with narrative asides or task instructions → strip to facts;
  link a how-to guide for the task.
- An explanation page with imperative steps → convert those into a linked
  how-to guide.

**6. Cross-link, don't duplicate.** The four quadrants are meant to reference
each other, not repeat each other. A tutorial links forward to explanations and
how-to guides for what it deliberately left out; a reference page links out to
a how-to guide showing the parameter in use. Duplication is a maintenance
liability — a fact stated in two places drifts out of sync the first time either
one changes.

**Common gotchas:**
- Defaulting every request to "reference" because it feels safest — reference
  material with no how-to guide leaves readers who want to *do* something
  stranded in an index of facts.
- Writing a tutorial with branches ("if you're on Windows... if you prefer
  approach B...") — tutorials should have exactly one path; branching belongs in
  a how-to guide.
- Skipping the outline step on the assumption the request is "simple" — the
  quadrant-mixing defect shows up just as often in short documents as long ones.

## Checklist / quality gate
- [ ] The document is classified into exactly one Diátaxis quadrant, and that
      classification is stated (in the outline or a doc-front-matter note).
- [ ] Audience, goal, and scope were confirmed before drafting, not assumed.
- [ ] An outline was proposed and approved (or self-checked against the
      quadrant's purpose) before full prose was written.
- [ ] The draft passes the quadrant-purity check — no tutorial theory-asides, no
      how-to narrative padding, no reference-page instructions, no explanation-
      page imperative steps.
- [ ] Cross-links to the other quadrants replace duplicated content, not
      repeat it.
- [ ] Code samples, if any, were actually run or otherwise verified, not just
      transcribed from memory.
- [ ] A grammar and terminology pass ran before publishing.

## References
- [Diátaxis](https://diataxis.fr/) — the canonical framework this skill implements
- [Diátaxis — Tutorials](https://diataxis.fr/tutorials/), [How-to guides](https://diataxis.fr/how-to-guides/), [Reference](https://diataxis.fr/reference/), [Explanation](https://diataxis.fr/explanation/)
- [I'd Rather Be Writing — What is Diátaxis?](https://idratherbewriting.com/blog/what-is-diataxis-documentation-framework)

## Composition
- Feeds `openapi-reference-generator` when the reference quadrant is API
  documentation generated from a machine-readable spec.
- Hands off to `prose-style-lint` before publishing — classification and
  structure are this skill's job; voice and terminology consistency are that
  skill's.
- Shares its pattern with a quickstart-tutorial generator (tutorial quadrant
  specialized for a runnable code sample) and a knowledge-base-article generator
  (how-to quadrant specialized for a single resolved support case).
- Feeds `content-staleness-audit`, which checks already-published Diátaxis
  content for drift rather than authoring it fresh.
