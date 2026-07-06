# Guide — playwright

**Category:** mcp
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Provides browser automation, testing, and screenshot capability for any
web-facing verification task.

## When to deploy (triggers)
Driving a web app end-to-end, capturing screenshots for a visual check,
or automating a browser-based test flow.

## Interface (how to invoke)
MCP server `playwright`, registered globally in `~/.claude.json`
(`mcpServers.playwright`, `npx @playwright/mcp@latest`).

## Composition (pairs with / hands off to)
Pairs with the `run` skill (launching an app) and the `verify` skill
(exercising a change end-to-end).

## Build & maintenance notes
Global registration; no project-specific setup required.
