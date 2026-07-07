---
name: prose-style-lint
description: Use before publishing any client-facing or user-facing prose a program or agent generated — documentation, release notes, report narratives, UI copy, error messages, support responses — to check it against a style guide and catch grammar and usage defects. Triggers include "review this draft before we ship it," a style-guide or Vale configuration in the repository, a reviewer comment flagging inconsistent terminology or passive voice, or any point right before machine-generated prose reaches an end user. Runs an automated terminology/voice/passive-voice pass plus a grammar pass, and reports violations with suggested fixes rather than silently rewriting.
---

# prose-style-lint

## Overview
Catches style-guide and grammar defects in prose before it reaches a reader —
the last gate between a draft and a published, client-facing document. It
treats machine-generated prose (report narratives, UI copy, auto-drafted
release notes) as carrying the *same* bar as human-written prose: a slip here
is a real defect, not a nit, because it reaches an end user with the
organization's name on it.

## When to use
- Any document is about to be published, sent to a client, or merged into
  user-facing documentation: guides, release notes, API descriptions, support
  replies, UI copy, error messages.
- A program or agent generated the prose itself (a report narrative, a
  templated summary, an auto-drafted changelog entry) — this is the highest-risk
  case, since nothing human proofread it by default.
- A style guide, terminology list, or Vale configuration exists in the
  repository and drafts haven't been checked against it yet.
- A reviewer flags inconsistent terminology (the product called two different
  names in the same document), unwanted passive voice, or a banned/deprecated
  term still in use.
- Content is being localized or repurposed across channels (docs → release
  notes → support macro) and voice consistency needs re-checking at each hop.

## Workflow

**1. Locate or establish the style guide before linting against it.** A
style-guide-free lint pass only catches grammar, not house-style violations.
Look for, in order: a project style guide (`STYLE_GUIDE.md`, a Vale
`styles/` directory, a `.vale.ini`), an existing published-content sample to
infer conventions from, or absent either, default to a well-known public
guide (Google Developer Documentation Style Guide, Microsoft Writing Style
Guide) and say explicitly which one was used.

**2. Run the terminology and voice pass.** Check for:
- **Term consistency** — the same concept referred to by two different names
  across the document or between documents (a feature called both "Workspace"
  and "Project" in the same guide). Build or reuse a terminology list; flag
  every deviation with the canonical term.
- **Banned/deprecated terms** — words the style guide explicitly disallows
  (often legacy product names, non-inclusive language, or jargon flagged for
  replacement). Flag every occurrence with the approved substitute.
- **Passive voice** — flag it where the style guide prefers active voice
  (most technical-writing guides do, for instructions and error messages
  especially). Not every passive construction is wrong — "the request was
  rejected by the server" is sometimes clearer than the active form — but flag
  it for a human call rather than silently rewriting.
- **Sentence length and readability** — flag sentences that run long enough to
  obscure the instruction inside them, especially in how-to or error-message
  contexts where the reader is mid-task.

**3. Run the grammar pass — non-negotiable, independent of house style.**
Regardless of which style guide applies, check for:
- **a/an** matching the *spoken* sound of the word that follows, including
  before numbers and acronyms — "an 8-node cluster," "a 99.9% SLO," "an ADR,"
  "an API," "a UART," "an ML model," "a one-time code" (starts with a "w"
  sound). This is the single most common miss in machine-generated prose
  because naive rules key off the *letter*, not the *sound*: an eight-core
  processor takes "an," not "a," since "eight" starts with a vowel sound.
- **Subject–verb agreement**, especially across long noun phrases where the
  verb can drift from its real subject ("the list of endpoints *are*..." should
  be "*is*").
- **its / it's**, **their / there / they're**, and other commonly confused
  homophones.
- **Tense consistency** within a section — don't drift between past and
  present tense describing the same sequence of steps or events.
- **No double spaces**, no trailing whitespace, no smart-quote/straight-quote
  mixing within the same document.
- **Punctuation inside vs. outside quotation marks** — pick the style guide's
  convention (US vs. UK) and apply it consistently.

**4. Report violations with suggested fixes — do not silently rewrite.**
For each violation, report the location, the rule violated, and a proposed
fix. Silent auto-rewriting removes the author's ability to catch a
misdiagnosis (a flagged passive-voice sentence that was intentional, a
"violation" that's actually a proper noun). The requester or author applies
or rejects each fix.

**5. Re-run after fixes are applied.** Style and grammar passes are cheap to
re-run; confirm a clean pass after fixes land rather than assuming the fix
list was applied correctly.

**Common gotchas:**
- Flagging every passive-voice instance as wrong — some are the clearer
  construction; flag for review, don't force a rewrite.
- Missing number-adjacent article errors because the checker only looks at
  the first letter of the next word rather than its pronunciation, so it
  waves through a mismatched article in front of a digit like "8" or "11."
- Running the grammar pass but skipping the terminology pass (or vice versa)
  — both are needed; a document can be grammatically perfect and still call
  the same feature three different names.
- Linting a draft once, early, and never re-checking after substantive edits
  — a mid-document rewrite can reintroduce exactly the class of error the
  first pass caught.

## Checklist / quality gate
- [ ] The applicable style guide is identified and named explicitly (project
      guide, or the public guide used as a fallback).
- [ ] Terminology is consistent for every recurring concept; deviations are
      flagged with the canonical term.
- [ ] No banned/deprecated terms remain unflagged.
- [ ] Passive-voice instances are flagged where the style guide prefers
      active voice, with a human left to confirm each rewrite.
- [ ] Article choice (a vs. an) is correct by spoken sound, including before
      numbers and acronyms.
- [ ] Subject–verb agreement, its/it's, their/there/they're, and tense
      consistency all check clean.
- [ ] No double spaces or stray whitespace remain.
- [ ] Every reported violation includes a location and a suggested fix, not
      just a flag.
- [ ] A second pass confirms the document is clean after fixes are applied.

## References
- [Vale](https://vale.sh/) — open-source, style-guide-as-code prose linter;
  the current default tool for this workflow
- [Google Developer Documentation Style Guide](https://developers.google.com/style)
- [Microsoft Writing Style Guide](https://learn.microsoft.com/en-us/style-guide/welcome/)
- [The Chicago Manual of Style](https://www.chicagomanualofstyle.org/) — general
  grammar and usage reference

## Composition
- Runs as the final gate on output from `docs-diataxis-authoring`,
  `openapi-reference-generator`, `changelog-from-git-range`,
  `status-report`, and any other skill that produces reader-facing prose
  — invoke it last, after structure and content are settled, since a style
  pass on a draft that's about to be restructured wastes the pass.
- Pairs with `content-staleness-audit` when a periodic docs-health sweep
  should check both currency (staleness) and voice (style) in the same pass.
- Distinct from a security or PII scrubber — this skill checks how prose
  reads, not what it discloses; run both where a document needs each.
