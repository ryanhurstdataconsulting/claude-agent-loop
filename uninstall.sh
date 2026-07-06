#!/usr/bin/env bash
# =============================================================================
# claude-agent-loop uninstaller
# -----------------------------------------------------------------------------
# Removes ONLY what install.sh added, and nothing else:
#   - the framework symlinks under ~/.claude/ that resolve back into THIS repo
#     (MANIFEST link-dir / link-file entries)
#   - the AGENT-LOOP sentinel block appended to ~/.claude/CLAUDE.md
#   - our SessionStart hook group in ~/.claude/settings.json (matched by the
#     exact command install.sh writes — the same dedup key)
#
# It NEVER removes real files/dirs you placed at a framework path, NEVER removes
# copy-if-absent outputs (the learning/ and registry/ seeds — your learned
# state), and NEVER touches ~/.claude/metrics/ or the rest of ~/.claude/learning/.
#
#   Usage:  bash uninstall.sh [--restore-backups]
#
#   --restore-backups   Additionally restore settings.json and CLAUDE.md from
#                       the one-time .bak-agentloop copies install.sh made
#                       (a full pre-install rewind of those two files).
#
# Idempotent: running it twice is safe. Like install.sh it does NOT `set -e`.
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD="$SCRIPT_DIR/payload"
CLAUDE_DIR="$HOME/.claude"
MANIFEST="$PAYLOAD/MANIFEST"

RESTORE_BACKUPS=0
for arg in "$@"; do
  case "$arg" in
    --restore-backups) RESTORE_BACKUPS=1 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) printf '   [!!] unknown argument: %s (ignored)\n' "$arg" ;;
  esac
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
ok()   { printf '   [ok] %s\n' "$*"; }
warn() { printf '   [!!] %s\n' "$*"; }

say "claude-agent-loop uninstaller"
say "Target: $CLAUDE_DIR"
say "Source: $SCRIPT_DIR  (only symlinks resolving into here are removed)"

PY=""
if command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
fi

removed_links=0
kept_real=0

# ---------------------------------------------------------------------------
step "Step 1 — remove framework symlinks that resolve into this repo"

if [ ! -f "$MANIFEST" ]; then
  warn "MANIFEST not found at $MANIFEST — cannot enumerate framework links."
else
  # Only link-dir / link-file entries are ours to remove. copy-if-absent
  # outputs (seeds) diverge locally and are left strictly alone.
  while IFS= read -r rawline || [ -n "$rawline" ]; do
    set -- $rawline
    [ "$#" -eq 0 ] && continue
    case "$1" in
      link-dir|link-file) : ;;
      *) continue ;;
    esac
    rel="$2"
    dest="$CLAUDE_DIR/$rel"
    if [ -L "$dest" ]; then
      tgt="$(readlink "$dest")"
      case "$tgt" in
        "$SCRIPT_DIR"/*)
          if rm -f "$dest"; then
            ok "removed link: $rel"
            removed_links=$((removed_links + 1))
          else
            warn "could not remove link: $rel"
          fi
          ;;
        *)
          warn "symlink points outside this repo, left as-is: $rel -> $tgt"
          ;;
      esac
    elif [ -e "$dest" ]; then
      ok "real file/dir (not ours), left as-is: $rel"
      kept_real=$((kept_real + 1))
    else
      ok "already absent: $rel"
    fi
  done < "$MANIFEST"
fi

# ---------------------------------------------------------------------------
step "Step 2 — CLAUDE.md"

CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
CLAUDE_BAK="$CLAUDE_MD.bak-agentloop"

if [ "$RESTORE_BACKUPS" -eq 1 ] && [ -f "$CLAUDE_BAK" ]; then
  if cp "$CLAUDE_BAK" "$CLAUDE_MD"; then
    ok "restored CLAUDE.md from $(basename "$CLAUDE_BAK")"
  else
    warn "could not restore CLAUDE.md from backup"
  fi
elif [ -z "$PY" ]; then
  warn "python3 not found — cannot strip the AGENT-LOOP block from CLAUDE.md by machine."
  warn "Delete the block between <!-- BEGIN AGENT-LOOP --> and <!-- END AGENT-LOOP --> by hand."
else
  "$PY" - "$CLAUDE_MD" <<'PY'
import sys

target = sys.argv[1]
BEGIN = "<!-- BEGIN AGENT-LOOP -->"
END = "<!-- END AGENT-LOOP -->"

try:
    with open(target) as f:
        existing = f.read()
except FileNotFoundError:
    print("   [ok] CLAUDE.md: none present")
    sys.exit(0)

if BEGIN in existing and END in existing:
    start = existing.index(BEGIN)
    end = existing.index(END) + len(END)
    head = existing[:start]
    tail = existing[end:]
    # Collapse the leftover blank line at the seam so we don't leave a double
    # blank where the block used to be.
    h = head.rstrip("\n")
    t = tail.lstrip("\n")
    if h and t:
        new = h + "\n\n" + t
    elif h:
        new = h + "\n"
    elif t:
        new = t
    else:
        new = ""
    with open(target, "w") as f:
        f.write(new)
    print("   [ok] CLAUDE.md: removed AGENT-LOOP block")
else:
    print("   [ok] CLAUDE.md: no AGENT-LOOP block present")
PY
fi

# ---------------------------------------------------------------------------
step "Step 3 — settings.json (SessionStart hook group)"

SETTINGS="$CLAUDE_DIR/settings.json"
SETTINGS_BAK="$SETTINGS.bak-agentloop"

if [ "$RESTORE_BACKUPS" -eq 1 ] && [ -f "$SETTINGS_BAK" ]; then
  if cp "$SETTINGS_BAK" "$SETTINGS"; then
    ok "restored settings.json from $(basename "$SETTINGS_BAK")"
  else
    warn "could not restore settings.json from backup"
  fi
elif [ -z "$PY" ]; then
  warn "python3 not found — cannot strip our hook group from settings.json by machine."
elif [ ! -f "$SETTINGS" ]; then
  ok "no settings.json present"
else
  "$PY" - "$SETTINGS" "$HOME" <<'PY'
import json, os, sys

settings_path, real_home = sys.argv[1], sys.argv[2]
our_cmd = real_home + "/.claude/hooks/inject-resource-loop.sh"

try:
    with open(settings_path) as f:
        settings = json.load(f)
except FileNotFoundError:
    print("   [ok] settings: none present")
    sys.exit(0)
except ValueError as e:
    print("   [!!] settings.json is not valid JSON (%s) — not touching it." % e,
          file=sys.stderr)
    sys.exit(0)

if not isinstance(settings, dict):
    print("   [!!] settings.json is not a JSON object — not touching it.",
          file=sys.stderr)
    sys.exit(0)

hooks = settings.get("hooks")
removed = 0
if isinstance(hooks, dict) and isinstance(hooks.get("SessionStart"), list):
    new_ss = []
    for group in hooks["SessionStart"]:
        if not isinstance(group, dict):
            new_ss.append(group)
            continue
        entries = group.get("hooks", [])
        kept = [h for h in entries
                if not (isinstance(h, dict) and h.get("command") == our_cmd)]
        if len(kept) != len(entries):
            removed += len(entries) - len(kept)
        if kept:
            group["hooks"] = kept
            new_ss.append(group)
        # else: the group held only our hook -> drop the whole group
    if new_ss:
        hooks["SessionStart"] = new_ss
    else:
        del hooks["SessionStart"]
        if not hooks:
            del settings["hooks"]

if removed:
    tmp = settings_path + ".hdctmp"
    with open(tmp, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    os.replace(tmp, settings_path)
    print("   [ok] settings: removed our SessionStart hook (%d entr%s), other settings kept"
          % (removed, "y" if removed == 1 else "ies"))
else:
    print("   [ok] settings: our SessionStart hook not present (nothing to remove)")
PY
fi

# ---------------------------------------------------------------------------
step "SUMMARY"
say "   Removed: $removed_links framework symlink(s)."
say "   Left in place: $kept_real real override(s), all copy-if-absent seeds,"
say "                  ~/.claude/learning/ (incl. .installed-version) and ~/.claude/metrics/."
if [ "$RESTORE_BACKUPS" -eq 1 ]; then
  say "   --restore-backups: settings.json and CLAUDE.md rewound to their .bak-agentloop copies where present."
else
  say "   The AGENT-LOOP block and our SessionStart hook group were stripped in place."
fi
say ""
say "Done. Safe to run again — a second run finds nothing left to remove."
exit 0
