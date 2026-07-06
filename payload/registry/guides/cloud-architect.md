# Guide — cloud-architect

**Category:** agent
**Scope:** per-project (adopt into whichever project needs it)
**Status:** active

## Why this exists (evidence)
Weeks of Terraform/IAM work and recurring cloud-architecture assessments were
being written inline in the main thread, with a read-only command battery
retyped from scratch in more than one session. This pattern recurred across
multiple projects. Agent determination: **ADOPT.** A grep confirms
`03-infrastructure/cloud-architect.md` exists in the VoltAgent catalog and its
description — "design, evaluate, or optimize cloud infrastructure architecture
at scale ... multi-cloud strategies, cloud migrations, disaster recovery, cost,
security/compliance" — is squarely on-topic. It was already a "propose, don't
adopt" placeholder on one project's roster and should now be ratified.

## When to deploy (triggers)
- Any AWS/Terraform/IAM/S3 provisioning task on a project you maintain.
- A cloud-architecture assessment: Well-Architected review, DB-downage
  mitigation, cost or disaster-recovery analysis.
- A recurring platform architecture assessment.

## Interface (how to invoke)
Dispatch via `Agent({description: "...", subagent_type: "cloud-architect",
prompt: "..."})`. It is the VoltAgent catalog agent
`voltagent-infra@voltagent-subagents`
(`03-infrastructure/cloud-architect`); adopt it through the project roster and
plugin-enable step — do NOT author a new agent file.

## Composition (pairs with / hands off to)
Pairs with the `aws-local-emulation` skill for dry runs against a local
emulator instead of a billed account, and would run the deferred
`aws-readonly-verify` tool as its standing inventory command. Hands off to
`technical-pm` for sprint/ticket planning of the provisioning work. Surfaced by
`resource-loop` on any cloud-architecture task.

## Build & maintenance notes
ADOPT — do not build. Per the global subagent routing protocol: (1) add a row
to the project's `.claude/SUBAGENTS.md` with a "why this one" and a "when to
dispatch" trigger; (2) enable `voltagent-infra@voltagent-subagents` in the
project's `.claude/settings.local.json` under `enabledPlugins`. Run
`/subagent-catalog:fetch cloud-architect` to preview before adopting. No new
agent file is authored.
