# Definition of Done — productionization (v1 scope)

> A missing artifact is a failed gate, not an assumption. Check a box
> only when the evidence it names actually exists.

- [ ] `app/` builds from a clean checkout without access to `agent/`,
      `evidence/`, or `scratch/`.
- [ ] Runtime, framework, dependency lockfile, configuration schema,
      endpoints/interfaces, and state dependencies are documented in
      `PROJECT-INVENTORY.md`.
- [ ] Docker image is reproducible (pinned digests), non-root, minimally
      scoped.
- [ ] Secrets are externalized; no verified secret remains in source,
      image, logs, or CI artifact (`repo-security-auditor` gate passed).
- [ ] IaC creates the required environment with least-privilege
      identities (Phase 4 output reviewed, not yet applied without human
      approval).
- [ ] CI runs tests, security scans, and SBOM generation.
- [ ] SBOM (CycloneDX or SPDX) exists under `evidence/`.
- [ ] Required test suites pass (Phase 6 gate).
- [ ] Health checks, structured logging, dashboard/alert definitions, and
      `runbook.md` are present (Phase 7 output).
- [ ] A staging deployment and post-deploy smoke test have passed, OR
      this project has no staging environment and that's recorded as a
      deliberate decision, not an oversight.
- [ ] The handoff package (`app/docs/`) contains architecture,
      operations, and reference-pattern documentation.

## Explicitly NOT required for v1 (see SKILL.md's Future Work section)

- DAST of any kind.
- SLSA/provenance attestation or OPA/CloudFormation Guard policy checks.
- Canary/blue-green release verification.
