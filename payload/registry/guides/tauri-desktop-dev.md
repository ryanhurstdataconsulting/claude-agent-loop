# Guide — tauri-desktop-dev

**Category:** skill
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Tauri-2 desktop builds cost multi-hour rediscovery of framework-specific quirks
that would otherwise ship broken to a pilot: `homeDir()` returning no trailing
slash on macOS (a v1→v2 change that silently wrote outside `$HOME`), WKWebView
`fetch` dying where Chromium succeeds, the Vite↔Vitest `strictPort: 1420`
collision that made the test suite unusable, and the PyInstaller sidecar's
health-gated window, orphan-process watchdog, and unsigned-app Gatekeeper
handoff. This pattern recurred across multiple projects, and it was already
reused once in a later desktop build. This skill merges the Tauri-2 gotcha
catalog and the Python-sidecar packaging recipe into one reference.

## When to deploy (triggers)
- Building or debugging a Tauri 2 desktop app.
- Packaging a Python/FastAPI backend as a Tauri sidecar.
- Symptoms it resolves: a file written just outside `$HOME`; a `fetch` that
  works in the browser but fails in the app window; a Vitest run that cannot
  bind port 1420; an orphaned Python sidecar process after the window closes;
  a Gatekeeper block on an unsigned build.

## Interface (how to invoke)
`Skill(tauri-desktop-dev)`. The skill carries each quirk with its symptom and
fix, plus the sidecar packaging recipe (health-gated window handoff,
orphan-process watchdog, and the Gatekeeper note for unsigned distribution).

## Composition (pairs with / hands off to)
Depends on `env-tooling-preflight` (Rust toolchain, Node, PyInstaller present)
and pairs with `dev-server-orchestration` (the Tauri dev-window up/down path)
and `background-build-watch` (watch the bundle build). Surfaced by
`resource-loop` on any Tauri task.

## Build & maintenance notes
Build sketch: one skill file, one entry per quirk — symptom, root cause, fix —
covering `homeDir()` v1→v2, WKWebView `fetch`, the Vite↔Vitest port collision,
and the PyInstaller sidecar lifecycle (health gate, orphan watchdog, Gatekeeper
handoff). Lives at `~/.claude/skills/tauri-desktop-dev/`; validate against the
desktop build that first exercised these paths.
