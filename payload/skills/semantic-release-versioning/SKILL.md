---
name: semantic-release-versioning
description: Use when a repo needs automated version bumps, changelog generation, and tag/publish on merge — "set up semantic release," "automate our versioning," a request to stop hand-editing a CHANGELOG or manually bumping package.json/Cargo.toml/pyproject.toml, or a pipeline that needs a deterministic next-version decision from commit history. Triggers include Conventional Commits already in use without automation behind them, a release process that is "whoever remembers to tag it," and questions about pre-1.0 versioning policy or monorepo per-package release scoping.
---

# semantic-release-versioning

## Overview
Wires Conventional-Commits-driven version bumping, changelog generation, and
tag-and-publish automation into a repo's release path. The one job it owns:
turn a merged commit history into a deterministic next version, a generated
changelog entry, and a published, tagged artifact — with no human guessing
whether a change is a major, minor, or patch.

## When to use
- A repo tags releases by hand, or "whoever remembers to" — no deterministic
  version-bump rule exists.
- The team already writes Conventional Commits (`feat:`, `fix:`, `BREAKING
  CHANGE:`) but nothing consumes them.
- A changelog is maintained by hand, drifts from reality, or gets skipped
  under deadline pressure.
- A monorepo needs independent per-package versioning instead of one
  repo-wide version.
- A request to "automate releases," "add semantic versioning," or "cut a
  release on every merge to main."

## Workflow
1. **Confirm the commit convention first.** Automated versioning is only as
   good as the input signal. If commits are not already Conventional-Commits
   style, that is a prerequisite, not an optional nice-to-have — propose a
   commit-lint gate (`commitlint` + a `commit-msg` hook or a CI check) before
   or alongside the release tooling. Do not wire version bumps to free-text
   commit messages; the bump decision will be wrong silently.
2. **Map commit types to bump severity** using the standard convention:
   - `fix:` → patch
   - `feat:` → minor
   - `BREAKING CHANGE:` footer, or `!` after the type/scope (e.g. `feat!:`)
     → major
   - `chore:`, `docs:`, `style:`, `refactor:`, `test:`, `ci:` → no release
     by default (configurable — some teams want `refactor:` to trigger a
     patch; confirm rather than assume).
3. **Pick the pre-1.0 policy explicitly.** Under `0.x.y`, a breaking change
   conventionally bumps the minor, not the major, until the project commits
   to `1.0.0`. State this rule in the release-tool config rather than leaving
   default behavior to be discovered later.
4. **Choose the mechanism** appropriate to the ecosystem — do not default to
   one tool for every stack:
   - JS/TS: `semantic-release` (npm) or `changesets` (better fit for
     monorepos with independent package versions).
   - Multi-language / polyglot monorepo: a task-graph-aware release tool
     (see `monorepo-build-optimization`) paired with per-package changelog
     generation, or `release-please` for a language-agnostic, PR-based flow.
   - Single-binary / non-npm ecosystems: `release-please` or a
     `git-cliff`-style changelog generator plus a thin tag-and-publish script.
5. **Gate the release on CI going green**, never on the merge event alone.
   The release step runs only after the full test suite and any required
   scan stages pass — release automation is a pipeline stage, not a separate
   trigger that can race the pipeline.
6. **Generate the changelog from the same commit data** used for the version
   decision, so the two never drift apart. Group entries by type (Features,
   Fixes, Breaking Changes) and link each entry back to its commit or PR.
7. **Automate the publish step** last: tag the commit, push the tag, publish
   the artifact (package registry, container registry, GitHub Release), and
   attach the generated changelog as release notes. Treat publish credentials
   as pipeline secrets, never checked-in tokens.
8. **Handle monorepos with independent versioning** — scope commits to the
   package(s) they actually touched (via changed-file paths or a scoped
   commit convention like `feat(pkg-a):`) so an unrelated package does not
   get an unwarranted version bump. `changesets` and `release-please`'s
   manifest mode both support this natively.

## Checklist / quality gate
- [ ] Commit convention is enforced (lint gate), not just documented.
- [ ] Pre-1.0 vs. post-1.0 bump policy is stated explicitly in config.
- [ ] Release only fires after CI is green — no race with the test suite.
- [ ] Changelog is generated from commit data, not hand-maintained.
- [ ] Monorepo packages version independently and are scoped correctly.
- [ ] Publish credentials are pipeline secrets, not committed tokens.
- [ ] A dry run (`--dry-run` / equivalent) was exercised before the first
      live release to confirm the computed version and changelog are correct.

## References
- [Conventional Commits specification](https://www.conventionalcommits.org/)
- [semantic-release documentation](https://semantic-release.gitbook.io/)

## Composition
Runs as a stage inside a pipeline built by `ci-pipeline-authoring` — that
skill authors the pipeline; this one versions and publishes what it produces.
For a monorepo, pair with `monorepo-build-optimization` so the release step
only fires for packages the affected-project graph says actually changed.
Hands off to `progressive-delivery-rollout` when the published artifact needs
a staged rollout rather than an all-at-once deploy.
