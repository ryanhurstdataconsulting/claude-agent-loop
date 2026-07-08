# claude-agent-loop

A self-contained, portable Claude Code environment: a curated set of skills, an
agent, tools, plugins, MCP specs, and a self-learning **Resource Loop**,
packaged so any machine can be configured the same way in one command. The loop
does not just deploy resources — it measures every task, scores the outcome, and
acts on that history under a hard safety floor. See **`LEARNING.md`** for how
that works.

## Quickstart

```bash
bash install.sh
```

Then, in Claude Code, run:

```
/environment-bootstrap
```

That inspects your machine, asks a few questions, and tailors the registry,
your `CLAUDE.md`, and the database/MCP templates to your stack. Restart Claude
Code (or run `/hooks` to reload), give it a task, and you should see a line
that begins with `Resource Loop —`. That is the environment working.

The installer is **idempotent** — safe to run twice — and it **merges** into
your existing config rather than overwriting it. It backs up your
`settings.json` and `CLAUDE.md` once, to `*.bak-agentloop`, before it changes
anything.

## What gets installed

Into `~/.claude/`:

| Resource | Count | What it is |
|---|---|---|
| `skills/` | 168 | 11 core framework skills plus a 157-skill role-based library covering every tech-company role — product, design, engineering, infra, data, ML/AI, and leadership. Browse them in the Skill catalog below. |
| `agents/` | 1 | `sql-safety-reviewer` — a read-only SQL safety gate. |
| `tools/` | 22 | Python and shell helpers: the learning tools (metrics harvester, task scorer, `SCALES.md`/`HEURISTICS.md` linters, the heuristics engine, the pending-themes check, the visibility classifier, and the autocommit/rollback/digest/promote scripts), plus the carried set (registry linter, grammar gate, secret/PII scrub gate, git and environment preflights, an SSH-tunnel keepalive, background build-watch, a transcript distiller, and coverage/canary checkers), plus `templates/` and `tests/`. |
| `registry/` | index + 26 guides | The resource registry the Resource Loop reads: `REGISTRY.md`, `TRIGGERS.md`, `guides/`, and `candidates/`. |
| `hooks/` | 4 | `inject-resource-loop.sh` (SessionStart), `harvest-metrics.sh` (SubagentStop + SessionEnd), `precompact-event.sh` (PreCompact), and `auto-update.sh` (SessionStart + UserPromptSubmit — fast-forward-pulls the package from git on a new or stale-resumed session; a pre-flight skips a dirty or diverged repo so local work is never clobbered). |
| `learning/` | 4 seeds | The self-learning state: `SCALES.md`, `HEURISTICS.md`, `LOOP_THEMES.md`, and `CLIENT_MARKERS.txt`, copied once from the shipped seeds and then kept local-only (never published). |
| plugins | 11 | `superpowers` plus the ten VoltAgent subagent-catalog categories, from two marketplaces (`claude-plugins-official`, `voltagent-subagents`). |

Into `~/.claude/settings.json` (merged, never clobbered): the four hook groups
(SessionStart, SubagentStop, SessionEnd, PreCompact), the 11-plugin
`enabledPlugins` map, and the two marketplace registrations.

Into `~/.claude/CLAUDE.md` (appended between `<!-- BEGIN AGENT-LOOP -->`
sentinels): the operating directives — the Resource Loop protocol, the
token-and-context discipline, the grammar standard, the data-visualization
directive, and a pointer to subagent routing.

**Not installed:** any secret, any hostname, or a live database MCP
registration. Those ship as *specs* under `payload/mcp-specs/`, which you wire
up yourself with your own credentials — the `environment-bootstrap` skill
walks you through it. See `payload/mcp-specs/postgres-readonly.md`.

<!-- BEGIN SKILL CATALOG -->
## Skill catalog

**168 skills across 34 categories** — every role in a tech company, from product management through database, ML/AI, and UI. Each is a trigger-oriented `SKILL.md` under [`payload/skills/`](payload/skills/) that an agent loads when a task matches. `★` marks a cross-cutting skill (27 of them) that recurs across roles. The plain index is [`payload/skills/CATALOG.md`](payload/skills/CATALOG.md).

| Category | Skills |
|---|--:|
| Core framework skills | 11 |
| Product Management | 5 |
| Program / Project Management | 5 |
| UX Research | 5 |
| Product & UX Design | 7 |
| UI / Visual & Design Systems | 8 |
| Frontend Engineering | 6 |
| Backend Engineering | 6 |
| Full-Stack Engineering | 3 |
| Mobile Engineering | 5 |
| Embedded / Firmware | 5 |
| API / Integrations | 6 |
| Software Architecture / Tech Lead | 4 |
| DevOps | 3 |
| CI/CD & Infrastructure-as-Code | 2 |
| Site Reliability Engineering | 6 |
| Platform Engineering | 5 |
| Cloud / Infrastructure | 5 |
| Security | 5 |
| QA / SDET | 6 |
| Release / Build / Dev-Productivity | 4 |
| Data Engineering | 5 |
| Analytics Engineering & BI | 7 |
| Database Administration | 6 |
| Data Science | 4 |
| Machine Learning Engineering | 4 |
| MLOps / ML Platform | 5 |
| AI / GenAI / LLM | 4 |
| Engineering Management | 2 |
| Engineering Leadership (Director / VP / CTO) | 3 |
| Developer Relations | 4 |
| Solutions / Sales Engineering | 4 |
| Technical Writing / Docs | 4 |
| Technical Support | 4 |
| **Total** | **168** |

<details>
<summary><b>Core framework skills</b> &middot; 11</summary>

- **`resource-loop`** — Run at the start of EVERY session and before every new task — match the task against your resource registry, announce deployments, route subagents by model…
- **`token-efficiency`** — Starting a long-horizon, high-volume, or multi-file task, or before dispatching a fleet of subagents — set context and token discipline without sacrificing…
- **`environment-bootstrap`** — Run once after install (and any time your setup changes) to tailor this Claude Code environment to YOUR machine.
- **`theme-assessment`** — Work the loop-themes backlog — cluster the unprocessed NEW rows in LOOP_THEMES.md, pull the metric records they reference, and decide per cluster to promote,…
- **`data-visualization`** — Master data visualization with chart selection, dashboard design, Tableau, Power BI, and effective data storytelling.
- **`visual-hierarchy-layered-charts`** — Apply the contrast ladder, stroke hierarchy ladder, and figure-ground dominance techniques when designing multi-series data visualizations with defined…
- **`explain-code`** — Explains code with visual diagrams and analogies.
- **`excalidraw-diagram`** — >
- **`document-render`** — Rendering a markdown deliverable to PDF (reports, leadership briefs, legal contracts) or converting a generated .pptx / .docx deck to PDF or per-slide images…
- **`tauri-desktop-dev`** — Building or debugging a Tauri 2 desktop app, or packaging a Python / FastAPI backend as a Tauri sidecar.
- **`aws-local-emulation`** — A dev or test task will create, mutate, or "verify" AWS resources (create-table, put-item, s3 mb, create-queue, create-function, deploy a CDK/Terraform stack)…

</details>

<details>
<summary><b>Product Management</b> &middot; 5</summary>

- &#9733; **`write-a-prd`** — A feature idea, one-line brief, or chat thread needs to become a structured product requirements document (PRD) before engineering can scope or estimate it.
- **`prioritize-with-rice`** — A backlog of candidate features, initiatives, or bugs needs a defensible ranked order and someone asks for a "priority score," "RICE score," or "what should…
- **`build-a-roadmap`** — A prioritized backlog and a set of strategic themes need to become a shareable roadmap artifact — a timeline, a now/next/later board, or a stakeholder-facing…
- **`run-competitive-analysis`** — A positioning decision or a build-vs-buy call needs a market or competitor teardown — a feature comparison matrix, a pricing comparison, or a gap analysis…
- **`draft-okrs`** — A product or team needs quarterly or annual objectives and key results drafted from a strategy statement — turning a goal like "grow enterprise adoption" into…

</details>

<details>
<summary><b>Program / Project Management</b> &middot; 5</summary>

- &#9733; **`raid-log-maintainer`** — Risks, assumptions, issues, or dependencies surface from standup notes, meeting transcripts, chat threads, or tickets and need to be captured in a structured,…
- **`map-dependencies`** — A multi-team initiative needs its cross-team hand-offs, blockers, and critical path made visible — building a dependency graph or table from linked…
- **`run-raci-assignment`** — A new program or initiative spans multiple contributing teams and needs role clarity before work starts — populating a RACI matrix…
- &#9733; **`sprint-plan-from-spec`** — An approved spec, PRD, or roadmap item needs to be decomposed into a sprint plan and a ticket set — parsing scope into tickets, flagging estimates for human…
- &#9733; **`status-report`** — A recurring status update is due to any audience — a team standup summary, a program-level stakeholder report built from a RAID log and sprint burndown, or an…

</details>

<details>
<summary><b>UX Research</b> &middot; 5</summary>

- **`write-a-research-plan`** — A user-research study is being scoped and needs its objectives, method, and timeline locked down before recruiting starts — turning a vague business question…
- **`draft-discussion-guide-and-screener`** — An interview or usability study needs a moderator discussion guide and a participant screener drafted from an existing research plan.
- **`synthesize-with-affinity-mapping`** — Raw qualitative research data — interview transcripts, usability-test notes, open-ended survey verbatims, support-ticket text — needs to become organized…
- **`design-a-survey`** — A research question calls for quantitative or attitudinal data at scale rather than a small qualitative sample — drafting unbiased survey items, choosing…
- **`maintain-research-repository`** — A research organization's past studies, findings, and artifacts need to become searchable and reusable instead of trapped in decks and scattered docs —…

</details>

<details>
<summary><b>Product & UX Design</b> &middot; 7</summary>

- **`run-a-design-sprint`** — A team needs to validate a significant product bet in days rather than months — structuring a five-day (or compressed) design sprint agenda, converging on a…
- **`structure-design-critique`** — A design (screen, flow, component, or full feature) needs structured peer or stakeholder feedback before it ships, or when a pile of raw design comments needs…
- **`write-jtbd-statements`** — A feature idea, customer quote, or support ticket needs to be re-grounded in the underlying customer job rather than a surface-level feature request —…
- **`build-a-prototype-plan`** — A design needs a prototype scoped for usability testing — deciding what fidelity level is needed, which screens and states must be real versus faked, and…
- **`run-heuristic-evaluation`** — An existing interface, flow, or feature needs a fast usability audit before, or instead of, a full research study — walking the interface against Nielsen's 10…
- **`map-user-journey`** — A team needs to see a user's end-to-end path across touchpoints to find friction or gaps — building a journey map (stages, actions, thoughts/feelings, pain…
- **`build-ia-sitemap`** — A product needs its navigation or information architecture defined or audited — inventorying content and features, grouping them into a taxonomy informed by…

</details>

<details>
<summary><b>UI / Visual & Design Systems</b> &middot; 8</summary>

- &#9733; **`accessibility-audit`** — A screen, component, or flow needs a WCAG accessibility pass before it ships — color-contrast ratios, keyboard navigation, focus order, and ARIA semantics.
- **`design-tokens`** — A brand or style spec (colors, type scale, spacing, radii) needs to become a structured, tool-portable design-token file, or when an existing token set needs…
- **`build-a-type-scale`** — A product needs a consistent typographic scale defined or audited — sizes, weights, and line-heights mapped to semantic roles like display, heading, body, and…
- **`audit-visual-consistency`** — A growing product surface needs a check for visual drift from its documented style guide or design tokens — off-palette colors, inconsistent spacing,…
- **`draft-contribution-model`** — A design system needs a documented process for how teams propose, review, and ship new or changed components.
- **`generate-component-changelog`** — A design-system or component-library release needs a changelog and migration notes for consuming teams.
- **`audit-storybook-documentation`** — A component library's Storybook (or equivalent living style guide such as zeroheight) needs a completeness and consistency check across entries.
- **`design-ops-tooling-audit`** — A design organization's tool stack — licenses, plugins, and the design-to-code hand-off chain — needs a health, cost, or redundancy review.

</details>

<details>
<summary><b>Frontend Engineering</b> &middot; 6</summary>

- **`scaffold-react-component-with-tests`** — A new UI component, page, or view is requested in a React (or similar component-framework) codebase.
- **`migrate-component-to-design-system`** — A legacy, ad hoc, or hardcoded-style component needs to move onto a shared design-system or design-token library.
- **`audit-core-web-vitals`** — A performance regression, a low Lighthouse score, or a Core Web Vitals alert (LCP, INP, CLS) is reported for a web page or app.
- **`add-accessibility-audit-fixes`** — A WCAG/a11y compliance request comes in, an automated accessibility test (axe-core, Lighthouse a11y, pa11y) fails, or a screen-reader/keyboard-only bug report…
- **`convert-js-to-typescript`** — Use for an incremental TypeScript migration of a JavaScript file, module, or whole project.
- **`integrate-rest-api-client`** — Wiring a frontend to a new or changed backend REST endpoint.

</details>

<details>
<summary><b>Backend Engineering</b> &middot; 6</summary>

- **`scaffold-rest-endpoint-with-tests`** — A new CRUD or resource endpoint is requested on a backend service — "add a POST /orders endpoint," "expose a new resource," "wire up create/read/update/delete…
- **`write-database-migration-with-rollback`** — A schema change is requested against a relational database — a new column, table, index, constraint, or a data backfill on an existing table.
- **`add-caching-layer`** — A latency or hot-path performance request calls for a caching layer — "this endpoint is slow under load," "cache this query," "add Redis in front of X," or a…
- **`implement-authn-authz`** — A new endpoint or route needs securing, or a login/session flow needs to be added — "add login to this app," "protect this route," "only admins should be able…
- **`containerize-service-for-deployment`** — A service needs a Dockerfile and a container build wired into CI — "containerize this app," "add a Dockerfile," "this build image is huge," or a container…
- &#9733; **`add-structured-logging-and-tracing`** — A service has an observability gap — no structured logs, no distributed tracing across service calls, or a postmortem action item calling for better…

</details>

<details>
<summary><b>Full-Stack Engineering</b> &middot; 3</summary>

- **`scaffold-full-feature-slice`** — A request reads as "add feature X" or "build out Y" spanning the whole stack — a new capability that needs a database migration, an API endpoint, a typed…
- &#9733; **`profile-and-fix-slow-request`** — A user reports "this is slow," a specific endpoint or page shows a measured latency regression, or a request/response cycle needs diagnosis across the…
- &#9733; **`write-unit-tests-with-coverage-target`** — Use whenever a code change lands without accompanying tests, a coverage report shows a module or diff below a target threshold, or a task explicitly asks to…

</details>

<details>
<summary><b>Mobile Engineering</b> &middot; 5</summary>

- **`scaffold-mobile-screen-with-viewmodel`** — A mobile codebase (Jetpack Compose, SwiftUI, or React Native) needs a new screen, feature module, or view — generates the screen composable/view plus its…
- **`set-up-fastlane-release-pipeline`** — A mobile app needs an automated build-sign-upload pipeline for the App Store or Play Store — authoring a Fastfile, wiring lanes for build/test/sign/upload,…
- **`integrate-crash-reporting-and-monitoring`** — A mobile app needs crash reporting and performance monitoring added or upgraded — SDK integration for tools such as Sentry, Crashlytics, Datadog, or Instabug,…
- **`implement-offline-first-sync`** — A mobile feature needs local persistence with server reconciliation — designing a conflict-resolution strategy (last-write-wins, merge, or user-prompt), a…
- **`audit-app-store-review-compliance`** — Use before submitting a mobile app for App Store or Play Store review, or after a build was rejected — checks permission-usage justifications, the iOS privacy…

</details>

<details>
<summary><b>Embedded / Firmware</b> &middot; 5</summary>

- **`write-peripheral-driver-with-hil-test`** — A new sensor, radio, or peripheral IC needs a driver over SPI/I2C/UART/CAN/1-Wire, when an existing driver is being ported to a new MCU or bus instance, or…
- **`design-rtos-task-and-ipc`** — Adding a new concurrent task, thread, or feature to an RTOS application (FreeRTOS, Zephyr, QNX, ThreadX) and deciding its priority, stack size, and how it…
- **`run-misra-static-analysis-triage`** — A MISRA-C, MISRA C++, or comparable static-analysis gate fails in CI, when a pre-release compliance audit requires a clean or fully justified static-analysis…
- **`design-ota-bootloader-update-flow`** — A product is moving from factory-only programming to field-updatable firmware, when an existing over-the-air (OTA) update flow has shipped a bad build and…
- **`set-up-embedded-ci-with-hil-runner`** — A firmware repository builds and unit-tests on a host machine but has no automated pass/fail signal from real hardware, when hardware regressions are only…

</details>

<details>
<summary><b>API / Integrations</b> &middot; 6</summary>

- **`design-external-integration-with-vendor-quirks`** — Integrating with a new third-party API, SaaS platform, or partner system — before writing the client code.
- **`implement-webhook-consumer-with-idempotency`** — Building or hardening an endpoint that receives inbound webhooks from a vendor or partner system.
- &#9733; **`write-openapi-spec-and-contract-tests`** — Publishing a new public or partner-facing API, or changing an existing one, and the change needs a machine-readable contract plus automated proof that…
- **`design-api-versioning-and-deprecation-plan`** — A breaking change is needed on an API that already has consumers, or when planning how a public/partner API will version and sunset old behavior over time.
- **`build-data-mapping-transform-layer`** — Syncing or transforming data between two systems with mismatched schemas — a CRM, ERP, payment gateway, or any external system whose field names, types, or…
- &#9733; **`idempotency-and-retry-design`** — Any operation might be executed more than once for the same logical intent — a client retrying a timed-out request, a message queue redelivering, a backfill…

</details>

<details>
<summary><b>Software Architecture / Tech Lead</b> &middot; 4</summary>

- &#9733; **`adr-authoring`** — A significant, hard-to-reverse technical or architectural choice is being made — a new framework or dependency, a build-vs-buy call, a platform migration, a…
- **`design-service-boundary-and-api-contract`** — A new microservice or bounded context is being proposed, when an existing service is being split or merged, or when two systems need a boundary drawn between…
- **`plan-zero-downtime-migration`** — A large-scale schema, service, data-store, or platform migration needs to ship without a maintenance window — a table rename or column-type change on a live…
- **`run-architecture-review-checklist`** — Use before a new system, service, or major feature launches, or when a design needs a structured pre-launch review — triggers include "design review," "is…

</details>

<details>
<summary><b>DevOps</b> &middot; 3</summary>

- **`dockerfile-hardening`** — Writing a new Dockerfile or auditing an existing one for production readiness — a single-stage build that ships compilers and dev dependencies into the…
- **`gitops-deployment-setup`** — Moving a service's deployment from imperative `kubectl apply`/`helm upgrade` runs to a GitOps model, or when configuring Argo CD or Flux for a cluster — "move…
- **`ansible-playbook-authoring`** — A configuration-management task is expressed as "provision/configure these hosts" — installing packages, laying down config files, or managing services across…

</details>

<details>
<summary><b>CI/CD & Infrastructure-as-Code</b> &middot; 2</summary>

- &#9733; **`ci-pipeline-authoring`** — A repository has no CI pipeline, an existing pipeline is broken or too slow, or the task is phrased as "set up CI," "add a build/test/deploy pipeline," "wire…
- &#9733; **`terraform-module-authoring`** — Writing or reviewing a Terraform (or OpenTofu) module or root configuration — new infrastructure-as-code, a module missing standard variables/outputs/versions…

</details>

<details>
<summary><b>Site Reliability Engineering</b> &middot; 6</summary>

- **`slo-error-budget-definition`** — A service needs Service Level Indicators (SLIs) and a Service Level Objective (SLO) defined or reviewed — a launch review is missing a reliability target, an…
- &#9733; **`postmortem-generator`** — An incident, outage, or bad release has been resolved and a blameless postmortem needs to be written from a raw timeline, alert history, deploy log, and chat…
- **`runbook-authoring-from-incident`** — Tribal on-call knowledge needs to become a written runbook — "we keep hitting this, write it down," a postmortem action item calling for an operational…
- **`chaos-experiment-design`** — Resilience needs to be tested deliberately rather than discovered during an outage — "let's test what happens if X fails," a postmortem reveals an untested…
- **`observability-instrumentation`** — A service is missing monitoring, tracing, or alerting coverage — "add monitoring to this service," "we have no visibility into X," "set up dashboards and…
- &#9733; **`capacity-planning-forecast`** — A scaling review, a known load event (launch, seasonal peak, migration), or a "will this hold up" question needs a data-backed answer instead of a guess.

</details>

<details>
<summary><b>Platform Engineering</b> &middot; 5</summary>

- **`golden-path-template-authoring`** — Asked to create a paved-road, golden-path, or "starter template" for a new microservice, database, batch job, or frontend app, or when standing up a…
- **`backstage-catalog-entity-authoring`** — Registering a new service, API, library, resource, or system in a Backstage-style software catalog — writing or fixing a catalog-info.yaml, wiring ownership…
- **`kubernetes-security-hardening`** — Authoring or reviewing Kubernetes manifests, Helm charts, namespace/RBAC configuration, or a live cluster's security posture — setting up multi-tenant…
- **`self-service-iac-module-catalog`** — Building or extending a catalog of reusable Terraform, OpenTofu, or Crossplane modules that product teams provision from directly, without a platform-team…
- **`engineering-delivery-metrics`** — Asked to measure engineering or developer productivity — instrumenting DORA metrics (deployment frequency, lead time for changes, change failure rate, time to…

</details>

<details>
<summary><b>Cloud / Infrastructure</b> &middot; 5</summary>

- &#9733; **`well-architected-review`** — The task is "review our cloud architecture," an architecture-assessment deliverable is requested, a new workload needs a pre-launch architecture sign-off, or…
- **`vpc-network-topology-design`** — Designing or reviewing a cloud VPC/VNet — subnetting, CIDR-range planning, routing, NAT/internet-gateway placement, security-group versus network-ACL…
- **`iam-least-privilege-policy-authoring`** — Writing or reviewing IAM policies, roles, service accounts, or cross-account/cross-project trust relationships in a cloud environment.
- **`cloud-cost-optimization-audit`** — The task is "reduce our cloud bill," a recurring cost review is due, a cost-anomaly alert fires, or finance flags a spend spike with no matching workload…
- **`disaster-recovery-plan-authoring`** — Designing a disaster-recovery or backup strategy, defining RTO/RPO targets, or producing a failover runbook for a critical system.

</details>

<details>
<summary><b>Security</b> &middot; 5</summary>

- &#9733; **`threat-model-on-diff`** — A pull request, design document, or code diff touches authentication, authorization, data handling, a trust boundary, or an external integration and needs a…
- **`sast-dast-sca-pipeline-integration`** — Adding automated security scanning (SAST, DAST, or SCA/dependency scanning) to a CI/CD pipeline, closing a DevSecOps maturity gap, or tuning severity-based…
- &#9733; **`secrets-scanning-remediation`** — A secret (API key, password, private key, token) has leaked into a git repository, or when setting up proactive secret scanning as a pre-commit hook and CI…
- **`supply-chain-signing`** — Generating a software bill of materials (SBOM), hardening a release pipeline's artifact integrity, wiring build provenance and artifact signing, or meeting a…
- **`vulnerability-triage-and-disclosure`** — A CVE lands against a dependency in use, a vulnerability report arrives (from a scanner, a bug bounty, or an external researcher), or an internally discovered…

</details>

<details>
<summary><b>QA / SDET</b> &middot; 6</summary>

- **`e2e-test-suite-authoring`** — A critical user journey lacks browser-level coverage, a new feature slice ships without end-to-end tests, or the task is phrased as "write E2E tests for this…
- **`api-contract-test-authoring`** — A REST or GraphQL service needs automated proof that its actual behavior matches its published contract — schema-driven test generation from an…
- **`flaky-test-triage`** — A CI test suite shows intermittent, non-deterministic failures — a test that is red on one run and green on the next with no code change in between, a "just…
- **`load-performance-test-authoring`** — A service or endpoint needs load, stress, spike, or soak testing before launch, a capacity question needs empirical evidence rather than a guess, or the task…
- **`test-strategy-and-coverage-audit`** — A new project or feature needs a test plan before code is written, or an existing codebase needs an audit of what its test suite actually covers versus what…
- **`accessibility-test-audit`** — Accessibility testing needs to be wired into a QA process or a CI pipeline rather than run as a one-off pass — an automated axe-core scan added to the test…

</details>

<details>
<summary><b>Release / Build / Dev-Productivity</b> &middot; 4</summary>

- **`semantic-release-versioning`** — A repo needs automated version bumps, changelog generation, and tag/publish on merge — "set up semantic release," "automate our versioning," a request to stop…
- **`monorepo-build-optimization`** — Monorepo builds are slow, duplicated, or run the full suite on every change — "our CI takes forever," "we're rebuilding everything even for a one-line…
- **`progressive-delivery-rollout`** — A release needs to ship safely rather than all-at-once — "roll this out gradually," "set up a canary," "we need blue-green deploys," or a feature-flagged…
- **`ci-runner-capacity-and-queue-tuning`** — CI queue times are growing, jobs sit "waiting for a runner" for minutes before starting, or runner capacity needs planning ahead of a headcount or repo-count…

</details>

<details>
<summary><b>Data Engineering</b> &middot; 5</summary>

- **`airflow-dag-authoring`** — Building or modifying a scheduled data pipeline, DAG, or Airflow task graph — new DAG files, `dag_id` definitions, sensors, operators, retry/SLA…
- **`dbt-model-and-test-authoring`** — Adding or modifying a dbt model, source definition, or schema test — new staging/intermediate/mart SQL files, `schema.yml` edits, `sources.yml` wiring, or a…
- **`idempotent-backfill-authoring`** — Backfilling historical data, re-running a pipeline over a date range, reprocessing a large table, or fixing data corrupted by a prior bad run — any task…
- **`streaming-pipeline-scaffolding`** — Building a Kafka/Kinesis producer-consumer pair, a change-data-capture (CDC) pipeline, or any event-streaming feature — new topic/stream definitions,…
- &#9733; **`data-quality-check-suite`** — A new or changed pipeline, dataset, or dbt model needs validation coverage before merge or before downstream consumers trust it — requests like "add data…

</details>

<details>
<summary><b>Analytics Engineering & BI</b> &middot; 7</summary>

- **`semantic-layer-metric-definition`** — A business metric (revenue, active users, churn rate, conversion rate) needs a canonical, reusable definition in a semantic layer such as dbt Semantic…
- **`dbt-ci-cd-pipeline-setup`** — A dbt project needs continuous-integration checks on pull requests, a slim-CI job that only builds modified models, automated documentation generation, or a…
- **`sql-refactor-to-dbt-layering`** — A legacy monolithic SQL script, a sprawling view, or a copy-pasted query needs decomposition into a proper dbt staging/intermediate/mart model structure.
- **`ad-hoc-sql-analysis-to-insight`** — A stakeholder asks a one-off business question answerable by querying a warehouse or database — "how many users churned last quarter," "which region had the…
- **`dashboard-spec-to-buildout`** — A stakeholder ask needs to become a built dashboard in a BI tool — Power BI, Tableau, Looker Studio, or an equivalent — rather than a one-off answer.
- **`metrics-definition-reconciliation`** — Two reports, dashboards, or stakeholders disagree on what should be the same KPI number — "why does the revenue dashboard say 1.2M and finance says 1.4M for…
- **`executive-report-narrative-draft`** — A recurring leadership or board report needs a written narrative alongside its charts and tables — not just the numbers, but the "what happened and why it…

</details>

<details>
<summary><b>Database Administration</b> &middot; 6</summary>

- &#9733; **`explain-analyze-query-tuning`** — A specific SQL query is slow and needs diagnosis — a dashboard timing out, an API endpoint with a growing p95, a batch job that used to finish in minutes and…
- **`index-strategy-design`** — Recurring slow queries against a table point to a missing or wrong index, when someone asks "what index should I add here," or when a table needs an index…
- **`database-migration-safety-review`** — Use to review a proposed schema migration or DDL change against a live database before it ships — an autogenerated ORM migration diff, a hand-written ALTER…
- **`backup-recovery-runbook-authoring`** — A database needs a documented, tested backup-and-restore or disaster-recovery procedure — a new database with no runbook, an audit finding that backups have…
- &#9733; **`read-only-diagnostic-query-pack`** — Use to profile a database's health when only a read-only credential or role is available — no DDL, no DML, no write access at all.
- **`connection-pool-and-vacuum-tuning`** — A database shows connection exhaustion ("too many connections," "FATAL: sorry, too many clients already," pool-exhaustion errors under load) or table bloat…

</details>

<details>
<summary><b>Data Science</b> &middot; 4</summary>

- **`ab-test-design-and-power-analysis`** — A task asks to design, size, or pre-register an A/B test or online controlled experiment — choosing a randomization unit, computing a minimum detectable…
- **`causal-inference-analysis`** — A task asks whether a treatment or intervention caused an observed outcome using non-randomized, observational data — no A/B test was run, but a policy…
- **`exploratory-data-analysis-to-hypothesis`** — A new or unfamiliar tabular dataset needs profiling before it is trusted for modeling, reporting, or an experiment — checking nulls, distributions, outliers,…
- **`predictive-model-baseline-to-iterate`** — A task asks for a first predictive model — classification or regression — on tabular data, or when an existing model needs a proper baseline comparison,…

</details>

<details>
<summary><b>Machine Learning Engineering</b> &middot; 4</summary>

- **`feature-engineering-pipeline`** — A task asks to build, extend, or debug a reusable feature set for a machine-learning model — turning raw or warehouse data into point-in-time-correct model…
- **`model-training-experiment-scaffold`** — A task asks to stand up or extend a model-training run with experiment tracking — scaffolding a training script wired to MLflow or Weights & Biases,…
- **`model-packaging-and-serving`** — A trained model needs to go behind an API, a batch job, or a streaming consumer — choosing batch vs.
- &#9733; **`eval-harness`** — A machine-learning model or a GenAI feature (RAG, agent, chat, prompt) needs a repeatable, automated evaluation before it ships or before a change to it merges.

</details>

<details>
<summary><b>MLOps / ML Platform</b> &middot; 5</summary>

- **`mlops-ci-cd-pipeline-setup`** — A repository needs continuous integration and deployment wired specifically for a trained-model artifact rather than an application binary — task phrasings…
- **`model-registry-and-versioning-setup`** — A project trains models with no central place to track which version is deployed where — task phrasings like "we don't have a model registry," "set up…
- **`model-drift-monitoring-setup`** — A model is already in production with no monitoring for accuracy degradation — task phrasings like "add drift monitoring to our production model," "the…
- **`feature-store-operationalization`** — Multiple models need the same engineered features computed consistently, or when a model's online (serving-time) predictions do not match its offline…
- **`ml-platform-iac-provisioning`** — A platform team needs infrastructure-as-code for shared ML infrastructure — a model registry, an experiment-tracking server, a serving cluster, or a feature…

</details>

<details>
<summary><b>AI / GenAI / LLM</b> &middot; 4</summary>

- **`rag-pipeline-scaffolding`** — A task asks to build, tune, or debug a retrieval-augmented-generation (RAG) feature — "answer questions over our docs," "add a knowledge base to the chatbot,"…
- **`prompt-regression-testing`** — An existing prompt, system message, or model version is about to change — "tighten up this system prompt," "we're switching models," "add a new instruction to…
- **`llm-cost-latency-optimization`** — A GenAI feature is too slow or too expensive in production — "the chatbot takes 8 seconds to respond," "our token spend doubled last month," "reduce API cost…
- **`agent-tool-use-design`** — A task asks to design an agent that calls tools, functions, or external APIs autonomously — "give the assistant a tool to look up orders," "build an agent…

</details>

<details>
<summary><b>Engineering Management</b> &middot; 2</summary>

- **`perf-review-drafting`** — A manager needs to draft a written performance review, self-review response, or calibration packet from a competency ladder plus a set of accomplishment…
- **`one-on-one-notes-synthesizer`** — A manager has raw 1:1 (one-on-one) notes or transcripts accumulated across weeks or a full review cycle and needs them synthesized into themes before the next…

</details>

<details>
<summary><b>Engineering Leadership (Director / VP / CTO)</b> &middot; 3</summary>

- **`build-vs-buy-memo`** — A team is deciding whether to build a capability in-house or buy/license a vendor, SaaS, or open-source solution — a new logging platform, an internal tool…
- **`career-ladder-calibration`** — Defining or updating an engineering career ladder or competency framework, or when a promotion packet needs to be checked against an existing ladder before a…
- **`tech-radar-update`** — A periodic (commonly quarterly) technology-radar refresh is due, or when a new tool, library, or platform needs to be classified into Adopt, Trial, Assess, or…

</details>

<details>
<summary><b>Developer Relations</b> &middot; 4</summary>

- **`quickstart-tutorial-generator`** — A new API endpoint, SDK method, or product feature ships and needs a learning-oriented "getting started" tutorial with a runnable code sample.
- **`sample-app-health-check`** — Use for a periodic audit of public sample apps, code snippets, or quickstart repos against the current API/SDK version — running each sample, flagging…
- **`community-feedback-digest`** — Use for producing a weekly or monthly digest of developer-forum, GitHub-issue, Discord, or Stack Overflow themes for product and engineering.
- &#9733; **`changelog-from-git-range`** — A release ships and needs developer-facing release notes distinct from the internal engineering changelog — turning a git commit range or conventional-commit…

</details>

<details>
<summary><b>Solutions / Sales Engineering</b> &middot; 4</summary>

- &#9733; **`rfp-response-drafter`** — An inbound RFP, security questionnaire, or vendor-due-diligence form arrives that mixes boilerplate compliance questions with deal-specific technical ones.
- **`poc-scoping-doc`** — A prospect has greenlit a proof-of-concept or pilot and needs a scoping document before the trial's engineering work starts.
- **`customer-architecture-diagram`** — A solutions architect or solutions engineer needs a target-state architecture diagram for a customer's environment or integration — showing the customer's…
- **`discovery-call-question-bank`** — Preparing for a discovery call with a new prospect, especially in an unfamiliar vertical or use case, and a tailored set of questions is needed to surface the…

</details>

<details>
<summary><b>Technical Writing / Docs</b> &middot; 4</summary>

- &#9733; **`docs-diataxis-authoring`** — A new feature, API, or product surface needs documentation and it is unclear whether the result should be a tutorial, a how-to guide, a reference page, or an…
- **`openapi-reference-generator`** — An OpenAPI/Swagger spec has changed and the published API reference docs need regenerating, or when a REST API has no reference documentation yet and one…
- &#9733; **`prose-style-lint`** — Use before publishing any client-facing or user-facing prose a program or agent generated — documentation, release notes, report narratives, UI copy, error…
- **`content-staleness-audit`** — Use for a periodic documentation-health sweep — finding dead links, version-drifted instructions, screenshots or code samples that no longer match the current…

</details>

<details>
<summary><b>Technical Support</b> &middot; 4</summary>

- **`ticket-triage-classifier`** — A new inbound support ticket needs categorization, severity, and product-area tagging before it reaches an engineer's queue.
- &#9733; **`known-issue-matcher`** — An incoming support ticket's symptoms need to be checked against a known-issues list, knowledge base, or history of resolved tickets before triage or reply.
- **`bug-report-escalation-writer`** — A support ticket is confirmed as a genuine product bug and needs to go to engineering as a structured report rather than a forwarded conversation thread.
- **`kb-article-from-resolved-ticket`** — A non-trivial support ticket has been resolved and the resolution pattern is likely to recur for other customers.

</details>

<!-- END SKILL CATALOG -->

## The Resource Loop in 60 seconds

The Resource Loop is a closed, self-learning loop that runs for every task:
before Claude starts, it checks what resources already exist so it reaches for
them instead of rebuilding them — and after the work is done, it measures the
result and acts on what it learns.

A SessionStart hook injects a compact **registry index** into the session. The
`resource-loop` skill then runs six steps:

1. **MATCH** — compare your task against the registry (by task shape, not just
   keywords).
2. **ANNOUNCE** — state, in one line, which resource it is deploying, or that
   there was no match and it is proceeding bare. (When a recurring need has no
   resource, it files a candidate stub for review — it never auto-creates one.)
3. **ROUTE** — dispatch subagents at the right model tier: planning at the
   session model, creation-heavy work to Opus, and mechanical work to Sonnet
   (or Haiku for trivial probes).
4. **EXECUTE** — do the work while three hooks passively harvest objective
   metrics (tokens, cache efficiency, tool errors, tests, duration).
5. **SCORE** — record a short subjective self-score of the outcome.
6. **LEARN** — evaluate a rulebook of heuristics over the metric history and act
   on what fired: improve a resource now, note a cross-task theme, or do nothing
   — logging the decision either way.

Underneath those steps sit the learning layers: a local-only **metrics** store,
ordinal **scoring** scales, a cross-task **theme** log, a **heuristics** rulebook,
and a gated **autonomy** path that commits the loop's own improvements under a
hard safety floor. All of it is explained in **`LEARNING.md`**; the full
mechanics are in `ARCHITECTURE.md`.

The payoff: less duplicated work, a visible announcement of what is in play, a
growing catalog of reusable resources, and a system that measures whether its
own choices worked.

## Making it yours

This bundle ships generic. The `environment-bootstrap` skill is what turns it
into *your* setup: it inspects your OS, editor, languages, cloud CLIs, and
database clients; interviews you about what you build and which databases you
touch; then tailors the registry (pruning what you don't need, enabling what
you do), appends a personalized block to your `CLAUDE.md`, and fills in the
database/MCP templates with your own connection details. Run it once after
install, and again any time your setup changes.

The bundle is DBA-friendly out of the box — a read-only SQL safety reviewer, a
read-only Postgres/MySQL MCP template, and an SSH-tunnel keepalive are
included — but none of it is required if that is not your work; the
interview simply skips or prunes what does not apply.

## Documentation in this folder

- **`README.md`** (this file) — what it is and how to start.
- **`INSTALL.md`** — the manual, step-by-step fallback, plus exactly what the
  installer changes and how to undo it.
- **`ARCHITECTURE.md`** — the component diagram, the three layers, the resource
  categories, the metrics store contract, the autonomy mechanics, and the
  model-routing table.
- **`LEARNING.md`** — the self-learning layer: what "learning" means here,
  objective metrics, subjective scores, themes, heuristics, and the gated
  autonomy path.
- **`SECURITY.md`** — what the installer will and will not touch, the secrets/PII
  posture, and the autonomy residual risks.
