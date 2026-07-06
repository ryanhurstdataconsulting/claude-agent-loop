# MCP spec — global personal MCPs (`playwright`, `google_workspace`)

**Category:** personal / standard MCPs · **Portable:** partial — `playwright`
is fully portable; `google_workspace` needs your own Google account.

These two MCP servers are registered **globally** on your machine (in
`~/.claude/settings.json` under `mcpServers`), not per project. They are not
part of any specific client stack — they are general-purpose tools. The
installer does **not** register them for you, because one of them is tied to a
personal Google login. Add whichever you want, yourself.

---

## `playwright` — browser automation (fully portable)

Standard Microsoft Playwright MCP. Drives a real browser for testing,
screenshots, and DOM checks. No account, no secret.

Global registration, in `~/.claude/settings.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp"]
    }
  }
}
```

First run downloads the browser binaries, which takes a minute. After that it
is instant.

---

## `google_workspace` — Drive / Sheets / Docs / Forms (your own account)

Connects to Google Workspace for Drive, Sheets, Docs, and Forms operations.
**This is bound to a Google account — use your own, never a colleague's.** The
exact package and the auth flow are personal setup, so treat this section as a
pointer rather than a turnkey block:

- Register it globally in `~/.claude/settings.json`, the same way as
  `playwright`, using the Google Workspace MCP package you choose.
- On first use, it runs a Google OAuth flow (`start_google_auth`) in your
  browser. Sign in with **your** Google account and grant the scopes.
- Nothing about this server should carry a token in `settings.json` — the auth
  lives in Google's session, not in the config file.

If you do not do Google Drive or Sheets work, skip this one entirely.

---

## Why the installer leaves these to you

This starter kit ships a generic environment. Browser automation is
generically useful, but a Google login is personal, so wiring it up for you
would be wrong. Add `playwright` if you expect to do any browser-driven
verification; add `google_workspace` only when you have a Google account you
are comfortable connecting.
