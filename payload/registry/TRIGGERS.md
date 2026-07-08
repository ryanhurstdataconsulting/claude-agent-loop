# Resource Triggers — keyword / file-glob → resource map
<!-- MATCH accelerator for the resource-loop skill. Scan this first, then confirm
     with a semantic read of the task. Rows map a trigger (keyword, phrase, or
     file glob) to one or more registry resource names. -->
<!-- This is a shortcut index, NOT the registry: the lint_registry.py linter
     scans REGISTRY.md + guides/ only, so rows here need no matching guide. A few
     targets are harness-native (superpowers skills, VoltAgent agent types)
     rather than REGISTRY rows; those are marked. Keep this scannable. -->
<!-- Run environment-bootstrap to tailor these rows to your own stack. -->

## Machine-global gates (fire on the trigger, every project)

| Trigger (keyword / phrase / glob) | Route to |
|---|---|
| before commit · leak · secret · password · JWT · PII · handoff bundle · staged files | secret-pii-scrub-gate |
| grammar · user-facing copy · report narrative · UI copy · a/an · its/it's · machine-generated prose | machine-prose-grammar-gate |
| session start · new project · before a non-trivial git op · unpushed commits · `.git` eviction | git-safety-preflight |
| session start on a Python/build project · which interpreter · venv · missing tool | env-tooling-preflight |
| after ANY registry edit · REGISTRY.md · guides/ change | lint-registry |
| first run · set me up · new machine · new database or cloud account · reconfigure | environment-bootstrap |

## Databases & remote access

| Trigger | Route to |
|---|---|
| before a prod query · SQL against a production DB · read-only wrapper · statement timeout · no DDL/DML | sql-safety-reviewer |
| Postgres/MySQL query · schema question · localhost tunnel · read-only connection | postgres-readonly (mcp) |
| SSH tunnel keepalive · long DB session · "connection refused" after idle · bastion idle-timeout | ssh-tunnel-keepalive |

## Data viz, charts, dashboards, reports

| Trigger | Route to |
|---|---|
| chart · dashboard · graph · plot · viz · analytics · report · ranking | data-visualization, visual-hierarchy-layered-charts |
| "make it pop" · highlight one series · dim vs. desaturate · focus/reference/selection tiers | visual-hierarchy-layered-charts |

## Rendering & documents

| Trigger | Route to |
|---|---|
| render · PDF · pptx · docx · deck · slides · weasyprint · pandoc · mojibake · smart-quote garble | document-render |
| architecture diagram · data-flow diagram · onboarding map · `*.excalidraw` | excalidraw-diagram |
| explain how this works · walk me through the code · teach this module | explain-code |

## Cloud & infrastructure

| Trigger | Route to |
|---|---|
| AWS · Terraform · S3 · IAM · cloud architecture · Well-Architected review | cloud-architect |
| local AWS emulation · LocalStack · "test the pipeline before we ship" against real credentials | aws-local-emulation (skill) |
| long-running build to poll · tail a log for success/fail · notify once | background-build-watch |
| "spin it up" · "let me test" · bring the dev stack up/down with a health gate | dev-server-orchestration |

## Desktop & meta

| Trigger | Route to |
|---|---|
| Tauri · Tauri 2 · desktop app · sidecar · PyInstaller sidecar · packaged-app fetch fails · Gatekeeper | tauri-desktop-dev |
| 2+ independent subtasks · multi-file sweep · fan out parallel agents (same session) | subagent-driven-development (superpower), dispatching-parallel-agents (superpower) |
| keep it cheap · token budget · long/high-volume task · big file sweep · many parallel agents · minimize context · run past compaction | token-efficiency |
| coverage check · does every session announce the loop · CLAUDE.md/SUBAGENTS.md present | check-coverage, run-canaries |
| redact session JSONL · extract user/assistant text from transcripts | distill-transcripts |

## Skill library (role-based) — MATCH shortcuts

<!-- The full 157-skill library is indexed in skills/CATALOG.md (grouped by
     family). The rows below are MATCH shortcuts for common task shapes; for
     anything not listed, grep CATALOG.md by family or invoke the skill by name —
     every library skill is also surfaced natively by the harness. -->

### Product, program & research
| Trigger | Route to |
|---|---|
| write a PRD · product spec · requirements doc · turn a feature brief into a spec | write-a-prd |
| prioritize a backlog · RICE · roadmap · now/next/later · OKRs · competitive teardown | prioritize-with-rice, build-a-roadmap, draft-okrs, run-competitive-analysis |
| RAID log · risks/assumptions/issues/dependencies · status report · sprint plan · dependency map · RACI | raid-log-maintainer, status-report, sprint-plan-from-spec, map-dependencies, run-raci-assignment |
| user research plan · interview guide · screener · affinity mapping · survey design · research repository | write-a-research-plan, draft-discussion-guide-and-screener, synthesize-with-affinity-mapping, design-a-survey, maintain-research-repository |

### Design (UX / UI / design systems)
| Trigger | Route to |
|---|---|
| design sprint · design critique · JTBD · prototype plan · heuristic evaluation · user journey · IA/sitemap | run-a-design-sprint, structure-design-critique, write-jtbd-statements, build-a-prototype-plan, run-heuristic-evaluation, map-user-journey, build-ia-sitemap |
| accessibility · WCAG · contrast ratio · keyboard/focus/ARIA · a11y audit | accessibility-audit, accessibility-test-audit, add-accessibility-audit-fixes |
| design tokens · type scale · visual consistency · Storybook docs · contribution model · component changelog · design-ops tooling | design-tokens, build-a-type-scale, audit-visual-consistency, audit-storybook-documentation, draft-contribution-model, generate-component-changelog, design-ops-tooling-audit |

### Application engineering (frontend / backend / full-stack / mobile / embedded / API)
| Trigger | Route to |
|---|---|
| new React/UI component · Core Web Vitals · JS→TS migration · design-system migration · typed REST client | scaffold-react-component-with-tests, audit-core-web-vitals, convert-js-to-typescript, migrate-component-to-design-system, integrate-rest-api-client |
| new REST endpoint · DB migration + rollback · caching layer · authn/authz · containerize · structured logging/tracing | scaffold-rest-endpoint-with-tests, write-database-migration-with-rollback, add-caching-layer, implement-authn-authz, containerize-service-for-deployment, add-structured-logging-and-tracing |
| full feature slice end-to-end · slow request across the stack · unit tests with a coverage target | scaffold-full-feature-slice, profile-and-fix-slow-request, write-unit-tests-with-coverage-target |
| mobile screen/ViewModel · Fastlane release · crash reporting · offline sync · app-store review compliance | scaffold-mobile-screen-with-viewmodel, set-up-fastlane-release-pipeline, integrate-crash-reporting-and-monitoring, implement-offline-first-sync, audit-app-store-review-compliance |
| firmware/peripheral driver · RTOS task/IPC · MISRA triage · OTA bootloader · embedded CI/HIL | write-peripheral-driver-with-hil-test, design-rtos-task-and-ipc, run-misra-static-analysis-triage, design-ota-bootloader-update-flow, set-up-embedded-ci-with-hil-runner |
| webhook consumer · idempotency/retry · OpenAPI + contract tests · API versioning/deprecation · data mapping · third-party vendor integration | implement-webhook-consumer-with-idempotency, idempotency-and-retry-design, write-openapi-spec-and-contract-tests, design-api-versioning-and-deprecation-plan, build-data-mapping-transform-layer, design-external-integration-with-vendor-quirks |

### Architecture & technical leadership
| Trigger | Route to |
|---|---|
| ADR · architecture decision · hard-to-reverse choice · service boundary · zero-downtime migration plan · architecture review | adr-authoring, design-service-boundary-and-api-contract, plan-zero-downtime-migration, run-architecture-review-checklist |
| build-vs-buy memo · career ladder/levels · tech radar · performance review · 1:1 synthesis | build-vs-buy-memo, career-ladder-calibration, tech-radar-update, perf-review-drafting, one-on-one-notes-synthesizer |

### Infra, reliability & security
| Trigger | Route to |
|---|---|
| set up CI · build/test/deploy pipeline · Terraform module · Dockerfile hardening · GitOps · Ansible playbook | ci-pipeline-authoring, terraform-module-authoring, dockerfile-hardening, gitops-deployment-setup, ansible-playbook-authoring |
| SLO/error budget · postmortem · runbook · chaos experiment · observability/instrumentation · capacity planning | slo-error-budget-definition, postmortem-generator, runbook-authoring-from-incident, chaos-experiment-design, observability-instrumentation, capacity-planning-forecast |
| golden path/IDP · Backstage catalog · Kubernetes hardening · self-service IaC · DORA/SPACE/DevEx metrics | golden-path-template-authoring, backstage-catalog-entity-authoring, kubernetes-security-hardening, self-service-iac-module-catalog, engineering-delivery-metrics |
| Well-Architected review · VPC/network topology · IAM least privilege · cloud cost · disaster recovery/RTO-RPO | well-architected-review, vpc-network-topology-design, iam-least-privilege-policy-authoring, cloud-cost-optimization-audit, disaster-recovery-plan-authoring |
| threat model · SAST/DAST/SCA · secrets scanning/remediation · SBOM/SLSA/signing · vulnerability triage/CVSS | threat-model-on-diff, sast-dast-sca-pipeline-integration, secrets-scanning-remediation, supply-chain-signing, vulnerability-triage-and-disclosure |
| E2E/Playwright tests · API contract tests · flaky-test triage · load/perf test · test strategy/coverage · a11y test | e2e-test-suite-authoring, api-contract-test-authoring, flaky-test-triage, load-performance-test-authoring, test-strategy-and-coverage-audit, accessibility-test-audit |
| semantic-release/versioning · monorepo build · progressive delivery/canary · CI runner capacity | semantic-release-versioning, monorepo-build-optimization, progressive-delivery-rollout, ci-runner-capacity-and-queue-tuning |

### Data, analytics & database
| Trigger | Route to |
|---|---|
| Airflow DAG · dbt model/tests · idempotent backfill · streaming/Kafka/CDC · data quality checks | airflow-dag-authoring, dbt-model-and-test-authoring, idempotent-backfill-authoring, streaming-pipeline-scaffolding, data-quality-check-suite |
| semantic layer/metric definition · dbt CI/CD · SQL→dbt refactor · ad-hoc SQL insight · BI dashboard · metric reconciliation · exec report narrative | semantic-layer-metric-definition, dbt-ci-cd-pipeline-setup, sql-refactor-to-dbt-layering, ad-hoc-sql-analysis-to-insight, dashboard-spec-to-buildout, metrics-definition-reconciliation, executive-report-narrative-draft |
| slow query · EXPLAIN ANALYZE · index strategy · read-only diagnostics · vacuum/bloat/pgBouncer · backup/recovery · migration safety review | explain-analyze-query-tuning, index-strategy-design, read-only-diagnostic-query-pack, connection-pool-and-vacuum-tuning, backup-recovery-runbook-authoring, database-migration-safety-review |

### Data science, ML & AI
| Trigger | Route to |
|---|---|
| A/B test/power analysis · causal inference · EDA→hypothesis · baseline predictive model | ab-test-design-and-power-analysis, causal-inference-analysis, exploratory-data-analysis-to-hypothesis, predictive-model-baseline-to-iterate |
| feature engineering/store · training + experiment tracking · model packaging/serving · eval harness | feature-engineering-pipeline, feature-store-operationalization, model-training-experiment-scaffold, model-packaging-and-serving, eval-harness |
| MLOps CI/CD · model registry/versioning · drift monitoring · ML platform IaC | mlops-ci-cd-pipeline-setup, model-registry-and-versioning-setup, model-drift-monitoring-setup, ml-platform-iac-provisioning |
| RAG pipeline · prompt regression testing · LLM cost/latency · agent/tool-use design | rag-pipeline-scaffolding, prompt-regression-testing, llm-cost-latency-optimization, agent-tool-use-design |

### Docs, DevRel, support & solutions
| Trigger | Route to |
|---|---|
| Diátaxis docs · OpenAPI reference · prose/style lint · content staleness · changelog from a git range | docs-diataxis-authoring, openapi-reference-generator, prose-style-lint, content-staleness-audit, changelog-from-git-range |
| quickstart/tutorial · sample-app health check · community feedback digest | quickstart-tutorial-generator, sample-app-health-check, community-feedback-digest |
| ticket triage · known-issue match · bug-report escalation · KB article from a resolved ticket | ticket-triage-classifier, known-issue-matcher, bug-report-escalation-writer, kb-article-from-resolved-ticket |
| RFP/security questionnaire · PoC scoping · customer architecture diagram · discovery-call questions | rfp-response-drafter, poc-scoping-doc, customer-architecture-diagram, discovery-call-question-bank |
