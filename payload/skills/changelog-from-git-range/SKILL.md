---
name: changelog-from-git-range
description: Use when a release ships and needs developer-facing release notes distinct from the internal engineering changelog — turning a git commit range or conventional-commit history into grouped, benefit-oriented notes with breaking changes called out prominently. Triggers include "write release notes for this release," a tagged version bump, a request to summarize "what changed between v1.2 and v1.3," or a changelog file that has fallen behind the actual commit history.
---

# changelog-from-git-range

## Overview
Transforms a git commit range into external, developer-facing release notes —
grouped by feature/fix/breaking-change, rewritten in benefit-oriented language,
with breaking changes surfaced first. The one job it owns: the git-log-to-
release-notes transformation, shared equally by developer relations (who
publish it) and technical writing (who often own final voice on it).

## When to use
- A version is tagged or a release is cut and needs public release notes.
- A request to summarize "what changed" between two commits, tags, or dates.
- An internal engineering changelog exists but the developer-facing notes have
  drifted behind it or were never split out from it.
- A pre-release draft of notes is needed so the team can review before
  publishing.

## Workflow
1. **Resolve the exact range.** Get the precise commit range (`git log
   v1.2.0..v1.3.0` or an equivalent date/tag bound) before doing anything else
   — an ambiguous range produces an incomplete or duplicated changelog.
2. **Prefer structured commit history when it exists.** If the repository
   follows [Conventional Commits](https://www.conventionalcommits.org/en/about/)
   (`feat:`, `fix:`, `BREAKING CHANGE:` footers, etc.), parse those prefixes
   directly rather than re-inferring intent from free-text messages.
3. **Fall back to reading the actual diff when messages are unstructured.** A
   commit message like "fix stuff" is not sufficient input — read the
   associated diff or linked issue/PR to determine what actually changed and
   who it affects.
4. **Group into standard sections**, in this order: Breaking Changes, New
   Features, Improvements, Bug Fixes, Deprecations. Omit empty sections rather
   than showing "None."
5. **Rewrite every entry in external, benefit-oriented voice.** "Refactored
   the auth middleware" (internal, implementation-focused) becomes "Requests
   with an expired token now return a clear `401` instead of a generic `500`"
   (external, effect-focused). The reader is a developer consuming the
   product, not a teammate reviewing the PR.
6. **Surface breaking changes prominently and with a migration path.** Every
   breaking-change entry needs what changed, why, and the concrete action a
   consumer must take (e.g., "rename `userId` to `id` in your request
   payload") — never just "this is now different."
7. **Attribute and link where useful**, not required — PR/issue links,
   contributor credit — matching the target changelog's existing convention
   (check `CHANGELOG.md` or the release-notes host for the established
   format before inventing a new one).
8. **Exclude internal-only noise** — CI config tweaks, internal refactors with
   no external behavior change, dependency bumps with no user-visible effect
   — unless the target audience is explicitly technical/SDK-integrator and
   needs that detail.
9. **Draft for review before publishing.** These notes usually need a second
   set of eyes (technical writing or the release owner) before going out; hand
   off a draft rather than auto-publishing.

## Checklist / quality gate
- [ ] The commit range is exact and stated in the output (tags, SHAs, or
      dates).
- [ ] Every entry is grouped correctly (breaking / feature / improvement /
      fix / deprecation), with empty sections omitted.
- [ ] Every entry reads in external, benefit-oriented language — no raw
      internal commit-message text copied through verbatim.
- [ ] Every breaking change includes a concrete migration action, not just a
      description of what changed.
- [ ] Internal-only commits (CI, pure refactors, unrelated dependency bumps)
      are excluded unless the audience explicitly needs them.
- [ ] The draft has passed a grammar/style check before being sent for
      publish review.

## References
- [Conventional Commits](https://www.conventionalcommits.org/en/about/) —
  the structured commit-message convention this skill parses when present.
- [git-cliff](https://git-cliff.org/) — a changelog generator implementing
  this same commit-range-to-notes pattern.
- [conventional-changelog](https://github.com/conventional-changelog/conventional-changelog) —
  the tooling ecosystem for Conventional-Commits-driven changelog generation.

## Composition
Shared ownership between developer relations (publishes it externally) and
technical writing (`docs-diataxis-authoring`, `prose-style-lint` for the final
voice pass). Pairs with `sample-app-health-check` when a release includes
breaking SDK changes — check whether published samples need updating in the
same cycle. Feeds a `community-feedback-digest` cycle: a release with breaking
changes is a strong prior for the next digest's theme volume.
