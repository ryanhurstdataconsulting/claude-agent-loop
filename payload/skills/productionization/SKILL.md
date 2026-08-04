---
name: productionization
description: Convert a Claude-assisted project codebase into a clean, independently deployable application package — separating app/ (deployable code) from agent/, evidence/, and scratch/ (Claude-agent artifacts) — then walk it through 7 phases (inventory, reference-pattern research, application hardening, infrastructure, security, QA/release, operations) by dispatching this environment's existing subagents. Invoke when preparing any project for cloud deployment, or when asked to "productionize" a codebase.
---

# Productionization

Converts a Claude-assisted project into a package a team that has never
seen the Claude tooling could clone, build, test, and deploy. Source
methodology: a "Productionization Agent Guiding Document" written at
enterprise scale, deliberately right-sized here for small teams and solo
maintainers rather than an organization with a dedicated release and
security function. Scale the ceremony up if your context warrants it.

## Non-goals (v1)

- No standalone orchestrator subagent. Dispatched subagents on this
  platform cannot themselves dispatch further subagents — their `tools:`
  allowlists do not include `Agent`. This skill runs in the main session,
  which is what actually has dispatch access; an "orchestrator agent"
  would structurally lack the one tool it needs.
- No DAST of any kind (local or ROE-staged) in v1.
- No SLSA/provenance attestation or OPA/CloudFormation Guard policy-as-code.
- No canary/blue-green release strategy — v1 release model is an
  immutable-digest deploy with a documented rollback.
- Not a rewrite chasing a fashionable framework.
- Never runs exploits, credential attacks, DoS tests, or intrusive
  scanning against a shared/staging/production target.

See "Future work" at the end of this file for what each deferral means
and when to reconsider it.

## The application boundary

Every productionized project gets this layout at its root (create
directories that don't yet exist; don't restructure ones that already do
unless a phase specifically calls for it):

```text
project-root/
  app/                # The only directory needed for deployable work
    src/
    tests/
    deploy/
      docker/
      infra/
      scripts/
    docs/
      architecture.md
      runbook.md
      threat-model.md
      api.md
    Dockerfile
    .dockerignore
    compose.yaml       # Local dependencies only, never production secrets
    README.md
  agent/                # Prompts, Claude instructions, plans, research
  evidence/             # Scan reports, SBOMs, test reports
  scratch/              # Never shipped, gitignored unless intentionally kept
  PROJECT-INVENTORY.md  # Thin, non-secret discovery summary
```

Boundary rules (verified at the end of Phase 3 and again at the end of
Phase 7):
1. `docker build app/` must succeed without reading `agent/`, `evidence/`,
   `scratch/`, or the parent directory.
2. `.dockerignore` excludes tests, local env files, editor state,
   credentials, and reports from image layers.
3. `app/README.md` states prerequisites, local start/test/build/run
   commands, configuration schema, health endpoint, and deployment
   workflow.
4. No absolute paths, shell aliases, private registries, or local-only
   services are implicit prerequisites.

## Two invocation modes

**Guided (default).** Run each phase below as its own Agent-tool
dispatch, in order, reviewing that phase's output before starting the
next. This is the only mode exercised by the initial pilot — every phase
boundary gets a human review the first time through a given project.

**Full-send (opt-in — only when the user explicitly asks for the whole
pipeline hands-off, in their own words, or an Ultracode-style standing
directive is active for the session).** Build a Workflow script that
pipelines the 7 phases below with `pipeline()`, keeping phases that don't
depend on each other's output concurrent (Reference-pattern research and
Application hardening's stack-detection can run alongside each other once
Inventory is done; QA/release and Operations can run concurrently once
Security has produced its gate result). This is a legitimate Workflow
invocation under this environment's rules — invoking this skill is the
user's explicit opt-in. Full-send mode should only be used for a project
that has already been through guided mode successfully at least once.

## Phases

Dispatch order matters for guided mode; the parenthetical after each
phase name is which existing subagent handles it — no new subagents are
created for this skill.

### Phase 1 — Inventory & discovery (`Explore`)

Dispatch `Explore` (search breadth: "very thorough") against the target
project root. Ask it to enumerate: language(s)/runtime(s), package
manager(s), build/test commands, all manifests and lockfiles, Dockerfiles,
IaC directories, CI workflow files, environment variables referenced in
code, HTTP endpoints/routes, outbound third-party API calls, and
persistent stores (databases, queues, object storage) it can find
references to. Do not assume a blank slate — a project may already have
partial `deploy/`, `infra/`, or CI scaffolding; Inventory's job is to
report what's actually there, not what a fresh project would need.

From Explore's findings, fill in `templates/productionization-intake.yaml`
(copy it into the target project as `productionization-intake.yaml` at
the project root) and write `PROJECT-INVENTORY.md` at the project root
using `templates/project-inventory.md` as the skeleton. Record every
unknown as an unknown — do not guess at `business_criticality`,
`security_test_authorization`, or other owner-only fields; ask the user
for those specifically before Phase 5 needs them.

### Phase 2 — Reference-pattern research (`software-architect`)

Dispatch `software-architect` with the exact stack identified in Phase 1
(language, major framework version, package manager, deployment target
candidate). Ask for at least 3 candidate reference repositories or
official framework examples, scored against: stack match, maintenance
activity, security posture, operational fit, license fit, and whether the
pattern is extractable (architecture/config conventions) versus requiring
a blind copy of application logic. Output goes to
`app/docs/reference-patterns.md` (`templates/reference-patterns.md` is
the skeleton) with exact URLs, versions checked, and rejected candidates
— never claim a reference repo is "production ready" without citing the
evidence for that claim.

### Phase 3 — Application hardening (`backend-engineer` and/or `frontend-engineer`, plus `technical-writer` and `voltagent-dev-exp:refactoring-specialist`)

**Decision rule** — use Phase 1's inventory to decide dispatch.
- If the project has one backend-only service (API, worker, CLI, pipeline
  with no separate browser-facing UI) → dispatch `backend-engineer` only.
- If the project has a distinct frontend service (a separate web app
  directory with its own package.json/build, e.g. a Next.js `web/`
  alongside a Python `api/`) → dispatch **both**, `backend-engineer` for
  the API/worker/pipeline services and `frontend-engineer` for the web
  service, as two separate Agent-tool calls (they can run concurrently in
  full-send mode; sequential in guided mode is fine too).
- If the project is frontend-only (a static site or SPA with no separate
  backend service under this project's control) → dispatch
  `frontend-engineer` only.

Each dispatch reconstructs only what's necessary to make its service
independently runnable: move deployable source into `app/`, add a typed
config module that validates required env vars at startup and never logs
secret values, deterministic dependency installation from lockfiles,
`/healthz` (liveness) and `/readyz` (dependency readiness, no detailed
error leakage), structured stdout/stderr logs with no secrets/tokens/PII,
graceful shutdown, request/connection timeouts, bounded retries with
backoff, idempotency for retryable operations, and a Dockerfile per
`templates/dockerfile-baseline.md`'s pattern for the detected stack
family. Verify boundary rule 1 (`docker build app/` succeeds without
reading `agent/`/`evidence/`/`scratch/`) at the end of this phase.

**Two additional dispatches run in this same phase, independent of stack
(always both, regardless of the backend/frontend split above):**

- `technical-writer`: review and consolidate every piece of Claude-facing
  documentation already in the project — `CLAUDE.md`, any `.claude/`
  scaffolding, `docs/superpowers/specs/`, `docs/superpowers/plans/`,
  `SUBAGENTS.md` if present, and any other agent-instruction file — into
  something clear and concise for an agent picking up the project cold.
  Consolidate duplication, remove stale references (dead links, renamed
  files, superseded specs), and keep the precedence/structure this
  workspace already uses (project `CLAUDE.md` as an index linking to
  specialized docs, not a monolith). This dispatch edits documentation
  only — it must not touch application source, `app/`, or any file
  outside doc/instruction files.
- `voltagent-dev-exp:refactoring-specialist`: a code cleanup and
  documentation pass across the application source identified in Phase 1
  — dead code, duplicated logic, inconsistent naming, and missing or
  stale inline documentation (docstrings/comments), while preserving all
  existing behavior. Run the project's existing test suite (if one
  exists) before and after to confirm no behavior changed. This dispatch
  is scoped to application source only — it does not touch `CLAUDE.md` or
  agent-instruction files (that's `technical-writer`'s job above), and it
  does not invent new features or abstractions beyond cleanup.

Both dispatches can run concurrently with each other and with the
backend/frontend hardening dispatch in full-send mode; in guided mode,
run them after the backend/frontend dispatch so there's real hardened
code to clean up and real deployment docs to fold into the consolidated
`CLAUDE.md`, rather than before.

### Phase 4 — Infrastructure (`cloud-architect` + `devops-engineer`)

Two dispatches, not one — they own genuinely different existing scopes:
- `cloud-architect`: IAM least-privilege plan (separate execution role
  vs. task role for ECS), VPC/network topology (private subnets, ALB for
  public ingress, security-group scoping), and the Terraform/CDK module
  layout under `app/deploy/infra/` (`modules/`, `environments/{dev,
  staging,production}/`, `policies/`).
- `devops-engineer`: the CI/CD workflow (`.github/workflows/` or
  equivalent), Dockerfile hardening review, and image build/push/deploy
  steps. **Feed it Phase 5's static-audit CI/CD recommendations if Phase 5 has
  already run** (in guided mode, run Phase 5 before
  finalizing this phase's CI workflow, or re-run this phase's CI step
  once Phase 5's recommendations exist) — a static audit only recommends
  CI/CD changes, it never authors them, so `devops-engineer` is the single
  place those recommendations actually land. Do not let both
  phases independently propose conflicting CI configs.

Neither dispatch applies a cloud change or grants a broad IAM permission
directly — output is a plan/IaC diff for human review, per this
environment's standing "human approval controls impact" rule.

### Phase 5 — Security (a static-audit agent, if you have one, + `security-engineer`)

This phase has two halves: a **static repo audit**, then a **threat model
and triage**. How you run the first half depends on your environment.

**If your environment has a dedicated static-security-audit agent** (this
framework does not ship one; some setups add a `repo-security-auditor` or
similar that knows local conventions like PII rules and vendor-finding
routing), dispatch it unchanged for the static half — scanners, secrets,
dependency CVEs, OWASP-class findings, dead-code surface, gitignore
compliance — writing `<target>/SECURITY_AUDIT.md`. Its CI/CD
recommendations, if any, are handed to Phase 4's `devops-engineer`
dispatch per the note above, never actioned independently here.

**If you have no such agent, `security-engineer` covers both halves** —
give it the static-audit scope explicitly in its brief, since it will not
assume it. Do not skip the static half; it is what produces the
`SECURITY_AUDIT.md` this phase's gate reads.

Then dispatch `security-engineer` for the ground a static audit
does not cover: a lightweight threat model (entry points,
identities, secrets, network paths, authorization decisions, state
stores, logs, third parties — one paragraph per trust boundary is
enough for a small project) and CVSS-based triage of anything
the static audit flagged as "needs a human decision." Also
generate the v1 SBOM here (CycloneDX or SPDX, one CLI call for the
detected stack — e.g. `cyclonedx-py` for Python, `cyclonedx-npm` for
Node) and attach it under `evidence/`.

**SBOM fallback (learned in the first pilot run).** Do not assume the
SBOM tooling is installed — `cyclonedx-py`, `cyclonedx-npm`, `syft`, and
`trivy` were all absent, as were `pip-audit`, `gitleaks`, and `semgrep`.
Never install scanners globally to satisfy this step. Either use a
`--user`/venv-local install confined to the project, or generate the SBOM
directly from the lockfiles, which is an explicitly acceptable fallback.
Record which method was used inside the SBOM document itself, and state
plainly that no CVE database was consulted if none was. A missing SBOM
fails this gate; a lockfile-derived SBOM passes it. Note also that OS-level
binaries the app shells out to (e.g. `ffmpeg`) will not appear in any
language-package SBOM — call them out separately rather than letting the
SBOM imply coverage it does not have.

This phase is a **fail-closed gate**: a verified secret, a critical/high
finding without an accepted-risk disposition from the project owner, or
a missing SBOM blocks promotion to Phase 6.

### Phase 6 — QA / release (`qa-engineer`)

Dispatch `qa-engineer` to assess (not necessarily build from scratch) the
test pyramid: unit, integration (using isolated resources, never a shared
DB), contract tests for any API/event interfaces, and end-to-end tests
for critical paths. Ask for a test-strategy and coverage-gap report
against what Phase 1's inventory found. This phase is also a fail-closed
gate: required test suites must pass before Phase 7's release-readiness
checklist can be marked done.

### Phase 7 — Operations (`sre`)

Dispatch `sre` to produce: a service dashboard spec (request rate, error
rate, latency, saturation, deploy version, dependency health, resource
utilization), alert definitions (owner, severity, threshold, runbook URL,
escalation route), and `app/docs/runbook.md`
(`templates/runbook.md` is the skeleton) covering rollout, rollback, top
alerts, logs/traces, safe restart, backup/restore, dependency outage, and
incident communication. Verify boundary rule 1 again here (the runbook
and any ops tooling added must not have snuck a dependency on
`agent/`/`evidence/`/`scratch/` back into `app/`).

## Dispatch hygiene (learned in the first pilot run)

Two failure modes cost real time on the first run. Put both into any
dispatch brief that will build a container or run a long command:

- **Never end a turn with a background build still running.** A Phase 3
  dispatch launched two `docker build` runs in the background and its turn
  ended before they wrote their exit markers; the builds completed fine,
  but their wrapper shells were orphaned and the results were lost, so the
  orchestrator sat waiting on a marker file that would never appear. Tell
  each dispatch to either run long builds synchronously, or poll them to
  completion and report the actual exit code before finishing.
- **Warn about legitimately slow builds.** A Python image installing
  `ffmpeg` on Debian took ~34 minutes cold (a very large `apt-get`
  dependency chain) and ~2 minutes warm. Without that warning, a slow build
  reads as a hang and gets killed. State the expected cold-build cost in
  the brief when the stack has heavy OS dependencies.

## Gates

| Gate | Blocks promotion when |
| --- | --- |
| Security (Phase 5) | A verified secret is present; a critical/high finding has no accepted-risk disposition from the project owner; no SBOM exists. |
| QA/release (Phase 6) | A required test suite fails. |
| Application boundary | `docker build app/` fails, or succeeds only by reading outside `app/`. |

Human-approval boundaries are **not** re-specified by this skill — they
defer to what already governs this workspace: any real AWS/cloud resource
change, secret rotation, or production touch follows the existing AWS
access rules and session-refresh convention; any git push to a shared
remote follows the existing global git-safety rules; any DAST/security
test against a non-local target is out of scope entirely for v1 (see
Non-goals).

## Definition of Done

See `templates/definition-of-done.md` for the full checklist. A missing
artifact is a failed gate, not an assumption — do not check a box without
the evidence it names.

## Templates

| File | Purpose |
| --- | --- |
| `templates/productionization-intake.yaml` | Per-project intake schema, filled in during Phase 1. |
| `templates/project-inventory.md` | `PROJECT-INVENTORY.md` skeleton, filled in during Phase 1. |
| `templates/reference-patterns.md` | Scoring-matrix + citation skeleton, filled in during Phase 2. |
| `templates/dockerfile-baseline.md` | Illustrative multi-stage Dockerfile patterns per stack family, referenced in Phase 3. |
| `templates/runbook.md` | Runbook skeleton, filled in during Phase 7. |
| `templates/definition-of-done.md` | The v1-scoped Definition of Done checklist. |

## Future work (explicitly deferred, not forgotten)

- **DAST.** Cut entirely for v1, not merely scaled down. Reconsider only
  if a specific client engagement has a real need for it — reintroduce as
  local/ephemeral scans first (e.g. an OWASP ZAP baseline scan against a
  local container), never staging/production DAST without a written ROE.
- **SLSA/provenance + OPA/CloudFormation Guard.** Sized for a team with a
  dedicated platform/security function. If nothing at your scale consumes
  this output, it is pure ceremony — revisit if that changes.
- **Canary/blue-green releases.** Most small projects are low-traffic. Revisit only if a specific project reaches
  real production traffic where a bad deploy's blast radius justifies the
  added release complexity.
