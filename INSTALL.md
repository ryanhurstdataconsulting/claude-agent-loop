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
3. **Symlinks** the framework files named in `payload/MANIFEST` (skills, agents,
   tools, hooks, and the registry guides) into `~/.claude/`, so a later
   `git pull` updates them in place. The registry index (`REGISTRY.md`,
   `TRIGGERS.md`) and the `learning/` seeds are **copied once** and then left
   alone, so your learned state is never re-clobbered. A real file you have put
   at a target path is never overwritten — the installer warns that it shadows
   the framework version.
4. Marks every hook and every `*.sh` tool executable, and creates the runtime
   `metrics/` and `learning/` directories.
5. Registers two plugin marketplaces (via the `claude` CLI when available,
   otherwise by writing them into `settings.json`).
6. Deep-merges `payload/fragments/settings.fragment.json` into
   `~/.claude/settings.json` — the four hook groups (SessionStart, SubagentStop,
   SessionEnd, PreCompact), the plugin map, and the marketplaces — deduping by
   command so a re-run never double-adds.
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

### 2. Install the payload resources

`install.sh` **symlinks** every framework path named in `payload/MANIFEST` out of
this repo into `~/.claude/`, so the repo stays the single source of truth and a
`git pull` is live at once. To approximate that by hand, link the framework
directories, mark the shell entry points executable, and create the runtime
directories:

```bash
ln -s "$PWD/payload/skills"  ~/.claude/skills     # (see MANIFEST for the exact per-file list)
ln -s "$PWD/payload/agents"  ~/.claude/agents
ln -s "$PWD/payload/tools"   ~/.claude/tools
ln -s "$PWD/payload/hooks"   ~/.claude/hooks
find payload/hooks -name '*.sh' -exec chmod +x {} \;
find payload/tools -name '*.sh' -exec chmod +x {} \;
mkdir -p ~/.claude/metrics/state ~/.claude/learning/digests
```

Prefer a static snapshot instead? `cp -R payload/<dir>/. ~/.claude/<dir>/` copies
rather than links — but then updates are not live, and you re-copy after each
`git pull`. Either way, seed the registry index and the `learning/` files **only
if they are absent**, so an existing local copy (your learned state) is never
overwritten:

```bash
mkdir -p ~/.claude/registry ~/.claude/learning
for f in registry/REGISTRY.md registry/TRIGGERS.md \
         learning/SCALES.md learning/HEURISTICS.md learning/LOOP_THEMES.md; do
  [ -e ~/.claude/"$f" ] || cp payload/"$f" ~/.claude/"$f"
done
[ -e ~/.claude/learning/CLIENT_MARKERS.txt ] \
  || cp payload/learning/CLIENT_MARKERS.template.txt ~/.claude/learning/CLIENT_MARKERS.txt
```

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

- **`hooks`** — add these five event groups (each only if a group with the same
  command is not already present), with `$HOME` replaced by your real home. The
  SessionStart hook injects the registry index; the PostToolUse hook watches the
  session's context budget; the other three passively harvest the metrics the
  loop learns from:

  ```json
  "SessionStart": [ { "hooks": [ { "type": "command", "command": "$HOME/.claude/hooks/inject-resource-loop.sh" } ] } ],
  "SubagentStop": [ { "hooks": [ { "type": "command", "command": "$HOME/.claude/hooks/harvest-metrics.sh" } ] } ],
  "SessionEnd":   [ { "hooks": [ { "type": "command", "command": "$HOME/.claude/hooks/harvest-metrics.sh" } ] } ],
  "PreCompact":   [ { "hooks": [ { "type": "command", "command": "$HOME/.claude/hooks/precompact-event.sh" } ] } ],
  "PostToolUse":  [ { "hooks": [ { "type": "command", "command": "$HOME/.claude/hooks/context-budget.sh" } ] } ]
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

## Updating

The framework files under `~/.claude/` are symlinks into this repo, so updating
is just:

```bash
git -C <this-repo> pull && bash install.sh
```

The symlinked content is live the instant the pull lands. `install.sh` prints the
version delta, re-seeds only what is missing, and never re-clobbers your learned
`registry/` and `learning/` state.

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

## Usage-budget poller (one-time)

The usage-budget poller (`tools/usage_poll.py`) needs two manual, one-time steps
that `install.sh` deliberately does not perform — it authenticates a real browser
session and loads a user-level launchd job, neither of which the MANIFEST symlink
mechanism touches.

1. **Authenticate once.** Run the poller in login mode; a browser window opens.
   Log in to claude.ai, open the usage page, then return to the terminal and press
   Enter:

   ```bash
   python3 ~/.claude/tools/usage_poll.py --login
   ```

   This writes `~/.claude-agent-loop/usage-session.json` — a persisted Playwright
   session (cookies + localStorage). Treat it exactly like `secrets.env`: it lives
   outside the repo, under your home directory, and must never be committed,
   printed, or logged in full. There is no repo `.gitignore` line for it because it
   is not inside the repo; this note is its safeguard.

2. **Load the launchd job.** Copy the plist template into `~/Library/LaunchAgents/`
   and bootstrap it so macOS runs `usage_poll.py --poll` every 10 minutes:

   ```bash
   cp ~/.claude/launchd/com.hdc.claude-agent-loop.usage-poll.plist \
      ~/Library/LaunchAgents/
   launchctl bootstrap gui/$(id -u) \
      ~/Library/LaunchAgents/com.hdc.claude-agent-loop.usage-poll.plist
   ```

   Confirm it is loaded:

   ```bash
   launchctl list | grep usage-poll
   ```

If claude.ai's session later expires, the poller logs a login-redirect line to
`~/.claude/metrics/logs/usage_poll.log` and leaves the cache untouched; re-run
step 1 to re-authenticate.

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

3. The framework `skills/`, `agents/`, `tools/`, `registry/`, and `hooks/`
   entries are **symlinks** into this repo (additive — they never replace your
   own files). The cleanest undo is `bash uninstall.sh`, which removes only the
   symlinks that resolve into the repo, our four hook groups, and the `CLAUDE.md`
   block; add `--restore-backups` to also restore `settings.json` / `CLAUDE.md`
   from the one-time `.bak-agentloop` copies. Your `metrics/` and `learning/`
   data are left untouched.
