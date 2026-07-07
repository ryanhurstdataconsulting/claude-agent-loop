---
name: sast-dast-sca-pipeline-integration
description: Use when adding automated security scanning (SAST, DAST, or SCA/dependency scanning) to a CI/CD pipeline, closing a DevSecOps maturity gap, or tuning severity-based gating on an existing scan stage that is either too noisy or too silent. Triggers include "add security scanning to the pipeline," a request for static analysis or dependency-vulnerability scanning, a DSOMM or security-maturity assessment naming a scanning gap, alert fatigue from an over-broad scan gate, or a false positive that needs a documented suppression.
---

# sast-dast-sca-pipeline-integration

## Overview
Selects and wires static analysis (SAST), dynamic analysis (DAST), and software-composition analysis (SCA/dependency scanning) into a CI/CD pipeline, then tunes the severity-based gate so it blocks what matters without drowning the team in noise. It owns getting automated security scanning from "absent or ad hoc" to "running on every change, gating on real risk."

## When to use
- A pipeline has no automated security scanning and one is being added for the first time.
- A DevSecOps maturity assessment (for example, against the OWASP DSOMM) identifies a scanning gap.
- An existing scan stage is either blocking merges on low-severity noise (alert fatigue) or missing findings it should catch (gate set too loose).
- A specific finding needs a documented, justified suppression rather than a silent ignore.
- A new language, framework, or dependency ecosystem is added to a repo and its scan coverage needs to be verified or extended.

## Workflow

1. **Inventory what the pipeline already runs.** Before adding anything, check for existing SAST/DAST/SCA steps (including ones bolted on by a platform default, like GitHub's built-in dependency alerts). Duplicate tooling wastes CI minutes and creates conflicting findings.

2. **Select tooling by category and stack fit.**
   - **SAST** (scans source code for insecure patterns without running it): pick a tool that supports the repo's languages natively — for example, Semgrep for fast, rule-based multi-language scanning, or CodeQL for deeper data-flow analysis. Semgrep is generally the faster first stage; CodeQL catches more but runs slower and suits a scheduled or nightly job as well as a merge gate.
   - **DAST** (scans a running instance for exploitable behavior): needs a deployed target — a staging environment or an ephemeral CI-spun instance. OWASP ZAP is the common open-source default; run it as a baseline scan on every deploy to staging, and a fuller active scan on a schedule rather than every commit (active scans are slow and can be disruptive).
   - **SCA** (scans dependencies for known vulnerabilities and license issues): pick a tool matched to the package ecosystem — Trivy (broad, covers containers and filesystems too) or Snyk (deeper remediation guidance, commercial). Run SCA on every PR; it is fast and catches supply-chain risk early.

3. **Wire each stage into CI with the right trigger.**
   - SAST and SCA: run on every pull request, blocking merge on the configured severity threshold.
   - DAST: run post-deploy against staging, not against production, and not synchronously blocking every PR (too slow) — use a scheduled or on-demand job, or gate only the release/promotion step on it.
   - Container/image scanning (if applicable): run at image-build time, before the image is pushed to a registry.

4. **Set severity-based gating deliberately — this is the step most teams get wrong.**
   - Start by blocking merges only on **critical/high** findings. Blocking on medium/low from day one is the single most common cause of alert fatigue and leads to teams disabling the gate entirely.
   - Route medium/low findings to a tracked backlog (ticket, dashboard) rather than a merge block, and revisit the threshold once the team has burned down the initial backlog of pre-existing findings.
   - Never gate on a raw finding count — a single critical finding should block; a hundred informational findings should not.

5. **Handle false positives with a documented suppression, not a silent ignore.** Every suppression needs: the finding ID/rule, the reason it does not apply in this context, who approved it, and a re-review date if the surrounding code might change the answer later. An undocumented suppression list rots into either a bypass mechanism or a source of re-litigated arguments.

6. **Verify the gate actually gates.** After wiring, confirm the pipeline fails on a known-bad test case (a deliberately vulnerable dependency version, a known-insecure code pattern) and passes on a clean baseline. A scanning stage that runs but never fails the build is decoration, not a gate.

7. **Revisit as the DSOMM maturity level rises.** Initial rollout targets a baseline maturity level (scanning exists, blocks on critical/high). As the team's tolerance and remediation velocity improve, tighten the threshold, add more scan types, and reduce the reliance on suppressions.

## Checklist / quality gate
- SAST, DAST, and SCA each have an owner tool, and none duplicate an existing pipeline step.
- Each scan type triggers at the appropriate point (SAST/SCA on PR, DAST post-deploy/scheduled, image scanning at build).
- The severity gate blocks on critical/high only at initial rollout, with a documented plan to tighten it.
- Every suppression has a reason, an approver, and (where relevant) a re-review date recorded alongside it — not just silenced in a config file.
- A known-bad test case was run through the pipeline to confirm the gate actually fails the build.
- Non-blocking findings route to a tracked backlog rather than disappearing.

## References
- OWASP DevSecOps Maturity Model (DSOMM): https://owasp.org/www-project-devsecops-maturity-model/
- Practical DevSecOps — DevSecOps Roadmap: https://www.practical-devsecops.com/devsecops-roadmap/ (names SAST, DAST, SCA, and secret scanning as core pipeline stages)

## Composition
Adds stages to a pipeline authored by `ci-pipeline-authoring`. Pairs with `secrets-scanning-remediation` (secret detection is a related but distinct scan category, usually wired alongside SCA). Findings severe enough to need formal scoring and a disclosure write-up hand off to `vulnerability-triage-and-disclosure`. A recurring class of finding that STRIDE analysis predicted during design review connects back to `threat-model-on-diff` — closing that loop is how a one-off finding becomes a permanent gate.
