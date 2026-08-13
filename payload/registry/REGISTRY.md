# Agent Resource Registry — compact index
<!-- Format: | name | category | domain | trigger | · one resource per line · budget 150 rows -->
<!-- domain ∈ core-dev, language, infra, quality-security, data-ai, dev-experience,
     specialized-domains, business-product, meta-orchestration, research-analysis -->
<!-- Lint after ANY edit: python3 ~/.claude/tools/lint_registry.py -->
<!-- Full guides: registry/guides/<name>.md · Proposals: registry/candidates/ -->
<!-- Plugin-provided skills (superpowers, VoltAgent catalog, …) are surfaced
     natively by the harness and are NOT re-indexed here. Run the
     environment-bootstrap skill once to tailor this registry to your machine. -->

## Superpowers (process)
| resource-loop | superpower | meta-orchestration | Start of every session: MATCH → ANNOUNCE → ROUTE → EXECUTE → SCORE → LEARN |
| token-efficiency | superpower | meta-orchestration | Long/high-volume/multi-file task or a subagent fleet — targeted reads, file-handoff, model/effort routing; never at the cost of evidence |

## Skills (domain)
| environment-bootstrap | skill | dev-experience | First run / reconfigure — inspect the machine, interview the user, and tailor this whole config |
| data-visualization | skill | data-ai | Chart selection, dashboard design, data storytelling |
| visual-hierarchy-layered-charts | skill | data-ai | Multi-series charts with importance tiers; focus/dim and "make it pop" decisions |
| explain-code | skill | dev-experience | Explaining how code works, with diagrams and analogies |
| excalidraw-diagram | skill | dev-experience | Architecture, data-flow, and onboarding diagrams as Excalidraw JSON |
| document-render | skill | dev-experience | Rendering any markdown deliverable to PDF, or a generated .pptx/.docx deck to PDF/images for QA (pandoc+weasyprint + headless-LibreOffice) |
| tauri-desktop-dev | skill | core-dev | Building/debugging a Tauri 2 desktop app or packaging a Python/FastAPI backend as a Tauri sidecar |
| skill-library | skill | meta-orchestration | Role-based skill library — 157 generic skills across 33 tech-org families (product → DB → ML/AI → UI). Browse skills/CATALOG.md, then invoke a specific skill by name |

## Agents
| sql-safety-reviewer | agent | quality-security | Dispatch before every production-database query — SAFE / NOT SAFE verdict (read-only wrapper present, no DDL/DML) |
| cloud-architect | agent | infra | AWS/Terraform/IAM provisioning or cloud-architecture assessment (Well-Architected review) |
| role-agents | agent | meta-orchestration | Serve as a company role — the router (route_role.py) picks the role agent (data-scientist, data-engineer, dba, cloud-architect, product-manager, …) whose skills/MCPs fit the task |

## MCPs
| postgres-readonly | mcp | data-ai | Live read-only SQL to a Postgres/MySQL database (localhost tunnel or direct) — fill in your host |
| playwright | mcp | quality-security | Browser automation, testing, and screenshots |
| google_workspace | mcp | business-product | Drive, Sheets, Docs, and Forms operations |

## Tools
| distill-transcripts | tool | dev-experience | Extract redacted user/assistant text from session JSONLs (~/.claude/tools/) |
| lint-registry | tool | meta-orchestration | Validate registry index ↔ guides after any registry edit |
| lint-roles | tool | meta-orchestration | Validate role-agent files after any agents/roles edit — frontmatter shape, skill existence, MCP bijection |
| route-role | tool | meta-orchestration | The deterministic task → role hop at MATCH — prints the Role — line with the role's skills and MCPs |
| plan-task | tool | meta-orchestration | DECOMPOSE/ASSIGN/BRIEF/RECORD — build a plan, route and brief each step, record each subagent's structured return |
| loop-contribute | tool | meta-orchestration | The feedback loop — gate-cleared (GENERIC-only) local resources auto-push to a contrib/* branch with an impact summary; --nudge at SessionStart |
| run-canaries | tool | quality-security | Full-coverage probe: does each project's session announce the loop? |
| check-coverage | tool | quality-security | Static check: CLAUDE.md stub + SUBAGENTS.md present across your projects |
| git-safety-preflight | tool | dev-experience | Session start / before non-trivial git ops — detect file-sync `.git` eviction, clobbered venv symlink, missing remote, unpushed commits, not-a-repo |
| machine-prose-grammar-gate | tool | quality-security | Before shipping ANY machine-generated user-facing prose — number-aware a/an, pluralization, subject-verb, its/it's |
| secret-pii-scrub-gate | tool | quality-security | Before any commit, handoff bundle, or deliverable — scan staged files for JWTs, passwords, SSH-key headers, emails, /Users/<name> paths, PII |
| env-tooling-preflight | tool | dev-experience | Session start on a Python/build project — interpreter/venv version, required-tool presence, macOS bash-3.2 portability |
| background-build-watch | tool | dev-experience | Any long-running build the agent must poll — tail a log for success/fail, notify once, no manual re-arm |
| ssh-tunnel-keepalive | tool | infra | Any remote-DB or SSH-tunnel session spanning multiple turns or >30 min — keepalive + auto-reconnect on idle drop |
| dev-server-orchestration | tool | dev-experience | "Spin it up" / "let me test" — one command brings the project's dev stack up/down with a health gate |
| audit-store | tool | quality-security | Ensure/verify/commit the repo-audit output store — a nested git repo under `~/.claude/metrics/audit`, no remote, ever |
| audit-dispatch | tool | quality-security | Nightly repo-security sweep: pick the due packages (interval elapsed AND HEAD moved), run each one, close with a digest |
| audit-run | tool | quality-security | Run one unattended repo-security audit — throwaway worktree, safety gates, commit to `audit/security-<date>`, never pushes |
| audit-digest | tool | quality-security | Severity-gated repo-audit alerts (Critical/High interrupt now) plus the batched digest and its SessionStart nudge |
| repo-audit-action | tool | quality-security | Per-change security audit in GitHub Actions — the four categories a checkout can answer, with the two it cannot stated on every run |
| bb-write | tool | meta-orchestration | Write a stamped row (task_id/phase/agent_id/ts/sha256) to the blackboard — shared_state, events, consensus_state, workflow_state, or artifacts |
| bb-read | tool | meta-orchestration | Read blackboard rows back, filtered by task_id (or artifact_id for the artifacts table) |
| bb-gc | tool | meta-orchestration | Nightly blackboard retention trim — 30-day shared_state/artifacts, 90-day events; consensus_state/workflow_state kept indefinitely |
| worktree-exec | tool | meta-orchestration | Create/merge a per-step git worktree for an EXECUTE step marked "worktree": true — merge refuses until the step's own return.ok is true |
| consensus-vote | tool | quality-security | Record/tally a 2-of-3 consensus vote (git-push, publish-release, aws-mutation) on the blackboard — an audit-log addition, not an enforcement gate |
