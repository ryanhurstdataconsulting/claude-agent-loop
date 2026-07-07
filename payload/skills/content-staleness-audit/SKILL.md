---
name: content-staleness-audit
description: Use for a periodic documentation-health sweep — finding dead links, version-drifted instructions, screenshots or code samples that no longer match the current release, and pages nobody has touched in many release cycles. Triggers include "audit the docs," "docs-health check," "which pages are out of date," a documentation-deflection-rate complaint, a version bump that leaves old docs referencing the previous release, or a scheduled/recurring docs-audit job. Crawls the doc set, cross-checks version references against the current release, flags pages stale by age or by content drift, and prioritizes the findings by traffic or deflection data when that's available.
---

# content-staleness-audit

## Overview
Runs a systematic health check over an existing documentation set to find
content that has quietly gone wrong since it was written: dead links, version
numbers that no longer match the shipped release, code samples that no longer
run, and pages nobody has revisited in a long time. It owns detection and
prioritization — it flags and ranks staleness, it does not rewrite content
(that's `docs-diataxis-authoring`'s job once a page is confirmed stale).

## When to use
- A scheduled or recurring documentation-health audit is due.
- A major or minor version ships and docs referencing the previous version
  need to be found before they mislead a reader.
- Support-ticket volume or a documentation-deflection-rate metric suggests a
  page (or a whole section) isn't doing its job anymore.
- A documentation platform migration needs a pre-migration inventory of what's
  actually still accurate versus what's safe to archive.
- A reader or reviewer reports a broken link, a screenshot that doesn't match
  the current UI, or a code sample that no longer runs.

## Workflow

**1. Establish the ground truth to audit against.** Staleness is relative to
something — pin down what before crawling:
- The current shipped version/release tag (from a changelog, release tags, or
  package manifest).
- The current UI/API surface (from the live product, current OpenAPI spec, or
  current screenshots baseline).
- A "last reviewed" or "last touched" timestamp convention, if the doc set
  has one (front matter, git blame on the file, or a docs-platform field).

**2. Crawl the doc set and classify each page's staleness signal.**
For every page, check:
- **Dead links** — internal links to pages that moved or were deleted, and
  external links returning 404/redirect-loop/timeout. Internal breaks are
  higher priority; they're fully within the team's control to fix.
- **Version drift** — a version number, deprecated flag, or "as of vX" claim
  in the text that no longer matches the current release. Cross-check
  explicit version mentions against the changelog/release history.
- **Code-sample drift** — a code sample that references a removed/renamed
  API, an outdated import path, or (if executable) fails to run against the
  current SDK/API version.
- **Screenshot/UI drift** — a referenced screenshot or described UI flow that
  no longer matches the current product surface, where that can be checked
  (image diff against a current capture, or a described click-path that no
  longer exists).
- **Age without a content check** — a page untouched since N releases ago is
  not automatically wrong, but it's a red flag worth surfacing; treat "old"
  as a prioritization signal, not proof of staleness on its own.

**3. Prioritize findings, don't just list them.** A flat list of every stale
page is not actionable. Rank by whatever signals are available, in order of
preference:
- **Traffic/deflection data**, if accessible — a high-traffic page with a
  high deflection-failure rate (readers hit it, then still file a ticket) is
  the highest-value fix.
- **Blast radius** — a getting-started or landing page with drift affects far
  more readers than a deep reference corner.
- **Severity of the drift** — a broken code sample or a dead link on the
  critical path (sign-up, first API call) outranks a cosmetic screenshot
  mismatch.
- **Age**, as the tiebreaker when no usage data exists.

**4. Distinguish "flag for rewrite" from "flag for deletion."** Not every
stale page should be updated — some describe a deprecated feature and should
be archived or redirected, not refreshed. Recommend which action applies per
finding rather than defaulting every finding to "needs an update."

**5. Produce a findings report the requester can act on**, not a data dump:
per finding, the page, the specific issue, the evidence (the dead URL, the
version mismatch, the failing code block), the recommended action, and a
priority tier. Group by priority tier so the highest-value fixes surface
first.

**6. Hand off remediation, don't perform it inline.** This skill's job ends
at a prioritized, evidenced findings report. Content rewrites go to
`docs-diataxis-authoring`; a full reference regeneration goes to
`openapi-reference-generator`; both should treat this audit's findings as
their input, not redo the detection work.

**Common gotchas:**
- Treating "old" as synonymous with "wrong" — a stable reference page that
  hasn't changed in a long time because nothing about it changed is not a
  finding; only flag age alongside an actual content check.
- Missing internal 404s because only external links were checked — internal
  breaks are usually cheaper to fix and more embarrassing to leave, so check
  both.
- Reporting every finding at equal priority — an unprioritized list of a
  hundred stale pages gets ignored; rank it.
- Auto-deleting or auto-archiving flagged pages without a human confirming
  the feature is actually deprecated, not just quiet.

## Checklist / quality gate
- [ ] The ground truth (current version, current UI/API surface) used for
      comparison is stated explicitly.
- [ ] Every page checked was evaluated for at least dead links and version
      drift; code-sample and screenshot checks ran wherever feasible.
- [ ] Findings are prioritized (traffic/deflection data if available, blast
      radius and severity otherwise), not presented as a flat list.
- [ ] Each finding includes concrete evidence — the broken URL, the version
      mismatch, the failing sample — not just a page name.
- [ ] Each finding recommends an action (update, archive, redirect), not a
      generic "needs review."
- [ ] Findings are handed off as input to a remediation skill, not
      rewritten inline as part of the audit.
- [ ] Age-only signals are clearly distinguished from confirmed-content
      defects in the report.

## References
- [Diátaxis](https://diataxis.fr/) — the structure staleness is being checked
  against; a page that's drifted often means it's drifted out of its
  quadrant's purpose, too
- [Write the Docs — Documentation Metrics](https://www.writethedocs.org/guide/tools/analytics/)
- [Google Developer Documentation Style Guide — Maintaining documentation](https://developers.google.com/style/product-names)

## Composition
- Consumes the current spec as ground truth when paired with
  `openapi-reference-generator`'s "has the reference drifted from the live
  spec" check — this skill covers the rest of the doc set (tutorials,
  how-to guides, explanations) that the reference generator doesn't touch.
- Hands stale-and-confirmed-wrong pages to `docs-diataxis-authoring` for
  rewriting, and hands the freshly rewritten page back through
  `prose-style-lint` before republishing.
- Findings on ticket-driven deflection failures pair well with a
  knowledge-base-article-from-resolved-ticket workflow — a page that keeps
  failing to deflect tickets is a candidate for replacement by a more
  specific how-to or KB article.
