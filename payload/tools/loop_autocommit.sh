#!/bin/bash
# loop_autocommit.sh — THE only sanctioned auto-write path for the loop (P5).
#
# Usage:
#   loop_autocommit.sh -m <subject> -b <bodyfile> [-r <rule-id>] <path...>
#
# Commits caller-supplied edits under strict, never-bypassable gates. Paths are
# realpath-resolved and routed to the FRAMEWORK repo (the claude-agent-loop repo
# this script ships in) or the LOCAL repo (~/.claude). A mixed set becomes TWO
# commits — framework first, then local — each suffixed [framework]/[local].
#
# Gate order (all must pass BEFORE any commit lands, so an abort leaves both
# repos exactly as they were):
#   0. Gated lane — settings.json / any hooks/*.sh / a CLAUDE.md sentinel block
#      are REFUSED (exit 4). File a candidates/ stub instead. No override flag
#      exists.
#   1. classify_visibility — every FRAMEWORK-bound path must be GENERIC
#      (CLIENT/UNSURE aborts, exit 3). LOCAL paths are exempt (local-only, no
#      remote — they cannot leak).
#   2. secret_pii_scrub_gate — on the explicit paths (any finding aborts).
#   3. prose_grammar_gate — on any .md paths (any finding aborts).
#   4. lint_registry (any registry/ path) · lint_scales (SCALES.md) ·
#      lint_heuristics (HEURISTICS.md, if the P6 tool exists — probed, else
#      skipped).
#
# On a gate abort: the affected index is reset (the working tree — the caller's
# edit — is preserved), an `autocommit-blocked` NEW row is appended to
# LOOP_THEMES.md, an OS notification fires (macOS only), and the exit is
# non-zero. On success: explicit `git add` (never -A), a `loop:`-prefixed commit
# with a `Co-Authored-By: claude-agent-loop autonomy` trailer, and one appended
# line to AUTO_COMMITS.log. A commit that ADDS a resource (skills/ agents/
# tools/ registry/guides/) fires a new-resource notification. This tool NEVER
# pushes — publication happens only at digest review, by hand.
#
# Exit codes: 0 ok · 1 a safety-floor gate refused · 2 usage error ·
# 3 classify refused a framework path · 4 gated-lane refusal.
#
# macOS bash-3.2 portable; no `set -e` (gate handling manages control flow).
set -u

# --- resolve self + sibling tools (follow the install symlink) --------------
_selfsrc="${BASH_SOURCE[0]}"
while [ -h "$_selfsrc" ]; do
  _dir="$(cd -P "$(dirname "$_selfsrc")" && pwd)"
  _selfsrc="$(readlink "$_selfsrc")"
  case "$_selfsrc" in /*) : ;; *) _selfsrc="$_dir/$_selfsrc" ;; esac
done
SELF="$(cd -P "$(dirname "$_selfsrc")" && pwd)"

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then echo "loop_autocommit: python3 required" >&2; exit 2; fi

CLASSIFY="$SELF/classify_visibility.py"
SCRUB="$SELF/secret_pii_scrub_gate.py"
GRAMMAR="$SELF/prose_grammar_gate.py"
LINT_REGISTRY="$SELF/lint_registry.py"
LINT_SCALES="$SELF/lint_scales.py"
LINT_HEURISTICS="$SELF/lint_heuristics.py"          # P6 — probed before use

realpath_of() { "$PY" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"; }

# Canonicalize the two repo roots so path routing survives symlinked temp dirs
# (macOS /var -> /private/var) and the ~/.claude install symlinks alike.
HOME_CLAUDE="$(realpath_of "$HOME/.claude")"
LEARNING_DIR="$HOME_CLAUDE/learning"
THEMES_FILE="$LEARNING_DIR/LOOP_THEMES.md"
AUTOLOG="$LEARNING_DIR/AUTO_COMMITS.log"

# Framework repo: env override (tests) else the git toplevel of this script.
FRAMEWORK_REPO="${LOOP_FRAMEWORK_REPO:-}"
if [ -z "$FRAMEWORK_REPO" ]; then
  FRAMEWORK_REPO="$(git -C "$SELF" rev-parse --show-toplevel 2>/dev/null || true)"
fi
[ -n "$FRAMEWORK_REPO" ] && FRAMEWORK_REPO="$(realpath_of "$FRAMEWORK_REPO")"

# --- OS notification (Darwin + osascript only; never fails the commit) -------
_notify() {
  msg="$(printf '%s' "$1" | tr -d '"')"
  [ "$(uname 2>/dev/null)" = "Darwin" ] || return 0
  command -v osascript >/dev/null 2>&1 || return 0
  osascript -e "display notification \"$msg\" with title \"claude-agent-loop\"" \
    >/dev/null 2>&1 || true
}

# --- arg parse ---------------------------------------------------------------
SUBJECT=""; BODYFILE=""; RULE_ID="-"
PATHS=""                                            # newline-delimited
while [ "$#" -gt 0 ]; do
  case "$1" in
    -m) SUBJECT="${2:-}"; shift 2 ;;
    -b) BODYFILE="${2:-}"; shift 2 ;;
    -r) RULE_ID="${2:-}"; shift 2 ;;
    --) shift; while [ "$#" -gt 0 ]; do PATHS="$PATHS$1"$'\n'; shift; done ;;
    -*) echo "loop_autocommit: unknown flag $1" >&2; exit 2 ;;
    *)  PATHS="$PATHS$1"$'\n'; shift ;;
  esac
done

if [ -z "$SUBJECT" ] || [ -z "$BODYFILE" ]; then
  echo "loop_autocommit: -m <subject> and -b <bodyfile> are required" >&2; exit 2
fi
if [ ! -r "$BODYFILE" ]; then
  echo "loop_autocommit: bodyfile not readable: $BODYFILE" >&2; exit 2
fi
[ -n "$(printf '%s' "$PATHS" | tr -d '[:space:]')" ] || {
  echo "loop_autocommit: at least one path is required" >&2; exit 2; }

SUBJECT_SANITIZED="$(printf '%s' "$SUBJECT" | tr '\t|' '  ')"

# --- route each path to a lane ----------------------------------------------
FW_PATHS=""; FW_RELS=""; LOCAL_PATHS=""
while IFS= read -r p; do
  [ -n "$p" ] || continue
  abs="$(realpath_of "$p")"
  case "$abs" in
    "$FRAMEWORK_REPO"/*)
      FW_PATHS="$FW_PATHS$abs"$'\n'
      FW_RELS="$FW_RELS${abs#"$FRAMEWORK_REPO"/}"$'\n' ;;
    "$HOME_CLAUDE"/*)
      LOCAL_PATHS="$LOCAL_PATHS$abs"$'\n' ;;
    *)
      echo "loop_autocommit: path is under neither the framework repo nor ~/.claude: $abs" >&2
      exit 2 ;;
  esac
done <<EOF
$PATHS
EOF

have_fw=0;    [ -n "$(printf '%s' "$FW_PATHS" | tr -d '[:space:]')" ] && have_fw=1
have_local=0; [ -n "$(printf '%s' "$LOCAL_PATHS" | tr -d '[:space:]')" ] && have_local=1
mixed=0; [ "$have_fw" -eq 1 ] && [ "$have_local" -eq 1 ] && mixed=1

# --- Gate 0: gated-lane refusal (settings.json / hooks/*.sh / CLAUDE sentinel)
gated_reason=""
while IFS= read -r abs; do
  [ -n "$abs" ] || continue
  base="$(basename "$abs")"
  case "$base" in
    settings.json|settings.local.json)
      case "$abs" in "$HOME_CLAUDE"/*) gated_reason="settings file ($base)"; break ;; esac ;;
  esac
  case "$abs" in
    */hooks/*.sh) gated_reason="hook script ($abs)"; break ;;
  esac
  if [ "$base" = "CLAUDE.md" ] && [ -f "$abs" ] \
     && grep -q 'BEGIN AGENT-LOOP' "$abs" 2>/dev/null; then
    gated_reason="CLAUDE.md sentinel block ($abs)"; break
  fi
done <<EOF
$FW_PATHS$LOCAL_PATHS
EOF
if [ -n "$gated_reason" ]; then
  echo "loop_autocommit: REFUSED — the gated lane covers $gated_reason." >&2
  echo "loop_autocommit: file a stub in ~/.claude/registry/candidates/ for owner review instead." >&2
  exit 4
fi

# --- abort helper: reset indexes, log a blocked theme row, notify, exit ------
mkdir -p "$LEARNING_DIR" 2>/dev/null || true
block() {
  repo_base="$1"; gate="$2"; code="$3"
  # Unstage only our paths in both repos; the working tree is untouched.
  [ "$have_fw" -eq 1 ] && printf '%s' "$FW_PATHS" | while IFS= read -r a; do
    [ -n "$a" ] && git -C "$FRAMEWORK_REPO" reset -q HEAD -- "$a" 2>/dev/null || true
  done
  [ "$have_local" -eq 1 ] && printf '%s' "$LOCAL_PATHS" | while IFS= read -r a; do
    [ -n "$a" ] && git -C "$HOME_CLAUDE" reset -q HEAD -- "$a" 2>/dev/null || true
  done
  today="$(date -u +%Y-%m-%d)"
  note="gate $gate refused $SUBJECT_SANITIZED"
  printf '| NEW | %s | %s | autocommit-blocked | %s | - |\n' \
    "$today" "$repo_base" "$note" >> "$THEMES_FILE"
  _notify "gate blocked: $gate refused $SUBJECT_SANITIZED"
  exit "$code"
}

# --- safety-floor runners (no staging, no commit — read-only checks) --------
# Collect a lane's .md paths and registry roots for the linters.
md_paths_of() { printf '%s' "$1" | while IFS= read -r a; do
  case "$a" in *.md) [ -n "$a" ] && printf '%s\n' "$a" ;; esac; done; }

run_floor() {
  lane="$1"; paths="$2"; rels="$3"; repo_base="$4"
  [ -n "$(printf '%s' "$paths" | tr -d '[:space:]')" ] || return 0

  # 1. classify — framework paths must all be GENERIC.
  if [ "$lane" = "framework" ]; then
    rel_args=""
    while IFS= read -r r; do [ -n "$r" ] && rel_args="$rel_args\"$r\" "; done <<EOF
$rels
EOF
    if ! ( cd "$FRAMEWORK_REPO" && eval "\"$PY\" \"$CLASSIFY\" $rel_args" ) >&2; then
      block "$repo_base" "classify" 3
    fi
  fi

  # 2. scrub — explicit paths.
  path_args=""
  while IFS= read -r a; do [ -n "$a" ] && path_args="$path_args\"$a\" "; done <<EOF
$paths
EOF
  if ! eval "\"$PY\" \"$SCRUB\" $path_args" >&2; then
    block "$repo_base" "scrub" 1
  fi

  # 3. grammar — any .md paths.
  md="$(md_paths_of "$paths")"
  if [ -n "$(printf '%s' "$md" | tr -d '[:space:]')" ]; then
    md_args=""
    while IFS= read -r a; do [ -n "$a" ] && md_args="$md_args\"$a\" "; done <<EOF
$md
EOF
    if ! eval "\"$PY\" \"$GRAMMAR\" $md_args" >&2; then
      block "$repo_base" "grammar" 1
    fi
  fi

  # 4. linters — registry root(s), SCALES.md, HEURISTICS.md (P6, probed).
  reg_roots=""
  while IFS= read -r a; do
    [ -n "$a" ] || continue
    case "$a" in
      */registry/*)
        root="${a%%/registry/*}/registry"
        case "$reg_roots" in *"$root"$'\n'*) : ;; *) reg_roots="$reg_roots$root"$'\n' ;; esac ;;
    esac
    case "$(basename "$a")" in
      SCALES.md)
        if ! "$PY" "$LINT_SCALES" "$a" >&2; then block "$repo_base" "lint-scales" 1; fi ;;
      HEURISTICS.md)
        if [ -f "$LINT_HEURISTICS" ]; then
          if ! "$PY" "$LINT_HEURISTICS" "$a" >&2; then block "$repo_base" "lint-heuristics" 1; fi
        fi ;;
    esac
  done <<EOF
$paths
EOF
  while IFS= read -r root; do
    [ -n "$root" ] || continue
    if ! "$PY" "$LINT_REGISTRY" "$root" >&2; then block "$repo_base" "lint-registry" 1; fi
  done <<EOF
$reg_roots
EOF
}

FW_BASE="$(basename "$FRAMEWORK_REPO")"
LOCAL_BASE="$(basename "$HOME_CLAUDE")"

# Run BOTH lanes' floors up front. Any failure calls block() and exits, so
# neither repo is ever committed on a partial pass.
[ "$have_fw" -eq 1 ]    && run_floor framework "$FW_PATHS" "$FW_RELS" "$FW_BASE"
[ "$have_local" -eq 1 ] && run_floor local     "$LOCAL_PATHS" "" "$LOCAL_BASE"

# --- commit a lane (all gates already passed) --------------------------------
iso_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

commit_lane() {
  repo="$1"; paths="$2"; suffix="$3"; repo_base="$4"

  # Stage the explicit paths only — never -A.
  while IFS= read -r a; do
    [ -n "$a" ] && git -C "$repo" add -- "$a"
  done <<EOF
$paths
EOF

  # New-resource detection: an ADDED file under skills/ agents/ tools/ or
  # registry/guides/ (repo-relative), BEFORE the commit.
  added="$(git -C "$repo" diff --cached --name-only --diff-filter=A 2>/dev/null)"
  new_resource=0
  while IFS= read -r f; do
    case "$f" in
      skills/*|*/skills/*|agents/*|*/agents/*|tools/*|*/tools/*|\
registry/guides/*|*/registry/guides/*) new_resource=1 ;;
    esac
  done <<EOF
$added
EOF

  # Build the commit message: subject (+suffix), body, autonomy trailer.
  msgfile="$(mktemp 2>/dev/null || mktemp -t loopmsg)"
  {
    printf 'loop: %s%s\n\n' "$SUBJECT" "$suffix"
    cat "$BODYFILE"
    printf '\n\nCo-Authored-By: claude-agent-loop autonomy\n'
  } > "$msgfile"
  git -C "$repo" commit -q -F "$msgfile"
  rc=$?
  rm -f "$msgfile"
  if [ "$rc" -ne 0 ]; then
    echo "loop_autocommit: commit failed in $repo_base" >&2
    return 1
  fi

  sha="$(git -C "$repo" rev-parse HEAD)"
  full_subject="loop: $SUBJECT$suffix"
  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$(iso_now)" "$repo_base" "$sha" \
    "$(printf '%s' "$full_subject" | tr '\t' ' ')" "$RULE_ID" >> "$AUTOLOG"

  [ "$new_resource" -eq 1 ] && _notify "new resource auto-created in $repo_base: $full_subject"
  echo "loop_autocommit: committed $sha in $repo_base ($full_subject)"
  return 0
}

fw_suffix=""; local_suffix=""
if [ "$mixed" -eq 1 ]; then fw_suffix=" [framework]"; local_suffix=" [local]"; fi

# Framework first, then local.
[ "$have_fw" -eq 1 ]    && commit_lane "$FRAMEWORK_REPO" "$FW_PATHS"    "$fw_suffix"    "$FW_BASE"
[ "$have_local" -eq 1 ] && commit_lane "$HOME_CLAUDE"    "$LOCAL_PATHS" "$local_suffix" "$LOCAL_BASE"

exit 0
