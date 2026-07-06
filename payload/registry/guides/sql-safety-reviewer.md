# Guide — sql-safety-reviewer

**Category:** agent
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Provides an independent SAFE / NOT SAFE verdict on SQL text and its
connection preamble before any query touches a production database.

## When to deploy (triggers)
Immediately before every production-database query — confirms the
read-only wrapper, statement timeout, and absence of DDL or writing DML.

## Interface (how to invoke)
Dispatch via `Agent({description: "...", subagent_type:
"sql-safety-reviewer", prompt: "..."})`; reviews text only (Read, Grep —
no execution), model tier as configured in the agent definition.

## Composition (pairs with / hands off to)
Always pairs with whatever project skill produced the query (e.g., a
project's own database-agent guide) and the `postgres-readonly` MCP (the
execution path it gates).

## Build & maintenance notes
Lives at `~/.claude/agents/sql-safety-reviewer.md`.
