# Guide — productionization

**Category:** skill
**Scope:** machine-global, invoked per-project
**Status:** active — guided mode validated end-to-end against a real
three-service monorepo

## Why this exists (evidence)
Claude-assisted project repos mix heavy agent artifacts
(plans, specs, scratch notes) with application code and have no
repeatable path to a clean, independently deployable package. Source: a "Productionization Agent Guiding Document" written at
enterprise scale, right-sized during design for small teams and solo
maintainers.

## When to deploy (triggers)
Any request to prepare, package, or "productionize" a project for
cloud deployment. Also relevant when a project's `SECURITY_AUDIT.md`
(from a static security audit) or a stakeholder conversation raises "is this
ready to deploy" as a real question.

## Interface (how to invoke)
`Skill(productionization)` in the main session. Guided mode (default)
runs 7 phases sequentially, each dispatching one existing subagent via
the Agent tool, reviewed before the next starts. Full-send mode (opt-in,
requires the user's explicit ask or an Ultracode-style standing
directive) builds a Workflow script that pipelines the phases instead.

## Composition (pairs with / hands off to)
Dispatches, unmodified: `Explore`, `software-architect`,
`backend-engineer`, `frontend-engineer`, `technical-writer`,
`voltagent-dev-exp:refactoring-specialist`, `cloud-architect`,
`devops-engineer`, `repo-security-auditor`, `security-engineer`,
`qa-engineer`, `sre`. `repo-security-auditor`'s existing brief and the
`repo-security-audit` skill are unchanged by this work — this skill
reuses `repo-security-auditor` for its Security phase's static-scan
portion rather than duplicating that logic.

## Build & maintenance notes
v1 explicitly excludes DAST (any tier), SLSA/provenance + OPA/
CloudFormation Guard, and canary/blue-green releases — see SKILL.md's
"Future work" section for what each deferral means and when to
reconsider it.
