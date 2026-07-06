# INSTALL — the manual fallback

`install.sh` does everything below for you, idempotently. This file is the
by-hand version: run it yourself if you would rather not run the script, or
read it to understand exactly what the script changes. Every path is under
`~/.claude/`.

> Throughout, `~` is your home directory. The installer rewrites the literal
> `$HOME` in the hook path to your actual home, so the hook works regardless of
> your username.

---

## What `install.sh` changes (the short list)

1. Creates `~/.claude/` if it does not exist.
2. Backs up `~/.claude/settings.json` and `~/.claude/CLAUDE.md` to
   `*.bak-agentloop` — **once** (a second run does not overwrite the backup).
3. Copies `payload/skills`, `payload/agents`, `payload/tools`,
   `payload/registry`, and `payload/hooks` into `~/.claude/`, merging with what
   is already there (it never deletes your files).
4. Marks the hook and every `*.sh` tool executable.
5. Registers two plugin marketplaces (via the `claude` CLI when available,
   otherwise by writing them into `settings.json`).
6. Deep-merges `payload/fragments/settings.fragment.json` into
   `~/.claude/settings.json`.
7. Appends `payload/fragments/CLAUDE.starter.md` into `~/.claude/CLAUDE.md`,
   between the `<!-- BEGIN AGENT-LOOP -->` and `<!-- END AGENT-LOOP -->`
   sentinels.

---

## Step by step, by hand

### 1. Pre-flight and backups

```bash
mkdir -p ~/.claude
[ -f ~/.claude/settings.json ] && cp ~/.claude/settings.json ~/.claude/settings.json.bak-agentloop
[ -f ~/.claude/CLAUDE.md ]     && cp ~/.claude/CLAUDE.md     ~/.claude/CLAUDE.md.bak-agentloop
```

### 2. Copy the payload resources

From this export folder:

```bash
cp -R payload/skills/.   ~/.claude/skills/
cp -R payload/agents/.   ~/.claude/agents/
cp -R payload/tools/.    ~/.claude/tools/
cp -R payload/registry/. ~/.claude/registry/
cp -R payload/hooks/.    ~/.claude/hooks/
chmod +x ~/.claude/hooks/inject-resource-loop.sh
find ~/.claude/tools -name '*.sh' -exec chmod +x {} \;
```

`cp -R <dir>/. <dest>/` copies the *contents* of `<dir>` into `<dest>`, merging
with whatever is already there.

### 3. Register the plugin marketplaces

If you have the `claude` CLI:

```bash
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin marketplace add VoltAgent/awesome-claude-code-subagents
```

If you do not, the marketplaces go into `settings.json` in the next step, and
you finish the installs by running `/plugin` inside Claude Code.

### 4. Merge `settings.json`

Add these keys to `~/.claude/settings.json`, keeping everything you already
have. Use a JSON-aware edit (the installer uses `python3`); do not use `sed` on
JSON.

- **`hooks.SessionStart`** — append this group (only if a group with the same
  command is not already present), with `$HOME` replaced by your real home:

  ```json
  { "hooks": [ { "type": "command",
                 "command": "$HOME/.claude/hooks/inject-resource-loop.sh" } ] }
  ```

- **`enabledPlugins`** — set each of these to `true`:
  `superpowers@claude-plugins-official`,
  `voltagent-core-dev@voltagent-subagents`,
  `voltagent-lang@voltagent-subagents`,
  `voltagent-infra@voltagent-subagents`,
  `voltagent-qa-sec@voltagent-subagents`,
  `voltagent-data-ai@voltagent-subagents`,
  `voltagent-dev-exp@voltagent-subagents`,
  `voltagent-domains@voltagent-subagents`,
  `voltagent-biz@voltagent-subagents`,
  `voltagent-meta@voltagent-subagents`,
  `voltagent-research@voltagent-subagents`.

- **`extraKnownMarketplaces`** — add (if you skipped the CLI in step 3):

  ```json
  "claude-plugins-official": { "source": { "source": "github", "repo": "anthropics/claude-plugins-official" } },
  "voltagent-subagents": { "source": { "source": "github", "repo": "VoltAgent/awesome-claude-code-subagents" } }
  ```

- **`autoCompactEnabled`** — suggested `true`, but the installer sets it only if
  you have not already chosen a value. `autoCompactWindow` is left alone unless
  you opt in when the installer asks; tune it later via `/config`.

The exact merge payload is `payload/fragments/settings.fragment.json`.

### 5. Append the starter directives to `CLAUDE.md`

Paste the entire contents of `payload/fragments/CLAUDE.starter.md` — sentinels
included — at the end of `~/.claude/CLAUDE.md` (create the file if it does not
exist). On a re-install, replace whatever is already between the two sentinels
rather than pasting a second copy.

### 6. Tailor it to your machine

Run the self-configuring skill inside Claude Code:

```
/environment-bootstrap
```

It inspects your OS, editor, languages, cloud CLIs, and database clients;
asks a short interview about what you build and which databases you reach;
then tailors the registry, appends a personalized block to your `CLAUDE.md`
below the managed block, and fills in the database/MCP templates with your
own connection details. Re-run it any time your setup changes.

### 7. Finish

- Restart Claude Code, or run `/hooks` to reload the SessionStart hook.
- If any plugins are missing, run `/plugin` and install them from the two
  marketplaces.
- Verify the registry:

  ```bash
  python3 ~/.claude/tools/lint_registry.py   # expect: lint_registry: OK (0 error(s))
  ```

- Start a session and give it a task; expect a `Resource Loop —` line.

---

## Connecting a database (optional, and yours to wire up)

The export contains no secrets and no hostnames. To use the read-only
Postgres/MySQL MCP:

1. Copy `payload/mcp-specs/secrets.env.template` to a project's `secrets.env`
   and fill in **your** values. Never commit `secrets.env`.
2. Follow `payload/mcp-specs/postgres-readonly.md`: point it at your own
   database host, user, and port; open an SSH tunnel with
   `ssh-tunnel-keepalive` if the database sits behind a bastion; and register
   the server in that project's `.claude/settings.local.json`.

`payload/mcp-specs/global-mcps.md` covers the other MCP servers (`playwright`,
`google_workspace`).

---

## How to undo

1. Restore your backed-up config:

   ```bash
   mv ~/.claude/settings.json.bak-agentloop ~/.claude/settings.json
   mv ~/.claude/CLAUDE.md.bak-agentloop     ~/.claude/CLAUDE.md
   ```

   (If you have made other changes since installing, merge by hand instead of a
   blind restore.)

2. If you would rather keep your current `CLAUDE.md`, just delete the block
   between `<!-- BEGIN AGENT-LOOP -->` and `<!-- END AGENT-LOOP -->`.

3. The copied `skills/`, `agents/`, `tools/`, `registry/`, and `hooks/` files
   are additive. Remove the specific files the payload added if you want them
   gone; nothing else depends on them once the hook and the CLAUDE.md block are
   removed.
