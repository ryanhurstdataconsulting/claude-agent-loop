---
name: generate-component-changelog
description: Use when a design-system or component-library release needs a changelog and migration notes for consuming teams. Triggers include "design-system changelog," "component release notes," "what broke between v3 and v4," a token or component diff between two versions, or a request to classify changes as breaking, non-breaking, or deprecated before a release ships.
---

# generate-component-changelog

## Overview
Diffs a design system's token and component set between two versions,
classifies every change as breaking, non-breaking, or a deprecation, and
drafts a changelog plus migration guide that follows the project's
established versioning cadence.

## When to use
- A design-system release is imminent and consuming teams need to know
  what changed and what will break their builds.
- A token or component diff between two commits/tags/branches needs to be
  turned into human-readable release notes.
- A component is being deprecated and consuming teams need a migration
  path documented before the old version is removed.
- A retroactive changelog is needed because releases have been shipping
  without one and drift has accumulated.

## Workflow

### 1. Establish the versioning scheme in force
Confirm (don't assume) whether the system follows semantic versioning
(`major.minor.patch`) or a cadence-based scheme (e.g., monthly minor
releases, quarterly majors). This determines which bucket each change
lands in and what version bump the release needs.

### 2. Diff the token and component set
Compare the previous release against the current state:
- **Tokens**: added, removed, or changed values (a value change is
  breaking if consumers referenced the literal value; non-breaking if
  they only ever referenced the token name and the semantic meaning is
  preserved).
- **Components**: added components; removed components; changed public
  API (props, slots, events); changed default visual behavior (size,
  spacing, color) even without an API change — a visual-only change can
  still be breaking for a consumer's visual regression tests.

### 3. Classify every change
Use three buckets, and be conservative — when in doubt, classify up
(toward breaking), because an under-classified breaking change is far
more costly to a consumer than an over-cautious label:

- **Breaking** — requires a consumer to change their code or accept a
  visible visual change to keep working correctly. Examples: a renamed or
  removed prop, a removed component, a token value change with no
  backward-compatible alias, a default behavior change.
- **Non-breaking (additive)** — new capability that doesn't affect
  existing consumers: a new component, a new optional prop with a
  sensible default, a new token that doesn't replace an existing one.
- **Deprecation** — still works today but is scheduled for removal.
  Always paired with: what replaces it, and the target removal version.
  A deprecation without both of those is incomplete.

### 4. Draft the changelog
Group by classification, most-impactful first (breaking → deprecations →
additive → fixes). For each entry:
- What changed (component/token name, one-line description).
- Why, if not obvious (a one-line rationale reduces "why did you do this"
  friction from consuming teams).
- The consumer-facing action required, if any — link straight to the
  migration-guide section for breaking changes rather than repeating it
  inline.

### 5. Draft the migration guide (breaking changes only)
For every breaking change, give the mechanical fix: before/after code
snippet, or a find-and-replace pattern if the change is systematic (e.g.,
"replace every `<Button variant='primary'>` with
`<Button intent='primary'>`"). A migration guide that only explains *what*
changed without showing *how to update* has not done its job.

### 6. Set the version number
Apply the versioning scheme from step 1: any breaking change forces a
major bump (in semver) or waits for the next major-release window
(in cadence-based schemes); deprecations and additions typically ship in
a minor; fixes alone ship in a patch.

## Checklist / quality gate
- Every change in the diff is classified into exactly one of breaking /
  non-breaking / deprecation — no unclassified entries.
- Every deprecation entry names its replacement and target removal
  version.
- Every breaking-change entry links to a migration-guide section with a
  concrete before/after.
- The version bump proposed matches the versioning scheme's own rule for
  the most-severe change present in the release.
- Visual-only changes (no API change, but a rendered difference) are
  still surfaced, not silently omitted because "the props didn't change."

## References
- Design-system versioning guide: https://figr.design/blog/design-system-versioning
- Component-versus-system versioning explainer:
  https://www.uxpin.com/studio/blog/component-versioning-vs-design-system-versioning/

## Composition
Consumes the output of `design-tokens` (token diffs) and pairs with
`draft-contribution-model`'s Release stage as the artifact that stage
produces. Hands off breaking accessibility-relevant changes to
`accessibility-audit` for a re-check before the release ships.
