---
name: ci-pipeline-authoring
description: Use when a repository has no CI pipeline, an existing pipeline is broken or too slow, or the task is phrased as "set up CI," "add a build/test/deploy pipeline," "wire this into GitHub Actions/GitLab CI/Jenkins," or "add a status check before merge." Detects the project's language and framework, generates lint-test-build-deploy stage YAML, wires dependency caching and native secret injection, and applies a pipeline-health checklist (idempotent stages, fail-fast, artifact retention). Also load it when adding scanning, test, or release stages to an existing pipeline rather than starting one from scratch.
---

# ci-pipeline-authoring

## Overview
Generates and hardens continuous-integration pipeline configuration —
lint, test, build, and deploy stages wired into the project's CI platform
of choice. Owns the pipeline's *structure and mechanics*: stage ordering,
caching, secret handling, and fail-fast behavior. It is the standard entry
point whenever a repository needs its first pipeline or an existing one
needs a new stage bolted on cleanly.

## When to use
- A repository has no CI configuration and a build/test/deploy pipeline is requested.
- An existing pipeline is slow, flaky, or missing a stage (lint, test, security scan, deploy).
- A task reads "add a status check before merge," "block merge on failing tests," or "gate this PR on CI."
- A new language or package is added to a monorepo and needs its own pipeline job.
- Security, QA, or release work asks to add a stage to a pipeline that already exists (scanning, contract tests, versioning) rather than author one from scratch — this skill owns the stage-wiring mechanics those tasks plug into.

## Workflow

1. **Detect the stack.** Identify language(s), package manager(s), and
   existing build tooling from manifest files (`package.json`, `pyproject.toml`,
   `go.mod`, `Cargo.toml`, `pom.xml`, etc.). A monorepo may need one job per
   package or a single job with path filters — check for existing monorepo
   tooling before assuming per-package jobs are needed.

2. **Pick the platform** — usually already decided by where the repo is
   hosted (GitHub Actions for GitHub, GitLab CI for GitLab) unless the user
   names Jenkins or another platform explicitly. Do not introduce a second
   CI platform into a repo that already has one working.

3. **Author the stage sequence**, in this order, each gating the next:
   - **Lint** — fastest feedback, runs first, fails the build on any error.
   - **Test** — unit tests, then integration tests as a separate job if the
     suite is slow enough to want independent scheduling.
   - **Build** — produce the deployable artifact (container image, package,
     binary) only after lint and test pass.
   - **Deploy** — gated on a protected branch or a manual approval; never
     runs on a feature-branch push.

4. **Wire dependency caching** keyed on the lockfile hash (e.g.
   `package-lock.json`, `poetry.lock`, `go.sum`), not on the branch name —
   a branch-keyed cache key never gets a cache hit on new branches and
   defeats the point.

5. **Inject secrets via the platform's native secret store** — GitHub
   Actions encrypted secrets / OIDC, GitLab CI protected variables, or the
   Jenkins credentials plugin. Never place a credential in the pipeline
   YAML itself, even "temporarily" — that YAML is committed to source
   control and any git history rewrite to remove it later is expensive.
   Prefer short-lived OIDC-issued credentials over long-lived static
   secrets when the target platform supports it (for example, cloud
   deployment via OIDC federation instead of a static access key).

6. **Set artifact retention** explicitly — build artifacts and test
   reports should have a defined retention window (days, not "forever"),
   sized to the project's debugging needs versus storage cost.

7. **Make every stage idempotent and fail-fast.** A stage that partially
   mutates state on failure (e.g., a deploy step that pushes some but not
   all resources) leaves the pipeline unsafe to simply re-run — flag this
   during authoring, not after the first bad run in production.

8. **Hand off adjacent concerns rather than absorbing them:**
   - Security scanning stages (SAST/DAST/SCA, secret scanning) are a
     specialized addition — this skill wires the stage slot; a dedicated
     security-scanning skill or reviewer owns severity-gating policy.
   - Versioning, changelog generation, and tag-and-publish automation on
     a green pipeline is a release-management concern layered on top of
     this pipeline, not authored by it.
   - End-to-end and contract test *suites* are authored elsewhere; this
     skill only wires the job that runs them and reports their result as
     a required check.

## Checklist / quality gate
- [ ] Lint, test, build, and deploy are separate stages, each gating the next.
- [ ] No credential, token, or key appears in the pipeline YAML in plaintext.
- [ ] Secrets are injected via the platform's native secret store (or OIDC), scoped to the minimum job that needs them.
- [ ] Dependency caching is keyed on a lockfile hash, not a branch name or a static string.
- [ ] Deploy stage runs only on a protected branch or behind manual approval — never on an arbitrary feature-branch push.
- [ ] Every stage fails fast (no swallowed non-zero exit codes) and is safe to re-run after a failure.
- [ ] Artifact and test-report retention is set to an explicit, bounded window.
- [ ] The pipeline has been run at least once (or dry-run validated) and produces a genuine pass/fail signal — not a stage that always reports green.

## References
- [GitHub Actions documentation](https://docs.github.com/actions)
- [GitLab CI/CD documentation](https://docs.gitlab.com/ee/ci/)

## Composition
Feeds the pipeline slot that `terraform-module-authoring`'s plan-check
workflow, dependency-scanning stages, contract-test suites, and
release-versioning automation all plug into — author the base pipeline
first, then layer those in as additional stages. Pairs with a Dockerfile-
hardening pass when the build stage produces a container image, and with
a monorepo build-optimization pass when CI runtime becomes the bottleneck
in a multi-package repository.
