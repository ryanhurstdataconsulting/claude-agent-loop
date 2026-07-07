---
name: quickstart-tutorial-generator
description: Use when a new API endpoint, SDK method, or product feature ships and needs a learning-oriented "getting started" tutorial with a runnable code sample. Triggers include requests to "write a quickstart," "add a getting-started guide," "show a first API call," a new SDK version needing an onboarding example, or an existing tutorial that fails when actually run. Produces a Diátaxis-style tutorial the agent has executed end to end, not just drafted.
---

# quickstart-tutorial-generator

## Overview
Turns a new or changed API/SDK surface into a runnable, learner-oriented
quickstart tutorial. The one job it owns: produce a tutorial whose code sample
has actually been executed and verified to work, not merely written to look
plausible.

## When to use
- A new API endpoint, SDK method, CLI command, or feature ships without an
  onboarding path for a first-time user.
- A request to write a "getting started," "quickstart," or "first steps"
  guide.
- An existing quickstart is stale against the current API/SDK version (signature
  drift, renamed parameters, deprecated auth flow).
- A tutorial in the docs set has never been confirmed to actually run — before
  publishing or re-publishing it.

## Workflow
1. **Pull the ground truth for the surface being taught.** Read the OpenAPI spec,
   SDK type signatures, or CLI `--help` output directly — never write example
   calls from memory or from a stale doc page. If no machine-readable spec
   exists, read the actual source (route handler, exported function signature).
2. **Scope to one learner goal, not a feature tour.** A tutorial is
   learning-oriented per Diátaxis: pick the smallest end-to-end path a
   newcomer completes (for example, "make one authenticated call and see a
   response"), not an exhaustive parameter walkthrough — that belongs in
   reference docs, not here.
3. **Scaffold the runnable sample first, prose second.** Write the actual code
   (curl, SDK snippet, CLI invocation) before the surrounding narrative, so the
   narrative describes what the code really does rather than what it was
   supposed to do.
4. **Execute the sample in a real or sandboxed environment.** Run it against a
   test/sandbox credential or local emulator — never against production data
   or a real customer account. If no safe environment exists, say so explicitly
   in the handoff rather than shipping an unverified sample.
5. **Capture the actual output**, not a fabricated one. Paste the real response
   (redacting secrets/PII) so the reader can pattern-match their own result
   against it.
6. **Write the narrative in second person, present tense, minimal branching.**
   Diátaxis tutorials avoid "if you want X, do Y instead" — that is a how-to
   guide's job. One straight path, no forks.
7. **Add a "what you built" recap and a next-step pointer** (to a how-to guide
   or reference page) at the end — a tutorial should end with the learner
   knowing where to go deeper.
8. **Quadrant-check before finishing.** Strip any content that has drifted into
   reference material (full parameter tables) or how-to material (troubleshooting
   branches) — route it to the appropriate doc type instead of leaving it here.

## Checklist / quality gate
- [ ] The code sample was actually executed, and its real output is quoted (not
      invented).
- [ ] The sample was run against a sandbox/test credential, never production or
      a real customer's account or data.
- [ ] No secrets, tokens, or PII appear in the sample or its captured output.
- [ ] The tutorial follows one linear path with no "or, alternatively" branches.
- [ ] Every parameter, header, or flag named in the sample matches the current
      spec or source — no renamed or deprecated fields.
- [ ] A "what you just built" summary and a next-step link close the tutorial.
- [ ] Prose has passed a grammar/style check before publishing.

## References
- [Diátaxis](https://diataxis.fr/) — the tutorial/how-to/reference/explanation
  framework this skill's tutorial mode implements.
- [Slack Engineering — Defining a career path for Developer Relations](https://slack.engineering/defining-a-career-path-for-developer-relations/) —
  sample-code and tutorial creation as a core developer-relations
  responsibility.

## Composition
Hands off to `docs-diataxis-authoring` when the same content needs a how-to or
reference companion page. Pairs with `sample-app-health-check` for the
standing maintenance loop once the tutorial ships (its sample becomes one more
snippet that needs periodic re-verification). Pairs with `prose-style-lint`
for the narrative pass, and with an API-contract skill (an OpenAPI-reference
generator or equivalent) as the source of truth for the sample's request
shape.
