# Agent Resource Registry — compact index
<!-- Format: | name | category | trigger | · one resource per line · budget 150 rows -->
<!-- Lint after ANY edit: python3 ~/.claude/tools/lint_registry.py -->
<!-- Full guides: registry/guides/<name>.md · Proposals: registry/candidates/ -->
<!-- Plugin-provided skills (superpowers, VoltAgent catalog, …) are surfaced
     natively by the harness and are NOT re-indexed here. Run the
     environment-bootstrap skill once to tailor this registry to your machine. -->

## Superpowers (process)
| resource-loop | superpower | Start of every session: MATCH → ANNOUNCE → ROUTE → EXECUTE → SCORE → LEARN |
| token-efficiency | superpower | Long/high-volume/multi-file task or a subagent fleet — targeted reads, file-handoff, model/effort routing; never at the cost of evidence |

## Skills (domain)
| environment-bootstrap | skill | First run / reconfigure — inspect the machine, interview the user, and tailor this whole config |
| data-visualization | skill | Chart selection, dashboard design, data storytelling |
| visual-hierarchy-layered-charts | skill | Multi-series charts with importance tiers; focus/dim and "make it pop" decisions |
| explain-code | skill | Explaining how code works, with diagrams and analogies |
| excalidraw-diagram | skill | Architecture, data-flow, and onboarding diagrams as Excalidraw JSON |
| document-render | skill | Rendering any markdown deliverable to PDF, or a generated .pptx/.docx deck to PDF/images for QA (pandoc+weasyprint + headless-LibreOffice) |
| tauri-desktop-dev | skill | Building/debugging a Tauri 2 desktop app or packaging a Python/FastAPI backend as a Tauri sidecar |
| skill-library | skill | Role-based skill library — 157 generic skills across 33 tech-org families (product → DB → ML/AI → UI). Browse skills/CATALOG.md, then invoke a specific skill by name |

## Agents
| sql-safety-reviewer | agent | Dispatch before every production-database query — SAFE / NOT SAFE verdict (read-only wrapper present, no DDL/DML) |
| cloud-architect | agent | AWS/Terraform/IAM provisioning or cloud-architecture assessment (Well-Architected review) |
| role-agents | agent | Serve as a company role — the router (route_role.py) picks the role agent (data-scientist, data-engineer, dba, cloud-architect, product-manager, …) whose skills/MCPs fit the task |

## MCPs
| postgres-readonly | mcp | Live read-only SQL to a Postgres/MySQL database (localhost tunnel or direct) — fill in your host |
| playwright | mcp | Browser automation, testing, and screenshots |
| google_workspace | mcp | Drive, Sheets, Docs, and Forms operations |

## Tools
| distill-transcripts | tool | Extract redacted user/assistant text from session JSONLs (~/.claude/tools/) |
| lint-registry | tool | Validate registry index ↔ guides after any registry edit |
| lint-roles | tool | Validate role-agent files after any agents/roles edit — frontmatter shape, skill existence, MCP bijection |
| route-role | tool | The deterministic task → role hop at MATCH — prints the Role — line with the role's skills and MCPs |
| plan-task | tool | DECOMPOSE/ASSIGN/LOG — build the work order, route each PART independently, record each subagent's structured return; refuses a creative task until brainstorming + writing-plans have run |
| make-brief | tool | BRIEF — render the dispatchable subagent prompt for one part, carrying its ids, skill shortlist, and required return schema |
| assess-task | tool | ASSESS — objective clean/dirty/unknown verdict per part from tests, tool errors, commits, and reverts; no model judgment |
| loop-contribute | tool | The feedback loop — gate-cleared (GENERIC-only) local resources auto-push to a contrib/* branch with an impact summary; --nudge at SessionStart |
| run-canaries | tool | Full-coverage probe: does each project's session announce the loop? |
| check-coverage | tool | Static check: CLAUDE.md stub + SUBAGENTS.md present across your projects |
| git-safety-preflight | tool | Session start / before non-trivial git ops — detect file-sync `.git` eviction, clobbered venv symlink, missing remote, unpushed commits, not-a-repo |
| machine-prose-grammar-gate | tool | Before shipping ANY machine-generated user-facing prose — number-aware a/an, pluralization, subject-verb, its/it's |
| secret-pii-scrub-gate | tool | Before any commit, handoff bundle, or deliverable — scan staged files for JWTs, passwords, SSH-key headers, emails, /Users/<name> paths, PII |
| env-tooling-preflight | tool | Session start on a Python/build project — interpreter/venv version, required-tool presence, macOS bash-3.2 portability |
| background-build-watch | tool | Any long-running build the agent must poll — tail a log for success/fail, notify once, no manual re-arm |
| ssh-tunnel-keepalive | tool | Any remote-DB or SSH-tunnel session spanning multiple turns or >30 min — keepalive + auto-reconnect on idle drop |
| dev-server-orchestration | tool | "Spin it up" / "let me test" — one command brings the project's dev stack up/down with a health gate |
| audit-store | tool | Ensure/verify/commit the repo-audit output store — a nested git repo under `~/.claude/metrics/audit`, no remote, ever |
| audit-dispatch | tool | Nightly repo-security sweep: pick the due packages (interval elapsed AND HEAD moved), run each one, close with a digest |
| audit-run | tool | Run one unattended repo-security audit — throwaway worktree, safety gates, commit to `audit/security-<date>`, never pushes |
| audit-digest | tool | Severity-gated repo-audit alerts (Critical/High interrupt now) plus the batched digest and its SessionStart nudge |
| repo-audit-action | tool | Per-change security audit in GitHub Actions — the four categories a checkout can answer, with the two it cannot stated on every run |
