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
