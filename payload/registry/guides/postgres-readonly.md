# Guide — postgres-readonly

**Category:** mcp
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
A DBA — or anyone who works against a database — wants Claude to run real SELECT
queries (schema questions, data checks, exploration) without copy-pasting result
sets. This registration gives Claude a live, read-only SQL connection, with
credentials kept out of any tracked file.

## When to deploy (triggers)
Any Postgres/MySQL query, schema question, or data-quality check against a real
database; a localhost tunnel to a remote DB; "run this SELECT for me".

## Interface (how to invoke)
Register the MCP server per `mcp-specs/postgres-readonly.md`
(`@modelcontextprotocol/server-postgres` over a localhost port). Connect
read-only; the password comes from `secrets.env`, never the registration. The
tunnel, if the database is remote, is held open by `ssh-tunnel-keepalive`.

## Composition (pairs with / hands off to)
Pairs with `ssh-tunnel-keepalive` (opens the local port) and, mandatorily, with
the `sql-safety-reviewer` agent — dispatch it for a SAFE / NOT SAFE verdict
before running any query it has not seen. Filled in during `environment-bootstrap`.

## Build & maintenance notes
Registration lives in a project's `.claude/settings.local.json` (or global
settings). Enforce read-only at the database (a SELECT-only role) and per session
(`SET default_transaction_read_only = on; SET statement_timeout = '30s';`). Never
embed a password; put it in `secrets.env` (gitignored).
