---
name: dbt-ci-cd-pipeline-setup
description: Use when a dbt project needs continuous-integration checks on pull requests, a slim-CI job that only builds modified models, automated documentation generation, or a dev-to-prod deploy/promotion job. Triggers include setting up a GitHub Actions/GitLab CI/dbt Cloud job for a dbt repo, "dbt build fails on every PR because it rebuilds the whole warehouse," a request to wire `dbt build --select state:modified+`, or a need to gate merges on `dbt test` passing before models reach production.
---

# dbt-ci-cd-pipeline-setup

## Overview
Configures continuous-integration and deployment pipelines for a dbt project — slim CI on pull requests, automated doc publishing, and a dev-to-prod promotion job — so every model change is built and tested against a real (but cheap) slice of the warehouse before it merges. Owns the CI/CD wiring around dbt; it does not author the models or tests themselves.

## When to use
- A dbt project has no CI at all, or CI rebuilds and tests the entire DAG on every pull request (slow, expensive, and a poor merge-confidence signal).
- A request to set up a GitHub Actions, GitLab CI, or dbt Cloud job for a dbt repository.
- Docs (`dbt docs generate`) are stale or manually generated instead of published automatically on merge.
- A team needs a formal dev → staging/QA → production promotion path instead of running `dbt run` by hand against production.
- An incident traces back to an untested model reaching production because CI did not gate the merge.

## Workflow

1. **Establish environments before touching pipeline YAML.** Confirm (or create) at minimum a `dev` and `prod` target in `profiles.yml`/dbt Cloud environments, each pointing at a separate schema or database so CI runs never write into production data.

2. **Build the slim-CI job — this is the default PR gate, not full-DAG rebuild:**
   - Trigger: pull request opened/updated against the main branch.
   - Command: `dbt build --select state:modified+ --defer --state <path-to-prod-manifest>` — this builds only models changed in the PR plus their downstream dependents, deferring unchanged upstream models to the production manifest instead of rebuilding them. This is the single highest-leverage config in this skill: without `--defer` + `state:modified+`, every PR pays for a full-DAG rebuild.
   - Requires a production `manifest.json` artifact available to the CI job — publish it from the production run job (dbt Cloud does this automatically; self-hosted CI needs an explicit artifact upload/download step).
   - Fail the check on any `dbt build` failure (model build failure, test failure, or a `dbt compile` error) — CI must block the merge, not just warn.

3. **Add doc generation and publishing on merge to main:**
   - `dbt docs generate` after every successful production build.
   - Publish the generated catalog somewhere durable (dbt Cloud's hosted docs, a static-site deploy of `target/`, or an internal docs host) — stale docs erode trust in the semantic layer faster than no docs at all.

4. **Wire the production deploy job separately from the PR-check job.** On merge to main:
   - Run a full `dbt build` (or `dbt run` + `dbt test`) against the production target.
   - Publish the production manifest artifact that the next PR's slim-CI job will defer against — this is what makes step 2 work; skipping this step silently degrades slim CI back into full-DAG builds.
   - Consider a scheduled full rebuild in addition to merge-triggered runs, to catch drift from source-data changes that no model edit would otherwise trigger.

5. **Gate on `dbt test`, not just `dbt run`.** A pipeline that only checks the models build but not that data-quality tests pass gives false confidence — always run `dbt build` (which interleaves run + test per node) or an explicit `dbt run` followed by `dbt test`, never `dbt run` alone.

6. **Add a freshness or source-staleness check** (`dbt source freshness`) as a separate scheduled job if the project ingests from external sources — this catches upstream pipeline failures that a model-only CI job would never see.

7. **Common gotchas to check for:**
   - CI credentials pointed at the same schema as production (defeats the whole purpose of environment separation).
   - Missing `--defer` causing every PR to silently rebuild the full DAG (slow CI, high warehouse cost, and defeats the "test only what changed" goal).
   - No `state:` artifact freshness check — deferring against a stale production manifest can mask breaking changes that already merged since.
   - Long-running CI jobs with no timeout, leaving stuck warehouse queries burning credits after a job is cancelled.

## Checklist / quality gate
- [ ] Separate dev/CI and prod targets/schemas exist; CI cannot write to production data.
- [ ] PR-check job uses `dbt build --select state:modified+ --defer` against a fresh production manifest.
- [ ] Merge-to-main job runs a full build and publishes both docs and the manifest artifact the next PR will defer against.
- [ ] The pipeline fails (blocks merge) on any test failure, not just a build/compile error.
- [ ] Source freshness checks exist if the project depends on external ingestion, on a schedule independent of model-change triggers.
- [ ] No hardcoded credentials in pipeline config; secrets come from the CI platform's secret store.

## References
- dbt Labs documentation on slim CI and `state:modified+` selection
- dbt Cloud CI job configuration and deferral documentation
- Analytics-engineering role expectations naming CI/testing as core engineering practice — industry role-description material (secondary source)

## Composition
Consumes models and tests from `dbt-model-and-test-authoring` and `sql-refactor-to-dbt-layering` — this skill wires the pipeline around work those skills produce, it does not write the SQL. Shares its stage-gate-promote shape with the general `ci-pipeline-authoring` pattern (train → eval → register → deploy is the model-artifact analog used in MLOps CI setups) — reuse that pattern's conventions when the two coexist in one repo.
