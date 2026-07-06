#!/usr/bin/env bash
# =============================================================================
# claude-agent-loop installer (v2 — MANIFEST-driven symlink engine)
# -----------------------------------------------------------------------------
# Idempotent. Safe to run twice. Never clobbers your existing config — it MERGES.
# Backs up settings.json and CLAUDE.md once before touching them.
#
#   Usage:  bash install.sh
#   Then, in Claude Code:  /environment-bootstrap   (tailors it to your machine)
#
# How framework content is installed:
#   Every path named in payload/MANIFEST is SYMLINKED out of this repo working
#   tree into ~/.claude/ (skills, agents, hooks, tools, registry guides). The
#   files stay live: this repo IS the source of truth, so updating is just
#
#       git -C <this-repo> pull && bash install.sh
#
#   and the symlinked content is current the instant the pull lands — no copy
#   step, no drift. A handful of files that are meant to DIVERGE locally
#   (registry/REGISTRY.md + TRIGGERS.md and the learning/ seeds) are COPIED once
#   and then never re-clobbered, so your learned state is never overwritten.
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
MANIFEST="$PAYLOAD/MANIFEST"
VERSION_FILE="$SCRIPT_DIR/VERSION"
INSTALLED_VERSION_FILE="$CLAUDE_DIR/learning/.installed-version"

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
ok()   { printf '   [ok] %s\n' "$*"; }
warn() { printf '   [!!] %s\n' "$*"; }

say "claude-agent-loop installer (v2)"
say "Target: $CLAUDE_DIR"
say "Source: $SCRIPT_DIR  (framework files are symlinked from here)"

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

# Counters for the Step 2 summary (and the loud shadowed-entry banner below).
# Declared at top level — not inside the MANIFEST branch — so they exist even
# if the MANIFEST is missing, and survive into the final NEXT STEPS message.
LINKED_COUNT=0
RELINKED_COUNT=0
SEEDED_COUNT=0
SHADOWED_COUNT=0
SHADOWED_LIST=""

# ---------------------------------------------------------------------------
step "Step 2 — install framework via MANIFEST (symlinks + seed copies)"

if [ ! -f "$MANIFEST" ]; then
  warn "MANIFEST not found at $MANIFEST — cannot install framework files."
else
  # Capture the previously installed version BEFORE we overwrite the marker,
  # so we can report the delta at the end.
  PREV_VERSION=""
  if [ -f "$INSTALLED_VERSION_FILE" ]; then
    PREV_VERSION="$(cat "$INSTALLED_VERSION_FILE" 2>/dev/null)"
  fi

  # --- link-dir / link-file: symlink SRC -> DEST, repairing as needed -------
  link_entry() {
    rel="$1"
    src="$PAYLOAD/$rel"
    dest="$CLAUDE_DIR/$rel"
    if [ ! -e "$src" ]; then
      warn "MANIFEST names a missing payload path: $rel"
      return
    fi
    if [ -L "$dest" ]; then
      cur="$(readlink "$dest")"
      if [ "$cur" = "$src" ]; then
        ok "link ok: $rel"
        LINKED_COUNT=$((LINKED_COUNT + 1))
      else
        rm -f "$dest"
        if ln -s "$src" "$dest"; then
          warn "relinked (was -> $cur): $rel"
          RELINKED_COUNT=$((RELINKED_COUNT + 1))
        else
          warn "relink failed: $rel"
        fi
      fi
    elif [ -e "$dest" ]; then
      # A real file/dir the user put here. Never clobber it.
      warn "local override shadows framework: $rel"
      SHADOWED_COUNT=$((SHADOWED_COUNT + 1))
      SHADOWED_LIST="${SHADOWED_LIST}${rel}
"
    else
      mkdir -p "$(dirname "$dest")"
      if ln -s "$src" "$dest"; then
        ok "linked: $rel"
        LINKED_COUNT=$((LINKED_COUNT + 1))
      else
        warn "link failed: $rel"
      fi
    fi
  }

  # --- copy-if-absent: seed a file only when nothing is already there -------
  copy_seed() {
    src_rel="$1"; dest_rel="$2"
    src="$PAYLOAD/$src_rel"
    dest="$CLAUDE_DIR/$dest_rel"
    if [ ! -f "$src" ]; then
      warn "MANIFEST names a missing seed: $src_rel"
      return
    fi
    if [ -e "$dest" ] || [ -L "$dest" ]; then
      ok "seed present, leaving as-is: $dest_rel"
    else
      mkdir -p "$(dirname "$dest")"
      if cp "$src" "$dest"; then
        ok "seeded: $dest_rel"
        SEEDED_COUNT=$((SEEDED_COUNT + 1))
      else
        warn "seed copy failed: $dest_rel"
      fi
    fi
  }

  # Walk the MANIFEST. `#` starts a full-line comment; blank lines are ignored.
  # Every verb branch guards its own arity before touching $2/$3: a malformed
  # line (a known verb with no path argument) must warn and move on, not
  # abort the whole run via an unset positional under `set -u`.
  while IFS= read -r rawline || [ -n "$rawline" ]; do
    set -- $rawline
    [ "$#" -eq 0 ] && continue
    case "$1" in
      '#'*)        continue ;;
      link-dir|link-file)
        if [ "$#" -ge 2 ]; then
          link_entry "$2"
        else
          warn "MANIFEST: '$1' missing path — skipped"
        fi
        ;;
      copy-if-absent)
        if [ "$#" -ge 2 ]; then
          copy_seed "$2" "${3:-$2}"
        else
          warn "MANIFEST: '$1' missing path — skipped"
        fi
        ;;
      *)           warn "MANIFEST: unknown verb '$1' (line ignored)" ;;
    esac
  done < "$MANIFEST"

  # --- runtime dirs the framework expects (untracked data + learned state) --
  mkdir -p "$CLAUDE_DIR/metrics/state"     && ok "metrics/state ready"     || warn "could not create metrics/state"
  mkdir -p "$CLAUDE_DIR/learning/digests"  && ok "learning/digests ready"  || warn "could not create learning/digests"

  # --- record the installed version -----------------------------------------
  if [ -f "$VERSION_FILE" ]; then
    if cp "$VERSION_FILE" "$INSTALLED_VERSION_FILE"; then
      ok "recorded installed version -> learning/.installed-version"
    else
      warn "could not write learning/.installed-version"
    fi
  else
    warn "VERSION file missing at $VERSION_FILE"
  fi

  # --- make shell entrypoints executable THROUGH the repo (they're symlinks) -
  # NOTE: $PAYLOAD/hooks and $PAYLOAD/tools live in THIS repo's working tree —
  # the ~/.claude destinations are symlinks pointing back at them, so chmod
  # here necessarily touches the repo files themselves, not copies. That is
  # deliberate: the framework scripts must be +x at their one true location
  # (the repo), which is what every ~/.claude symlink resolves to.
  find "$PAYLOAD/hooks" -name '*.sh' -exec chmod +x {} \; 2>/dev/null
  find "$PAYLOAD/tools" -name '*.sh' -exec chmod +x {} \; 2>/dev/null
  ok "shell tools under payload/tools/ and payload/hooks/ marked executable"

  # --- Step 2 summary: counts + a loud banner if anything is shadowed -------
  say ""
  say "   Step 2 summary — linked: $LINKED_COUNT   relinked: $RELINKED_COUNT   seeded: $SEEDED_COUNT   shadowed: $SHADOWED_COUNT"
  if [ "$SHADOWED_COUNT" -gt 0 ]; then
    if [ "$SHADOWED_COUNT" -eq 1 ]; then
      SHADOWED_HEADLINE="SHADOWED FRAMEWORK ENTRY — 1 path is NOT active"
    else
      SHADOWED_HEADLINE="SHADOWED FRAMEWORK ENTRIES — $SHADOWED_COUNT paths are NOT active"
    fi
    say ""
    say "   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    say "   $SHADOWED_HEADLINE"
    say "   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    printf '%s' "$SHADOWED_LIST" | while IFS= read -r p; do
      [ -n "$p" ] && say "     - $p"
    done
    say ""
    say "   A real file/dir already exists at each path above, so the framework"
    say "   version was NOT linked there and is NOT active. Move or remove the"
    say "   local file/dir, then re-run install.sh to bring the framework"
    say "   version into effect."
  fi
fi

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

# --- hooks: merge every event group from the fragment (SessionStart plus the
#     metrics events SubagentStop / SessionEnd / PreCompact). A group is added
#     only if its command is not already present (per-command dedup), so re-runs
#     never duplicate and any foreign group/event you already have is untouched.
frag_hooks = frag.get("hooks", {})
if isinstance(frag_hooks, dict) and frag_hooks:
    settings.setdefault("hooks", {})
    if not isinstance(settings["hooks"], dict):
        settings["hooks"] = {}
    for event, frag_groups in frag_hooks.items():
        if not isinstance(frag_groups, list):
            continue
        dest = settings["hooks"].setdefault(event, [])
        if not isinstance(dest, list):
            dest = []
            settings["hooks"][event] = dest

        existing_cmds = set()
        for group in dest:
            if isinstance(group, dict):
                for h in group.get("hooks", []):
                    if isinstance(h, dict) and "command" in h:
                        existing_cmds.add(h["command"])

        for group in frag_groups:
            g = json.loads(json.dumps(group))  # deep copy
            cmds = []
            for h in g.get("hooks", []):
                if isinstance(h, dict) and "command" in h:
                    h["command"] = h["command"].replace("$HOME", real_home)
                    cmds.append(h["command"])
            if not any(c in existing_cmds for c in cmds):
                dest.append(g)
                existing_cmds.update(cmds)
                changed.append("added %s hook" % event)
            else:
                changed.append("%s hook already present" % event)

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

# Report the version delta (current vs. the previously installed marker).
NEW_VERSION="unknown"
[ -f "$VERSION_FILE" ] && NEW_VERSION="$(cat "$VERSION_FILE" 2>/dev/null)"
if [ -n "${PREV_VERSION:-}" ] && [ "${PREV_VERSION:-}" != "$NEW_VERSION" ]; then
  say "   Updated: $PREV_VERSION  ->  $NEW_VERSION"
else
  say "   Installed version: $NEW_VERSION"
fi

cat <<'STEPS'

   Framework files under ~/.claude/ are SYMLINKS into this repo working tree.
   To update later, just pull and re-run — the symlinked content is live at once:
         git -C <this-repo> pull && bash install.sh

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

   To undo everything, run:  bash uninstall.sh
   (add --restore-backups to also restore settings.json / CLAUDE.md from the
   one-time .bak-agentloop copies).
STEPS

say ""
if [ "${SHADOWED_COUNT:-0}" -gt 0 ]; then
  if [ "$SHADOWED_COUNT" -eq 1 ]; then
    say "Done — 1 framework entry was shadowed by a local override this run."
  else
    say "Done — $SHADOWED_COUNT framework entries were shadowed by local overrides this run."
  fi
  say "See the shadowed-entries banner above: those entries are NOT active."
  say "The install itself is still valid and idempotent; re-run it any time."
else
  say "Done. This installer is idempotent — re-run it any time; it will not"
  say "duplicate the hook, re-enable what is already on, or clobber your settings."
fi
exit 0
