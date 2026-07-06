#!/usr/bin/env bash
# =============================================================================
# claude-agent-loop-starter installer
# -----------------------------------------------------------------------------
# Idempotent. Safe to run twice. Never clobbers your existing config — it MERGES.
# Backs up settings.json and CLAUDE.md once before touching them.
#
#   Usage:  bash install.sh
#   Then, in Claude Code:  /environment-bootstrap   (tailors it to your machine)
#
# What it installs into ~/.claude/:
#   - skills/  agents/  tools/  registry/  hooks/   (copied, never deleting yours)
#   - a SessionStart hook that injects the Resource Loop each session
#   - the enabledPlugins map (11 plugins: superpowers + the VoltAgent catalog)
#   - the agent-loop operating directives, appended to CLAUDE.md between sentinels
#
# It installs NO secret, NO database host, and NO MCP registration. Those are
# templates under payload/mcp-specs/ that the environment-bootstrap skill helps
# you wire up yourself.
# =============================================================================

# We intentionally do NOT `set -e`: every step is guarded and the script must
# never abort a re-run just because one step was already done.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD="$SCRIPT_DIR/payload"
CLAUDE_DIR="$HOME/.claude"
FRAGMENTS="$PAYLOAD/fragments"

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
ok()   { printf '   [ok] %s\n' "$*"; }
warn() { printf '   [!!] %s\n' "$*"; }

say "claude-agent-loop-starter installer"
say "Target: $CLAUDE_DIR"

# --- python3 is required for the JSON merges --------------------------------
PY=""
if command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
fi

# ---------------------------------------------------------------------------
step "Step 1 — pre-flight and one-time backups"

if [ ! -d "$CLAUDE_DIR" ]; then
  mkdir -p "$CLAUDE_DIR" && ok "created $CLAUDE_DIR" || warn "could not create $CLAUDE_DIR"
else
  ok "$CLAUDE_DIR exists"
fi

backup_once() {
  f="$1"
  if [ -f "$f" ] && [ ! -f "$f.bak-agentloop" ]; then
    cp "$f" "$f.bak-agentloop" && ok "backed up $(basename "$f") -> $(basename "$f").bak-agentloop"
  elif [ -f "$f.bak-agentloop" ]; then
    ok "backup already present for $(basename "$f") (original .bak-agentloop kept intact)"
  else
    ok "no existing $(basename "$f") to back up (fresh)"
  fi
}
backup_once "$CLAUDE_DIR/settings.json"
backup_once "$CLAUDE_DIR/CLAUDE.md"

# ---------------------------------------------------------------------------
step "Step 2 — copy payload resources (merge; your other files are untouched)"

copy_into() {
  src="$1"; dest="$2"
  if [ -d "$src" ]; then
    mkdir -p "$dest"
    if cp -R "$src/." "$dest/" 2>/dev/null; then
      ok "$(basename "$dest")/  <-  payload/$(basename "$src")/"
    else
      warn "copy failed: $src -> $dest"
    fi
  else
    warn "missing payload dir: $src"
  fi
}

copy_into "$PAYLOAD/skills"   "$CLAUDE_DIR/skills"
copy_into "$PAYLOAD/agents"   "$CLAUDE_DIR/agents"
copy_into "$PAYLOAD/tools"    "$CLAUDE_DIR/tools"
copy_into "$PAYLOAD/registry" "$CLAUDE_DIR/registry"
copy_into "$PAYLOAD/hooks"    "$CLAUDE_DIR/hooks"

# Make the hook and every shell tool executable.
if [ -f "$CLAUDE_DIR/hooks/inject-resource-loop.sh" ]; then
  chmod +x "$CLAUDE_DIR/hooks/inject-resource-loop.sh" 2>/dev/null && ok "hook is executable" || warn "could not chmod hook"
fi
find "$CLAUDE_DIR/hooks" -name '*.sh' -exec chmod +x {} \; 2>/dev/null
find "$CLAUDE_DIR/tools" -name '*.sh' -exec chmod +x {} \; 2>/dev/null
ok "shell tools under tools/ and hooks/ marked executable"

# ---------------------------------------------------------------------------
step "Step 3 — register plugin marketplaces"

EXTRA_MP=""
if command -v claude >/dev/null 2>&1; then
  ok "claude CLI found — adding marketplaces via the CLI"
  for repo in \
    anthropics/claude-plugins-official \
    VoltAgent/awesome-claude-code-subagents
  do
    if claude plugin marketplace add "$repo" >/dev/null 2>&1; then
      ok "added marketplace $repo"
    else
      ok "marketplace $repo already known (or add skipped) — fine"
    fi
  done
  say "   (plugins enabled in settings.json will install on next start; run /plugin if any are missing)"
else
  warn "claude CLI not found — writing marketplaces into settings.json instead"
  say "   You will finish plugin installs by running /plugin inside Claude Code."
  EXTRA_MP="claude-plugins-official=anthropics/claude-plugins-official,voltagent-subagents=VoltAgent/awesome-claude-code-subagents"
fi
export EXTRA_MP

# ---------------------------------------------------------------------------
step "Step 4 — optional: autoCompactWindow"

AUTOCOMPACT_WINDOW=""
if [ -t 0 ]; then
  printf '   Set autoCompactWindow (token budget before auto-compact)? [y/N] '
  read ans
  case "$ans" in
    y|Y|yes|YES|Yes)
      printf '   Enter a token count (e.g. 120000), or leave blank to skip: '
      read acw
      case "$acw" in
        ''|*[!0-9]*) ok "skipped (no valid number given)";;
        *) AUTOCOMPACT_WINDOW="$acw"; ok "will set autoCompactWindow=$acw";;
      esac
      ;;
    *) ok "autoCompactWindow left unset (tune it later via /config)";;
  esac
else
  ok "non-interactive run — autoCompactWindow left unset"
fi
export AUTOCOMPACT_WINDOW

# ---------------------------------------------------------------------------
step "Step 5 — merge settings.json (deep-merge; everything you have is kept)"

if [ -z "$PY" ]; then
  warn "python3 not found — CANNOT safely merge settings.json."
  warn "Install python3, then re-run this script (it is idempotent)."
else
  "$PY" - "$CLAUDE_DIR/settings.json" "$FRAGMENTS/settings.fragment.json" "$HOME" <<'PY'
import json, os, sys

settings_path, fragment_path, real_home = sys.argv[1], sys.argv[2], sys.argv[3]
extra_mp = os.environ.get("EXTRA_MP", "").strip()
ac_window = os.environ.get("AUTOCOMPACT_WINDOW", "").strip()

def load(p, required=False):
    try:
        with open(p) as f:
            return json.load(f)
    except FileNotFoundError:
        if required:
            print("ERROR: fragment not found: %s" % p, file=sys.stderr)
            sys.exit(2)
        return {}
    except ValueError as e:
        print("ERROR: %s is not valid JSON (%s) — not touching it." % (p, e),
              file=sys.stderr)
        sys.exit(3)

settings = load(settings_path)
frag = load(fragment_path, required=True)
if not isinstance(settings, dict):
    print("ERROR: %s is not a JSON object — not touching it." % settings_path,
          file=sys.stderr)
    sys.exit(4)

changed = []

# --- SessionStart hook: add our group only if its command is not already there
frag_ss = frag.get("hooks", {}).get("SessionStart", [])
settings.setdefault("hooks", {})
if not isinstance(settings["hooks"], dict):
    settings["hooks"] = {}
ss = settings["hooks"].setdefault("SessionStart", [])
if not isinstance(ss, list):
    ss = []
    settings["hooks"]["SessionStart"] = ss

existing_cmds = set()
for group in ss:
    if isinstance(group, dict):
        for h in group.get("hooks", []):
            if isinstance(h, dict) and "command" in h:
                existing_cmds.add(h["command"])

for group in frag_ss:
    g = json.loads(json.dumps(group))  # deep copy
    cmds = []
    for h in g.get("hooks", []):
        if isinstance(h, dict) and "command" in h:
            h["command"] = h["command"].replace("$HOME", real_home)
            cmds.append(h["command"])
    if not any(c in existing_cmds for c in cmds):
        ss.append(g)
        existing_cmds.update(cmds)
        changed.append("added SessionStart hook")
    else:
        changed.append("SessionStart hook already present")

# --- enabledPlugins: ours are required, so force them enabled; keep yours
ep = settings.setdefault("enabledPlugins", {})
if not isinstance(ep, dict):
    ep = {}
    settings["enabledPlugins"] = ep
for k, v in frag.get("enabledPlugins", {}).items():
    if ep.get(k) is not True:
        ep[k] = v
        changed.append("enabled %s" % k)

# --- extraKnownMarketplaces: add any missing, never overwrite yours
ekm = settings.setdefault("extraKnownMarketplaces", {})
if not isinstance(ekm, dict):
    ekm = {}
    settings["extraKnownMarketplaces"] = ekm
for k, v in frag.get("extraKnownMarketplaces", {}).items():
    if k not in ekm:
        ekm[k] = v
        changed.append("known marketplace %s" % k)
if extra_mp:
    for pair in extra_mp.split(","):
        pair = pair.strip()
        if not pair:
            continue
        name, _, repo = pair.partition("=")
        name, repo = name.strip(), repo.strip()
        if name and repo and name not in ekm:
            ekm[name] = {"source": {"source": "github", "repo": repo}}
            changed.append("known marketplace %s" % name)

# --- autoCompactEnabled: suggested; set only if you have not chosen already
if "autoCompactEnabled" in frag and "autoCompactEnabled" not in settings:
    settings["autoCompactEnabled"] = frag["autoCompactEnabled"]
    changed.append("autoCompactEnabled=%s" % frag["autoCompactEnabled"])

# --- autoCompactWindow: only when you opted in above
if ac_window:
    try:
        settings["autoCompactWindow"] = int(ac_window)
        changed.append("autoCompactWindow=%s" % ac_window)
    except ValueError:
        pass

tmp = settings_path + ".hdctmp"
with open(tmp, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
os.replace(tmp, settings_path)

if changed:
    for c in changed:
        print("   [ok] settings: %s" % c)
else:
    print("   [ok] settings already up to date")
PY
  if [ $? -eq 0 ]; then
    ok "settings.json merged"
  else
    warn "settings.json merge reported a problem (see message above) — your file was left untouched"
  fi
fi

# ---------------------------------------------------------------------------
step "Step 6 — append agent-loop directives to CLAUDE.md (between sentinels)"

if [ -z "$PY" ]; then
  warn "python3 not found — skipping CLAUDE.md merge. Append fragments/CLAUDE.starter.md by hand."
else
  "$PY" - "$CLAUDE_DIR/CLAUDE.md" "$FRAGMENTS/CLAUDE.starter.md" <<'PY'
import sys

target, fragment = sys.argv[1], sys.argv[2]
BEGIN = "<!-- BEGIN AGENT-LOOP -->"
END = "<!-- END AGENT-LOOP -->"

with open(fragment) as f:
    frag = f.read().strip("\n")

try:
    with open(target) as f:
        existing = f.read()
except FileNotFoundError:
    existing = ""

if BEGIN in existing and END in existing:
    start = existing.index(BEGIN)
    end = existing.index(END) + len(END)
    new = existing[:start] + frag + existing[end:]
    action = "replaced existing AGENT-LOOP block"
else:
    new = existing
    if new and not new.endswith("\n"):
        new += "\n"
    if new:
        new += "\n"
    new += frag + "\n"
    action = "appended AGENT-LOOP block"

with open(target, "w") as f:
    f.write(new)
print("   [ok] CLAUDE.md: %s" % action)
PY
  ok "CLAUDE.md updated"
fi

# ---------------------------------------------------------------------------
step "NEXT STEPS"
cat <<'STEPS'
   1. Tailor this setup to YOUR machine. Open Claude Code in VS Code and run:
         /environment-bootstrap
      It inspects your system, asks a few questions, and personalizes the
      registry, your CLAUDE.md, and the database/MCP templates.

   2. Restart Claude Code (or run /hooks to reload) so the SessionStart hook
      takes effect. Start a session: you should see a line beginning
      "Resource Loop —" once you give it a task.

   3. If any plugins are missing, run  /plugin  inside Claude Code and install
      from the two marketplaces (claude-plugins-official, voltagent-subagents).
      This is required only if the claude CLI was not available during install.

   4. Verify the registry is intact:
         python3 ~/.claude/tools/lint_registry.py
      Expect:  lint_registry: OK (0 error(s))

   5. To connect a database, copy  payload/mcp-specs/secrets.env.template  to a
      project's secrets.env, fill in YOUR values (never commit it), open a tunnel
      if the database is remote (ssh-tunnel-keepalive), and register the server
      per  payload/mcp-specs/postgres-readonly.md . The install ships NO secrets.

   To undo: restore ~/.claude/settings.json.bak-agentloop and
   ~/.claude/CLAUDE.md.bak-agentloop, and delete the block between the
   <!-- BEGIN AGENT-LOOP --> / <!-- END AGENT-LOOP --> sentinels in CLAUDE.md.
STEPS

say ""
say "Done. This installer is idempotent — re-run it any time; it will not"
say "duplicate the hook, re-enable what is already on, or clobber your settings."
exit 0
