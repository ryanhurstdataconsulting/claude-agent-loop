---
name: run-misra-static-analysis-triage
description: Use when a MISRA-C, MISRA C++, or comparable static-analysis gate fails in CI, when a pre-release compliance audit requires a clean or fully justified static-analysis report, or when a large legacy codebase is being brought under a rule set for the first time with a violation count in the thousands. Triggers include violation reports, deviation records, mandatory/required/advisory rule categories, and pushback on an undocumented suppression comment.
---

# run-misra-static-analysis-triage

## Overview
Triages a MISRA-C/C++ (or comparable) static-analysis violation report into
fix-now, deviate-with-justification, or suppress-as-false-positive, and
produces the deviation record a compliance or safety audit expects to find.
The one job it owns: turn a wall of violations into a defensible, documented
disposition for every single one.

## When to use
- A static-analysis or MISRA-C/C++ gate fails in CI and the run needs triage
  before merge.
- A pre-release or compliance audit requires a clean, or fully justified,
  static-analysis report.
- A large legacy codebase is being brought under a MISRA rule set for the
  first time and the initial violation count is in the thousands.
- A reviewer pushes back on a suppression comment with no justification
  attached.

## Workflow
1. **Sort violations by MISRA category, not tool default order.**

   | Category | Deviation policy |
   |---|---|
   | Mandatory | No deviation, ever — fix before anything else |
   | Required | Deviation permitted only with a documented, reviewed justification |
   | Advisory | Deviation permitted with lighter justification |

   Fix all Mandatory violations first; they are not a judgment call.
2. **For each Required/Advisory violation, decide in this fixed order:**
   1. Can the code be rewritten to comply without changing behavior? If yes,
      fix it — this is almost always the right default for cheap fixes (for
      example, adding braces to a single-line `if`).
   2. If it is a genuine false positive (the tool cannot see a proof the code
      relies on), write a scoped suppression tied to the exact rule ID and
      line/function, with a one-line reason — never a blanket file-level
      suppression.
   3. Otherwise, write a deviation record: rule ID, location, rationale, and
      the compensating control (a test, a code-review sign-off, a runtime
      check) that offsets the risk the rule exists to prevent.
3. **Never suppress a Mandatory rule.** If a tool flags a Mandatory-category
   rule and the team believes it is a false positive, that is an escalation
   to a human safety reviewer, not a suppression comment.
4. **Keep the deviation log version-controlled and first-class** — rule ID,
   count, location, rationale, reviewer, date. Auditors and future engineers
   both need to find "why is this rule disabled here" without spelunking
   through commit history.
5. **For a first-time adoption on an existing codebase**, triage in this
   order rather than alphabetically or by file: Mandatory rules first, then
   the rules with the highest fix-to-risk-reduction ratio (usually
   type-safety and control-flow rules), then bulk-fixable style rules last
   (often automatable via the tool's own auto-fix, reviewed before it lands).

**Gotcha:** a suppression with no rationale is functionally the same as not
running the analyzer at all, and is often flagged as a finding on its own in
a later audit.

**Gotcha:** some violations only appear under a specific compiler or
optimization flag combination. Re-run the analysis with the same flags used
for the release build, not just the default developer build.

## Checklist / quality gate
- Zero unresolved Mandatory-category violations.
- Every Required/Advisory deviation has a rule ID, location, rationale, and
  compensating control on record.
- No blanket/file-level suppressions where a scoped, line-level suppression
  would do.
- The deviation log is checked into version control and is the system of
  record for "why is this disabled."
- The analysis ran with the same compiler flags as the release build.

## References
- A Complete Guide to Embedded Security Testing — Parasoft — https://www.parasoft.com/blog/embedded-security-testing/
- Firmware Testing Guide for Embedded Systems — BugProve — https://bugprove.com/knowledge-hub/firmware-vulnerabilities-you-dont-want-in-your-product/

## Composition
Gates code produced by `write-peripheral-driver-with-hil-test` and
`design-rtos-task-and-ipc` before merge. Wires into the same pipeline as
hardware tests via `set-up-embedded-ci-with-hil-runner`. A Mandatory-rule
violation is frequently also a security finding — cross-check against
`vulnerability-triage-and-disclosure`.
