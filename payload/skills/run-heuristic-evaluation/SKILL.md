---
name: run-heuristic-evaluation
description: Use when an existing interface, flow, or feature needs a fast usability audit before, or instead of, a full research study — walking the interface against Nielsen's 10 usability heuristics, logging each violation with a severity rating and a heuristic tag, and producing a prioritized findings list. Triggers include "usability audit," "heuristic evaluation," "review this UI for usability issues," a live app or Figma flow that needs a fast expert pass, or a request to check an interface before committing to a full usability-testing study.
---

# run-heuristic-evaluation

## Overview
Performs a structured expert-inspection audit of an interface against Nielsen's 10
usability heuristics, producing a severity-rated, prioritized findings list without
requiring live participants. The one job this skill owns: catching usability
defects fast, using an established checklist, when a full research study is not
warranted or not yet possible.

## When to use
- An interface, flow, or feature needs a usability check before shipping and there
  is no time or budget for a moderated study.
- A live app or interactive prototype is available to walk through directly
  (well suited to browser-automation-driven inspection).
- A design critique needs a rigorous usability axis rather than a subjective
  gut-check (pairs with `structure-design-critique`).
- The request mentions "heuristic evaluation," "usability audit," "Nielsen
  heuristics," or "expert review."
- A team wants a quick triage pass to decide whether a full usability-testing study
  is even necessary.

## Workflow

**1. Define the scope and the user task(s) being evaluated.** A heuristic
evaluation without a task in mind degenerates into unfocused nitpicking. Pick one
to three representative tasks (e.g., "complete checkout," "find and edit a saved
draft") and walk each end to end.

**2. Walk the interface against each of the 10 heuristics, one pass per
heuristic** (not one pass evaluating everything at once — separate passes catch
more, because each pass narrows attention to a single failure mode):
   1. **Visibility of system status** — does the interface keep the user informed,
      with reasonable feedback, within reasonable time?
   2. **Match between system and the real world** — does it speak the user's
      language, follow real-world conventions, in a natural and logical order?
   3. **User control and freedom** — is there a clearly marked "emergency exit"
      (undo/redo, cancel) for mistaken actions?
   4. **Consistency and standards** — do words, situations, and actions mean the
      same thing throughout, and does the interface follow platform conventions?
   5. **Error prevention** — does the design prevent problems before they occur,
      via careful design or confirmation for destructive actions?
   6. **Recognition rather than recall** — are objects, actions, and options
      visible, minimizing the user's memory load?
   7. **Flexibility and efficiency of use** — are there accelerators for expert
      users that do not clutter the experience for novices?
   8. **Aesthetic and minimalist design** — do interfaces avoid irrelevant or
      rarely needed information competing with relevant units of information?
   9. **Help users recognize, diagnose, and recover from errors** — are error
      messages in plain language, precisely indicating the problem and
      constructively suggesting a solution?
   10. **Help and documentation** — if help is needed, is it easy to search,
       focused on the user's task, and not overly large?

**3. Log every violation as a finding**, each with:
   - The heuristic it violates (by number/name).
   - Where it occurs (screen, component, step in the task).
   - A severity rating (a 0–4 scale is standard: 0 = not a usability problem,
     1 = cosmetic, 2 = minor, 3 = major, 4 = usability catastrophe).
   - A one-line fix suggestion where one is obvious; leave it open when it is not.

**4. Aggregate and prioritize.** Sort findings by severity, then by how many
distinct tasks/screens the same root cause touches — a single root cause hitting
five screens outranks five unrelated cosmetic nits. Note when several minor
findings share a root cause; fixing the root cause once likely resolves all of
them.

**5. Distinguish evaluator confidence from certainty.** A heuristic evaluation is
an expert-inspection method, not empirical proof of user behavior — flag findings
that are strong candidates for confirmation via real usability testing (severity 3
or 4, or where the evaluator is inferring intent rather than observing a clear
violation).

## Checklist / quality gate
- Every finding names the specific heuristic it violates, not a vague "this is
  confusing."
- Every finding has a severity rating on a defined scale, and the list is sorted by
  it.
- Findings sharing a root cause are grouped, with the shared cause called out.
- At least one representative task was walked end to end, not just individual
  screens in isolation.
- High-severity findings are flagged as candidates for validation via real
  usability testing rather than presented as settled fact.

## References
- Nielsen's 10 usability heuristics — https://heurilens.com/resources
- Eleken, heuristics-based UX design audit checklist — https://www.eleken.co/blog-posts/a-checklist-for-ux-design-audit-based-on-jakob-nielsens-10-usability-heuristics

## Composition
Feeds the usability axis of `structure-design-critique`. Findings rated as needing
confirmation route into `write-a-research-plan` to scope a usability-testing study.
Pairs with an accessibility-audit skill (keyboard/screen-reader/contrast) as a
parallel, complementary inspection pass over the same interface.
