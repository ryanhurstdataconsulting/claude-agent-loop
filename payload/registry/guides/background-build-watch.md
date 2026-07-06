# Guide — background-build-watch

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Long-running builds forced agents to hand-roll `until`-loops to poll a log —
one session held 10+ of them — and the `Monitor` tool, which needs manual
re-arming, twice expired unused because the agent forgot to re-point it. This
pattern recurred across multiple projects and sessions. It is a thin
convenience wrapper over `Monitor`, not a duplicate: the value it adds is
firing exactly one notification and self-clearing, so no re-arm step can be
forgotten.

## When to deploy (triggers)
- Any long-running build, compile, render, or process the agent must poll for
  completion (a webpack/Vite build, a Tauri bundle, a PDF render, a data ETL).
- Whenever the alternative is a hand-written `until grep ... done` loop.
- Whenever a previous `Monitor` watcher was set and then forgotten.

## Interface (how to invoke)
Tool. Give it a log path, a success regex, and a fail regex; it watches via the
`Monitor` tool, fires one notification on the first match of either pattern,
and self-clears. Exact invocation:
`python3 ~/.claude/tools/background_build_watch.py --log <path> --ok
<success-regex> --fail <fail-regex>`.

## Composition (pairs with / hands off to)
Wraps the `Monitor` tool (its execution backbone). Pairs with
`dev-server-orchestration` (watch the server it brings up) and with
`tauri-desktop-dev` / `document-render` builds. Surfaced by
`resource-loop` whenever a build is launched in the background.

## Build & maintenance notes
Build sketch: a wrapper taking a log path plus a success regex and a fail
regex, backed by `Monitor`, that notifies exactly once and self-clears — framed
as an extension of the established `Monitor` usage pattern, not a new watcher
engine. Lives at `~/.claude/tools/background_build_watch.py`; test by tailing a
fixture log that emits a success line, then one that emits a failure line.
