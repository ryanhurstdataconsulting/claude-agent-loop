# Guide — google_workspace

**Category:** mcp
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Provides Drive, Sheets, Docs, and Forms operations for deliverables that
live in Google Workspace rather than the local filesystem.

## When to deploy (triggers)
Reading/writing Google Sheets or Docs, managing Drive files or
permissions, or building/reading Google Forms.

## Interface (how to invoke)
MCP server `google_workspace`, registered globally in `~/.claude.json`
(`mcpServers.google_workspace`, `uvx workspace-mcp --tools drive sheets
forms`).

## Composition (pairs with / hands off to)
Pairs with `sports-analyst` / `data-visualization` when a deliverable is
exported to a Google Sheet or Slide deck.

## Build & maintenance notes
Global registration; requires Google OAuth
(`GOOGLE_OAUTH_CLIENT_ID` set in the server env).
