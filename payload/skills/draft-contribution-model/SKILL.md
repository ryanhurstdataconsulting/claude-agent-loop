---
name: draft-contribution-model
description: Use when a design system needs a documented process for how teams propose, review, and ship new or changed components. Triggers include "contribution model," "design-system governance," "how do we add a component to the system," "who approves new components," or a design system experiencing ad hoc component sprawl because there is no defined intake pipeline.
---

# draft-contribution-model

## Overview
Defines the end-to-end pipeline for how a new or modified component enters
a shared design system — request, review, design, build, document,
release — with named review criteria and owners per stage, packaged as a
contribution-guide document consuming teams can follow without asking the
system team for help each time.

## When to use
- A design system exists but has no documented process for proposing new
  components, so teams either duplicate work or bypass the system entirely
  with one-off components.
- Component sprawl is showing up — multiple near-identical components
  built by different teams because no one knew a request process existed.
- A design-system team is scaling past one or two people and needs to
  formalize what was previously tribal knowledge.
- An existing contribution process is unclear about ownership — proposals
  stall because no one knows who has final say.

## Workflow

### 1. Map the pipeline stages
The standard shape is six stages; adapt names to the organization but keep
the sequence — each stage gates the next:

1. **Request** — a team identifies a need not met by the existing system.
   Capture: the use case, why an existing component doesn't fit, and
   expected reuse (is this a one-off or a genuine pattern?).
2. **Review** (triage) — the system team or a governance group decides:
   reject (use an existing component or one-off it locally), extend an
   existing component, or accept as a new addition.
3. **Design** — the component is designed to system conventions (token
   usage, states, responsive behavior, accessibility) and reviewed against
   the existing visual language.
4. **Build** — implemented in code against the system's component API
   conventions, with tests and Storybook (or equivalent) stories.
5. **Document** — usage guidelines, do/don't examples, code snippets,
   accessibility notes, and prop/API reference are written before release,
   not after.
6. **Release** — versioned and shipped per the system's versioning cadence
   (see `generate-component-changelog`), with migration notes if it
   replaces or deprecates something.

### 2. Assign owners and criteria per stage
For each stage, define explicitly:
- **Who decides** (a named role, not "the team" — e.g., "design-system
  lead" for triage, "two design-system engineers" for build review).
- **What "done" looks like** — a checklist per stage (e.g., Design stage
  exit criteria: uses only existing tokens or a newly-approved token,
  covers all interactive states, passes a baseline accessibility check).
- **Turnaround expectation** — a stalled proposal with no SLA is
  indistinguishable from a rejected one; set an expected response window
  per stage even if it's approximate.

### 3. Set the acceptance bar
Decide and document the actual threshold for "this becomes a system
component" versus "this stays a one-off in the consuming team's codebase."
Common bar: evidence of reuse across two or more teams/products, or a
strong forward-looking case for reuse. Write this down explicitly —
otherwise every triage decision re-litigates the bar from scratch.

### 4. Define the escalation and appeal path
What happens when a requesting team disagrees with a rejection or a
scope-down? Name the escalation route (e.g., to a design-system steering
group) so contribution doesn't quietly become "whoever complains loudest
gets their component built."

### 5. Package as a contribution guide
Produce a single document a requesting team can follow unassisted:
pipeline diagram, stage-by-stage criteria and owners, the acceptance bar,
submission template (what info a Request needs), and the escalation path.

## Checklist / quality gate
- All six pipeline stages are present with a named owner for each — no
  stage says "the team" without specifying which role.
- Exit criteria are defined per stage, not just for the pipeline as a
  whole.
- The acceptance bar (what makes something system-worthy versus a local
  one-off) is written down explicitly.
- A turnaround expectation exists per stage, even if approximate.
- An escalation/appeal path exists for rejected or stalled proposals.
- The output is a single, self-service document — a requesting team
  should not need to ask the system team "what do I do first."

## References
- Design-system governance guide: https://sealab.design/blog/design-system-governance/
- "Who should be on your design system team" (role/ownership framing):
  https://www.knapsack.cloud/blog/who-should-be-on-your-design-system-team

## Composition
Feeds `generate-component-changelog` at the Release stage. Pairs with
`audit-storybook-documentation` for the Document stage's exit criteria and
with `accessibility-audit` for the Design/Build stage's accessibility
checks. The governance decisions embedded in this process (who has final
say, what the acceptance bar is) remain a human call — this skill
structures and documents the decision, it doesn't make it.
