---
name: monorepo-build-optimization
description: Use when monorepo builds are slow, duplicated, or run the full suite on every change — "our CI takes forever," "we're rebuilding everything even for a one-line change," or a monorepo build system needs to be stood up from scratch (Nx, Turborepo, Bazel, Rush). Triggers include low or absent build-cache hit rates, CI minutes ballooning as the repo grows, a request for "affected-only" test/build scoping, or a team debating which monorepo tool to adopt.
---

# monorepo-build-optimization

## Overview
Selects and configures a task-graph build system for a monorepo so that CI
and local builds only do the work a change actually requires. The one job it
owns: turn "we rebuild and retest everything, every time" into "we rebuild
and retest exactly what changed, with cache hits absorbing the rest."

## When to use
- CI build/test time grows roughly linearly with repo size rather than with
  the size of a given change.
- A monorepo has no build-cache layer, or a cache exists but hit rates are
  low.
- A team is standing up a monorepo for the first time and needs to pick a
  task-graph tool.
- "Affected" scoping does not exist — every PR builds and tests the entire
  repo regardless of which packages changed.
- Local developer builds are slow enough to interrupt flow (multi-minute
  rebuilds for single-file edits).

## Workflow
1. **Establish the baseline before touching anything.** Capture current
   cold-build time, warm-build time, CI wall-clock time for a typical PR, and
   (if any caching exists) the current hit rate. Optimization work is
   unverifiable without a before/after number.
2. **Match the tool to the language mix**, not to popularity:
   - Single-language JS/TS monorepo, team wants low config overhead →
     **Turborepo**.
   - Polyglot or JS/TS with deeper plugin/generator needs (scaffolding,
     code-gen, enforced module boundaries) → **Nx**.
   - Very large scale, multi-language, hermetic/reproducible builds are a
     hard requirement (e.g., regulated or security-sensitive builds) →
     **Bazel** — accept its steeper setup and BUILD-file maintenance cost
     deliberately, not by default.
   - JS/TS monorepo already on Rush conventions, or needing strict
     phantom-dependency prevention → **Rush**.
   Do not reach for Bazel by reflex; its setup cost is real and only pays off
   at the scale or hermeticity requirement that justifies it.
3. **Build the task graph from real dependencies**, not directory
   convention. Declare each package's inputs (source files, its own
   dependency packages) and outputs (build artifacts, test results) so the
   tool can compute what "affected" means correctly. A package with an
   undeclared dependency will silently miss rebuilds when that dependency
   changes — verify the graph against a known cross-package change before
   trusting it.
4. **Turn on remote caching** once the local task graph is correct. Local
   caching helps one developer; remote (shared) caching lets CI and every
   teammate reuse each other's build/test outputs. Confirm cache keys include
   every real input (source content hash, dependency versions, relevant env
   vars, tool version) — an under-keyed cache serves stale results, which is
   worse than no cache.
5. **Wire "affected" scoping into CI**, computed against a stable base ref
   (the target branch's merge-base, not just the previous commit — a
   shallow/rebased history will otherwise miscompute the diff). Run the full
   build/test suite only on a schedule or before a release tag, not on every
   PR.
6. **Watch for the failure modes specific to affected-scoping**:
   - A change to a shared config or lint rule may not register as touching
     any package's declared inputs — treat root-level config files as
     inputs to every package, or explicitly enumerate what they affect.
   - A dynamically-loaded or reflection-based dependency (common in some
     backend frameworks) will not show up in a static dependency graph —
     flag these and add explicit graph edges by hand.
   - Flaky affected-detection erodes trust in the whole system fast; when a
     team stops believing "affected" is correct, they revert to running
     everything, which erases the whole optimization.
7. **Report the after-numbers** against the same baseline metrics from step
   1: cache hit rate, cold vs. warm build time, CI wall-clock time for a
   representative PR.

## Checklist / quality gate
- [ ] Before/after build and CI-time numbers are captured and compared.
- [ ] Task graph is built from declared package inputs/outputs, verified
      against at least one real cross-package change.
- [ ] Remote cache keys include every input that can change a build's output
      (source hash, dependency versions, tool version, relevant env vars).
- [ ] Affected-scope detection uses a stable merge-base diff, not just
      `HEAD~1`.
- [ ] Root-level config/lint changes are mapped to the packages they
      actually affect, not silently missed.
- [ ] A full (non-affected) build/test run is still scheduled periodically
      as a correctness backstop.

## References
- [DevOpsSchool — Build Engineer role blueprint](https://www.devopsschool.com/blog/build-engineer-role-blueprint-responsibilities-skills-kpis-and-career-path/) — names monorepo tooling adoption and remote-cache rollout as core build-engineer roadmap items.
- [Nx documentation](https://nx.dev/)
- [Turborepo documentation](https://turborepo.com/docs)
- [Bazel documentation](https://bazel.build/)

## Composition
Feeds `semantic-release-versioning` for monorepos — scoped-package version
bumps depend on the same affected-project graph this skill builds. Sits under
`ci-pipeline-authoring`, which owns the pipeline shell this optimization
plugs into. For build infrastructure that is CPU/runner-bound rather than
cache-bound, hand off to `ci-runner-capacity-and-queue-tuning`.
