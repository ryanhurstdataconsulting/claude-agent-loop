---
name: sample-app-health-check
description: Use for a periodic audit of public sample apps, code snippets, or quickstart repos against the current API/SDK version — running each sample, flagging breakage or deprecated calls, and opening issues or fix PRs. Triggers include a scheduled "sample repo health check," an SDK major-version bump that may break published examples, a developer report that a quickstart no longer runs, or a request to sweep a docs/examples directory for drift.
---

# sample-app-health-check

## Overview
Runs every public sample app, code snippet, or quickstart example against the
current API/SDK version and triages what breaks. The one job it owns: turn
"is our sample code still true" from a manual spot-check into a repeatable,
evidence-based sweep that ends in filed issues or fix PRs — not just a list of
suspicions.

## When to use
- A recurring (weekly/monthly/per-release) audit of a samples repo, docs
  `examples/` directory, or embedded code snippets is due.
- An SDK or API ships a breaking or deprecating change and published samples
  need re-verification.
- A developer reports that a quickstart or sample repo no longer runs.
- Before a major release, as a gate on whether existing samples still pass.

## Workflow
1. **Inventory every sample.** Enumerate standalone sample repos, an
   `examples/` directory, and any code blocks embedded in docs that are meant
   to be runnable (not illustrative pseudocode — distinguish the two).
2. **Pin the current API/SDK version being tested against.** Record it in the
   audit output; a health check without a version pin cannot be reproduced or
   trusted later.
3. **Run each sample in isolation.** Use a sandboxed environment or test
   credentials — never real customer data or production-only endpoints. For
   samples requiring network calls to a third-party service, use recorded
   fixtures or a mock where live calls are not safe to make repeatedly.
4. **Classify each failure**, not just pass/fail:
   - **Hard break** — the sample errors out or crashes.
   - **Silent drift** — it runs but produces output inconsistent with what the
     sample claims to demonstrate (a renamed field is now `undefined` but no
     exception fires).
   - **Deprecated-but-working** — it runs today but calls a method flagged for
     removal; flag with the deprecation timeline if known.
   - **Stale idiom** — it runs and produces correct output but no longer
     reflects current best practice (e.g., an outdated auth pattern).
5. **Triage severity before filing.** A hard break in the first-run quickstart
   is high severity (blocks every new developer); a stale idiom in a rarely
   viewed advanced sample is low.
6. **File or fix, don't just report.** For mechanical fixes (renamed parameter,
   updated import path), open a PR with the fix and the failing-then-passing
   run output as evidence. For fixes requiring a judgment call (which of two
   new APIs replaces a removed one), open an issue with the diagnostic detail
   and a recommended fix, flagged for human review.
7. **Roll up a summary** — total samples checked, pass count, and one line per
   failure with its classification and filed issue/PR link — so the next
   health check can diff against this one.

## Checklist / quality gate
- [ ] Every sample was actually executed (or run against a documented mock/
      fixture) — no sample marked "pass" on inspection alone.
- [ ] The API/SDK version tested against is recorded in the output.
- [ ] Failures are classified (hard break / silent drift / deprecated /
      stale idiom), not lumped into a single "broken" bucket.
- [ ] No live calls were made against production data or a real customer
      account.
- [ ] Each filed issue or PR includes the actual failing output as evidence,
      not a paraphrase.
- [ ] Mechanical fixes are proposed as PRs with before/after run output;
      judgment-call fixes are issues, not silent PRs.

## References
- [Slack Engineering — Defining a career path for Developer Relations](https://slack.engineering/defining-a-career-path-for-developer-relations/) —
  sample-code maintenance as a standing developer-relations duty.

## Composition
Feeds from `quickstart-tutorial-generator` (the samples it creates are what
this skill later re-verifies) and from a CI-pipeline-authoring skill if the
health check should run as a scheduled job rather than an ad hoc sweep.
Escalates unresolved breaks that need engineering judgment through a bug-
report/escalation-writing skill.
