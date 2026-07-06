---
name: tauri-desktop-dev
description: Use when building or debugging a Tauri 2 desktop app, or packaging a Python / FastAPI backend as a Tauri sidecar. Carries each Tauri-2 gotcha with its symptom and fix, plus the PyInstaller-sidecar lifecycle recipe (health-gated window, orphan-process watchdog, Gatekeeper handoff). Triggers include a file written just outside $HOME, a fetch() that works in the browser or in Chromium but fails in the packaged macOS app window, a Vitest run that cannot bind port 1420, an orphaned Python process holding the port after the window closes, and a Gatekeeper "app is damaged" block on an unsigned build.
---

# tauri-desktop-dev

## Overview

Tauri 2 desktop builds cost multi-hour rediscovery of framework-specific quirks
that otherwise ship broken to a pilot. This skill is the running catalog: **each
gotcha as symptom → root cause → fix**, plus the recipe for packaging a Python /
FastAPI backend as a bundled sidecar. It was validated against the RankingTool
desktop build that first exercised these paths.

Two framing facts to keep in mind throughout:

- **macOS Tauri renders in WKWebView, not Chromium.** `tauri dev` in a browser
  tab and the packaged `.app` are *different runtimes*. "It works in the browser"
  proves almost nothing about the shipped window.
- **Tauri v2 changed several API contracts from v1** in ways that fail silently
  rather than loudly. The `homeDir()` change below is the canonical example.

## Gotcha 1 — `homeDir()` lost its trailing slash (v1 → v2), silently writing outside `$HOME`

**Symptom:** files land just *outside* the home directory — e.g. a save meant
for `/Users/you/AppData/` is written to `/Users/youAppData/` (note the missing
separator). No error is thrown; the write "succeeds" in the wrong place.

**Root cause:** in Tauri v1, `homeDir()` returned a path **with** a trailing
slash (`/Users/you/`). In v2 it returns **no** trailing slash (`/Users/you`).
Any code that string-concatenates — `homeDir() + "AppData/"` — now produces a
sibling path instead of a child path.

**Fix:** never string-concatenate paths. Use the path API's `join`:

```ts
import { homeDir, join } from '@tauri-apps/api/path';
const target = await join(await homeDir(), 'AppData', 'state.json'); // correct on v1 and v2
```

Audit every `homeDir() +`, `appDataDir() +`, and `+ "/"` concatenation when
migrating a v1 app to v2 — this is a data-loss-class bug that leaves no trace.

## Gotcha 2 — WKWebView `fetch` dies where Chromium succeeds

**Symptom:** a `fetch()` to the local sidecar (or any host) works in `tauri dev`
/ a Chromium tab but fails in the packaged macOS window — silently, or as a CORS
/ mixed-content / "Load failed" error.

**Root cause:** WKWebView (the macOS webview) is far stricter than Chromium about
`localhost` vs `127.0.0.1`, custom URL schemes, mixed content, and CORS
preflights. Requests Chromium waves through, WKWebView drops.

**Fix — prefer moving the network call out of the webview entirely:**

- Use the Tauri HTTP plugin (`@tauri-apps/plugin-http`) or `invoke` a Rust
  command that makes the request, instead of the webview's `fetch`. Rust-side
  requests are not subject to WKWebView's policy.
- If the call must stay in the webview: bind the sidecar to **`127.0.0.1`
  explicitly** (not `localhost`, which WKWebView may resolve differently), have
  the sidecar send permissive CORS headers for the app origin, and add the host
  to the CSP / `app.security.csp` allowlist in `tauri.conf.json`.
- Always reproduce network bugs in the **packaged app**, never only in the dev
  browser — the two runtimes disagree exactly here.

## Gotcha 3 — the Vite ↔ Vitest `strictPort: 1420` collision

**Symptom:** the Vitest suite fails to start or hangs — port 1420 is already in
use, or the dev server and a test run fight over the same port and one dies.

**Root cause:** the Tauri scaffold sets `server.strictPort: true` on port
**1420** in `vite.config.ts`. Vitest inherits that same config, so if the Tauri
dev server is running (or two test processes overlap), Vitest cannot bind 1420
and `strictPort` makes it fail hard instead of picking another port.

**Fix:** keep the strict port for `tauri dev` but do not let Vitest inherit it.
Either gate it on the Vitest env, or give Vitest its own config:

```ts
// vite.config.ts
export default defineConfig({
  server: { strictPort: !process.env.VITEST, port: 1420 }, // relax under Vitest
  test: { /* ... */ },
});
```

The `!process.env.VITEST` guard lets the dev server hold 1420 while the test
runner is free to bind anything.

## Packaging a Python / FastAPI backend as a Tauri sidecar

Bundle the backend as a PyInstaller binary declared in `tauri.conf.json` under
`bundle.externalBin`. The binary name **must** carry Tauri's target-triple
suffix (e.g. `backend-aarch64-apple-darwin`) or the bundler will not find it.
Beyond naming, three lifecycle problems bite every time.

### Health-gated window handoff

**Symptom:** the window opens, the UI loads, its first `fetch` to the sidecar
fails, and the app appears broken — because the FastAPI process has not finished
starting.

**Fix:** do not show the window until the backend answers. In the Rust `setup()`
hook, spawn the sidecar, then poll `GET /health` (with a short timeout and a
bounded retry loop) and only call `window.show()` once it returns 200. Start the
window `visible: false` in `tauri.conf.json` and reveal it on the health gate.

### Orphan-process watchdog

**Symptom:** after the Tauri window closes, the PyInstaller sidecar keeps
running as an orphan, holding its port — so the next launch cannot bind, or `ps`
shows a pile of stale backends.

**Fix — belt and suspenders, because either side can die first:**

- **Tauri side:** on `WindowEvent::CloseRequested` / `Destroyed` (and on app
  exit), kill the spawned child. Keep the `CommandChild` handle from
  `spawn()` and call `.kill()`; do not rely on the child dying with the parent.
- **Python side:** have the sidecar watch its parent PID and self-exit when the
  parent disappears (poll `os.getppid()` — a reparent to PID 1 means the Tauri
  app is gone). This catches the case where Tauri crashes without running its
  handler.

### Unsigned-app Gatekeeper handoff

**Symptom:** the pilot user double-clicks the `.app` / `.dmg` and macOS refuses:
"app is damaged and can't be opened" or "cannot verify the developer."

**Root cause:** an unsigned, unnotarized bundle gets a
`com.apple.quarantine` xattr on download, and Gatekeeper blocks it.

**Fix:**

- **Short term (pilot, no Developer ID yet):** ship the handoff instruction —
  either right-click → **Open** (once) to override, or strip quarantine:
  `xattr -dr com.apple.quarantine "/Applications/YourApp.app"`. Document this in
  the pilot's install note so it is not mistaken for a broken build.
- **Proper fix:** sign with a Developer ID certificate and notarize
  (`codesign --deep --sign`, then `notarytool submit --wait` and `stapler`). Do
  this before any wider distribution — the `xattr` workaround does not scale.

## Composition

- Confirm the toolchain first (Rust, Node, PyInstaller present) before building.
- Use one command to bring the dev stack (Tauri window + sidecar) up and down
  with a health gate rather than juggling processes by hand.
- Watch the bundle build in the background rather than blocking on it.
