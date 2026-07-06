# Guide — dev-server-orchestration

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
"Spin it up" and "let me test" repeatedly triggered 8-to-12 manual
kill/restart/health-probe cycles per session across FastAPI+Vite,
`http.server`, and Tauri stacks, and in one case a stale process was mistaken
for a code bug. This pattern recurred across multiple projects and sessions.
The fix is one shared convention — a per-project script exposing the same
entry point — so every project brings its dev stack up with a health gate and
tears it down cleanly, and a restart-versus-code-bug false alarm cannot recur.

## When to deploy (triggers)
- The user says "spin it up", "let me test", "run it", or "bring the server
  up".
- Any task that needs the project's dev stack (tunnel + API + admin, a plain
  `http.server`, or a Tauri dev window) running before it can proceed.
- Symptoms it prevents: an orphaned port-holding process; a stale server
  serving old code; a manual health-probe loop.

## Interface (how to invoke)
Tool. One shared filename convention per project — `dev_up.sh` and
`dev_down.sh` (or `make serve` / `make stop`). `dev_up.sh` starts the stack and
blocks on a health gate (HTTP 200 on a known path) before returning;
`dev_down.sh` stops every process it started. Exact call: `./dev_up.sh` /
`./dev_down.sh` from the project root.

## Composition (pairs with / hands off to)
Pairs with `background-build-watch` (watch the server log it starts) and with
`ssh-tunnel-keepalive` (the tunnel a full stack needs). For Tauri stacks
it hands off to `tauri-desktop-dev`. Surfaced by `resource-loop` on any
"spin it up" trigger.

## Build & maintenance notes
Build sketch: a thin per-project wrapper over the stack's real start commands
plus a health poll, standardized on one filename so every project exposes an
identical entry point. Keep the health gate strict (a real 200, not just "the
process exists") to kill the restart-vs-code-bug ambiguity. Lives per project
at the repo root; the shared convention is documented once. Test by bringing a
stack up, confirming the gate, and confirming clean teardown.
