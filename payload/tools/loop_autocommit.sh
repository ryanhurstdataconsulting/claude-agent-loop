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
#   0. Gated lane — REFUSED (exit 4), routed to candidates/, no override flag:
#      - installed artifacts: ~/.claude/settings*.json, any hooks/* path, a
#        CLAUDE.md sentinel block;
#      - framework SOURCES of those artifacts (they BECOME gated files on
#        install): any path under a fragments/ dir, any settings*.json basename
#        anywhere, any path under a hooks/ dir REGARDLESS of extension.
#   1. classify_visibility — every FRAMEWORK-bound path must be GENERIC
#      (CLIENT/UNSURE aborts, exit 3). A framework path that cannot be scanned
#      (a NUL-byte binary) is refused too. LOCAL paths are exempt (local-only,
#      no remote — they cannot leak).
#   2. secret_pii_scrub_gate — on the explicit paths (any finding aborts).
#   3. prose_grammar_gate — on any .md paths (any finding aborts).
#   4. lint_registry (any registry/ path) · lint_scales (SCALES.md) ·
#      lint_heuristics (HEURISTICS.md, if the P6 tool exists — probed, else
#      skipped).
#   5. MESSAGE channel — the commit subject+body are content too. For a
#      FRAMEWORK commit they must classify GENERIC and pass the scrub gate;
#      for a LOCAL commit they are scrub-scanned (no remote to leak to, but a
#      secret still must not be logged). A CLIENT/UNSURE/finding aborts.
#
# On a gate abort: the affected index is reset (the working tree — the caller's
# edit — is preserved), an `autocommit-blocked` NEW row is appended to
# LOOP_THEMES.md, an OS notification fires (macOS only), and the exit is
# non-zero. On success: explicit `git add` (never -A) plus a pathspec (`--only`)
# commit so any pre-staged entry is left untouched, a `loop:`-prefixed commit
# with a `Co-Authored-By: claude-agent-loop autonomy` trailer, and one appended
# line to AUTO_COMMITS.log. Each ledger line carries a trailing GROUP id (the
# framework sha's first 8 chars) shared by both halves of a mixed commit so
# loop_rollback can undo a two-lane pair as one unit. A commit that ADDS a
# resource (skills/ agents/ tools/ registry/guides/) fires a new-resource
# notification. This tool NEVER pushes — publication happens only at digest
# review, by hand.
#
# Two-lane honesty: the two commits are as atomic as two repos allow. If the
# first/only lane's commit fails, nothing lands and the exit is non-zero. If the
# framework lane committed but the local lane then fails, a PARTIAL line is
# logged naming the orphaned framework sha, a notification fires, and the exit is
# non-zero with a `loop_rollback.sh <sha>` hint — this tool never reports success
# for a commit that did not land.
#
# Exit codes: 0 ok · 1 a safety-floor gate refused · 2 usage error ·
# 3 classify refused a framework path · 4 gated-lane refusal ·
# 5 a requested commit failed and nothing landed ·
# 6 partial: the framework lane committed but the local lane failed.
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

# True (exit 0) when the file at $1 contains a NUL byte — a binary blob the
# text-oriented visibility/scrub scanners cannot inspect. Unreadable files exit
# non-zero here and are handled by the classifier's unreadable path instead.
has_nul() {
  "$PY" -c 'import sys
try:
    d = open(sys.argv[1], "rb").read()
except OSError:
    sys.exit(1)
sys.exit(0 if b"\x00" in d else 1)' "$1" 2>/dev/null
}

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

# R1: snapshot the body once, at scan time (below), and commit from THIS
# snapshot — never a fresh $BODYFILE re-read. A bodyfile mutated between the
# up-front message scan and the commit therefore cannot slip an UNSCANNED body
# into the committed message. Cleaned up on every exit path.
BODY_SNAPSHOT=""
_cleanup_snapshot() { [ -n "$BODY_SNAPSHOT" ] && rm -f "$BODY_SNAPSHOT" 2>/dev/null || true; }
trap _cleanup_snapshot EXIT INT TERM

# Collapse newline / tab / pipe in the subject to spaces. A raw newline would
# split the tab-delimited AUTO_COMMITS.log record (dropping the commit from the
# digest review surface) and would spill past the git subject line. This one
# sanitized form is used for BOTH the git commit subject and the logged line.
SUBJECT_SANITIZED="$(printf '%s' "$SUBJECT" | tr '\n\t|' '   ')"

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

# --- Gate 0: gated-lane refusal ---------------------------------------------
# Refuses both the INSTALLED gated artifacts and the framework SOURCES that
# become them on install. These stay owner-approved via a candidates/ stub.
gated_reason=""
while IFS= read -r abs; do
  [ -n "$abs" ] || continue
  base="$(basename "$abs")"
  # (a) any settings*.json basename, anywhere (installed file OR its fragment).
  case "$base" in
    settings*.json) gated_reason="settings file ($base)"; break ;;
  esac
  # (b) any path under a fragments/ dir — the install-time templates that BECOME
  #     settings.json / the CLAUDE.md sentinel block (catches
  #     settings.fragment.json AND CLAUDE.starter.md with no doc false-positive).
  case "$abs" in
    */fragments/*) gated_reason="framework fragment source ($abs)"; break ;;
  esac
  # (c) any path under a hooks/ dir, REGARDLESS of extension (a hooks/*.py or an
  #     extensionless hook slipped past the old */hooks/*.sh rule).
  case "$abs" in
    */hooks/*) gated_reason="hook path ($abs)"; break ;;
  esac
  # (d) an installed CLAUDE.md carrying the agent-loop sentinel block.
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

# --- unstage a lane's own paths (working tree left untouched) ----------------
clean_staged() {
  repo="$1"; paths="$2"
  printf '%s' "$paths" | while IFS= read -r a; do
    [ -n "$a" ] && git -C "$repo" reset -q HEAD -- "$a" 2>/dev/null || true
  done
}

# --- abort helper: reset indexes, log a blocked theme row, notify, exit ------
mkdir -p "$LEARNING_DIR" 2>/dev/null || true
block() {
  repo_base="$1"; gate="$2"; code="$3"
  # Scoped cleanup. This PRESERVES the loop's working-tree edit (the file
  # content stays on disk, untouched) and DISCARDS only the staged index entry
  # for a loop-TARGETED path — including a human's staged version of that same
  # path, because the loop owns its declared paths by contract. No other staged
  # entry, and no working-tree file, is touched.
  [ "$have_fw" -eq 1 ]    && clean_staged "$FRAMEWORK_REPO" "$FW_PATHS"
  [ "$have_local" -eq 1 ] && clean_staged "$HOME_CLAUDE" "$LOCAL_PATHS"
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

  # 1. classify — framework paths must all be GENERIC, and each must be
  #    text-scannable (a NUL-byte binary cannot be inspected → refuse).
  if [ "$lane" = "framework" ]; then
    while IFS= read -r a; do
      [ -n "$a" ] || continue
      if has_nul "$a"; then block "$repo_base" "binary" 3; fi
    done <<EOF
$paths
EOF
    rel_argv=()
    while IFS= read -r r; do
      [ -n "$r" ] && rel_argv[${#rel_argv[@]}]="$r"
    done <<EOF
$rels
EOF
    if [ "${#rel_argv[@]}" -gt 0 ]; then
      if ! ( cd "$FRAMEWORK_REPO" && "$PY" "$CLASSIFY" "${rel_argv[@]}" ) >&2; then
        block "$repo_base" "classify" 3
      fi
    fi
  fi

  # 2. scrub — explicit paths (argv array; no eval on constructed strings).
  path_argv=()
  while IFS= read -r a; do
    [ -n "$a" ] && path_argv[${#path_argv[@]}]="$a"
  done <<EOF
$paths
EOF
  if [ "${#path_argv[@]}" -gt 0 ]; then
    if ! "$PY" "$SCRUB" "${path_argv[@]}" >&2; then
      block "$repo_base" "scrub" 1
    fi
  fi

  # 3. grammar — any .md paths.
  md="$(md_paths_of "$paths")"
  md_argv=()
  while IFS= read -r a; do
    [ -n "$a" ] && md_argv[${#md_argv[@]}]="$a"
  done <<EOF
$md
EOF
  if [ "${#md_argv[@]}" -gt 0 ]; then
    if ! "$PY" "$GRAMMAR" "${md_argv[@]}" >&2; then
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

# --- message-channel scan (the subject + body are committed content too) -----
# Compose subject+body into a temp file (in TMPDIR, removed after). For a
# framework commit the message must classify GENERIC; for either lane it must
# pass the scrub gate. classify runs from the temp dir on the basename so the
# temp path itself (which may sit under /Users on some machines) never
# self-flags a structural signal.
scan_message() {
  lane="$1"; repo_base="$2"
  mtdir="${TMPDIR:-/tmp}"
  # R1: capture the exact body bytes ONCE. Both the scan (here) and the commit
  # (commit_lane) read this snapshot, so what is scanned is byte-identical to
  # what is committed even if $BODYFILE changes afterward.
  if [ -z "$BODY_SNAPSHOT" ]; then
    BODY_SNAPSHOT="$(mktemp "$mtdir/loopbodysnap.XXXXXX" 2>/dev/null || mktemp -t loopbodysnap)"
    cat "$BODYFILE" > "$BODY_SNAPSHOT"
  fi
  msgtmp="$(mktemp "$mtdir/loopmsg.XXXXXX" 2>/dev/null || mktemp -t loopmsg)"
  {
    printf '%s\n\n' "$SUBJECT"
    cat "$BODY_SNAPSHOT"
  } > "$msgtmp"
  mbase="$(basename "$msgtmp")"; mdir="$(dirname "$msgtmp")"
  if [ "$lane" = "framework" ]; then
    if ! ( cd "$mdir" && "$PY" "$CLASSIFY" "$mbase" ) >&2; then
      rm -f "$msgtmp"; block "$repo_base" "message-classify" 3
    fi
  fi
  if ! "$PY" "$SCRUB" "$msgtmp" >&2; then
    rm -f "$msgtmp"; block "$repo_base" "message-scrub" 1
  fi
  rm -f "$msgtmp"
}

FW_BASE="$(basename "$FRAMEWORK_REPO")"
LOCAL_BASE="$(basename "$HOME_CLAUDE")"

# Run BOTH lanes' floors (including the message-channel scan) up front. Any
# failure calls block() and exits, so neither repo is ever committed on a
# partial pass.
[ "$have_fw" -eq 1 ]    && run_floor framework "$FW_PATHS" "$FW_RELS" "$FW_BASE"
[ "$have_local" -eq 1 ] && run_floor local     "$LOCAL_PATHS" "" "$LOCAL_BASE"
[ "$have_fw" -eq 1 ]    && scan_message framework "$FW_BASE"
[ "$have_local" -eq 1 ] && scan_message local     "$LOCAL_BASE"

# --- commit a lane (all gates already passed) --------------------------------
iso_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Sets LAST_SHA / LAST_GROUP on success. Returns:
#   0 committed · 1 git commit failed (infra) · 2 staged-scan (AM1) leak.
# On any non-zero return the lane's own staged paths are unstaged first.
LAST_SHA=""; LAST_GROUP=""
commit_lane() {
  repo="$1"; paths="$2"; suffix="$3"; repo_base="$4"; group_in="$5"

  # Stage the explicit paths only — never -A. Build the repo-relative pathspec
  # in the same pass for the --only commit below.
  ps_argv=()
  while IFS= read -r a; do
    [ -n "$a" ] || continue
    git -C "$repo" add -- "$a"
    ps_argv[${#ps_argv[@]}]="${a#"$repo"/}"
  done <<EOF
$paths
EOF

  # AM1 (TOCTOU): re-scan the STAGED index for secrets before committing, as a
  # belt-and-suspenders against a file mutated between the up-front floor scan
  # and this git add. Any finding → unstage and refuse (never silently commit).
  if ! ( cd "$repo" && "$PY" "$SCRUB" ) >&2; then
    clean_staged "$repo" "$paths"
    return 2
  fi

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

  # Build the commit message: sanitized subject (+suffix), body, autonomy
  # trailer. R1: the body comes from the scanned snapshot (byte-identical to
  # what the message channel gated), NOT a fresh $BODYFILE re-read. Fall back to
  # $BODYFILE only in the theoretical case commit_lane runs before any scan.
  body_src="$BODY_SNAPSHOT"; [ -n "$body_src" ] || body_src="$BODYFILE"
  msgfile="$(mktemp 2>/dev/null || mktemp -t loopmsg)"
  {
    printf 'loop: %s%s\n\n' "$SUBJECT_SANITIZED" "$suffix"
    cat "$body_src"
    printf '\n\nCo-Authored-By: claude-agent-loop autonomy\n'
  } > "$msgfile"
  # Pathspec (--only) commit: commit EXACTLY these paths and leave any other
  # pre-staged index entry (human or concurrent-loop) untouched.
  if [ "${#ps_argv[@]}" -gt 0 ]; then
    git -C "$repo" commit -q -F "$msgfile" -- "${ps_argv[@]}"
  else
    git -C "$repo" commit -q -F "$msgfile"
  fi
  rc=$?
  rm -f "$msgfile"
  if [ "$rc" -ne 0 ]; then
    clean_staged "$repo" "$paths"
    echo "loop_autocommit: commit failed in $repo_base" >&2
    return 1
  fi

  sha="$(git -C "$repo" rev-parse HEAD)"
  LAST_SHA="$sha"
  # Group id: caller-supplied (the framework sha shared across a mixed pair) or,
  # for a single-lane / first-lane commit, this commit's own sha prefix.
  group="$group_in"
  [ -n "$group" ] || group="$(printf '%s' "$sha" | cut -c1-8)"
  LAST_GROUP="$group"
  full_subject="loop: $SUBJECT_SANITIZED$suffix"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(iso_now)" "$repo_base" "$sha" \
    "$(printf '%s' "$full_subject" | tr '\t' ' ')" "$RULE_ID" "$group" >> "$AUTOLOG"

  [ "$new_resource" -eq 1 ] && _notify "new resource auto-created in $repo_base: $full_subject"
  echo "loop_autocommit: committed $sha in $repo_base ($full_subject)"
  return 0
}

fw_suffix=""; local_suffix=""
if [ "$mixed" -eq 1 ]; then fw_suffix=" [framework]"; local_suffix=" [local]"; fi

# Framework first, then local. Capture each lane's outcome; never exit 0 unless
# every requested commit actually landed.
FW_COMMITTED=0; FW_SHA=""; GROUP=""
if [ "$have_fw" -eq 1 ]; then
  commit_lane "$FRAMEWORK_REPO" "$FW_PATHS" "$fw_suffix" "$FW_BASE" ""
  rc=$?
  case "$rc" in
    0) FW_COMMITTED=1; FW_SHA="$LAST_SHA"; GROUP="$LAST_GROUP" ;;
    2) block "$FW_BASE" "staged-scrub" 1 ;;      # AM1 leak; nothing has landed
    *) echo "loop_autocommit: framework lane did not commit; nothing committed" >&2
       exit 5 ;;
  esac
fi

if [ "$have_local" -eq 1 ]; then
  commit_lane "$HOME_CLAUDE" "$LOCAL_PATHS" "$local_suffix" "$LOCAL_BASE" "$GROUP"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    if [ "$FW_COMMITTED" -eq 1 ]; then
      # The framework half already landed → be HONEST: record a PARTIAL line
      # naming the orphaned sha, notify, and point the owner at rollback.
      printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$(iso_now)" "$FW_BASE" "$FW_SHA" \
        "PARTIAL framework $FW_SHA orphaned (local lane failed)" "-" "$GROUP" >> "$AUTOLOG"
      _notify "PARTIAL: framework $FW_SHA committed but the local lane failed — run loop_rollback.sh $FW_SHA"
      echo "loop_autocommit: PARTIAL — framework commit $FW_SHA landed but the local lane failed." >&2
      echo "loop_autocommit: to undo the orphaned framework half, run: loop_rollback.sh $FW_SHA" >&2
      exit 6
    fi
    # Local-only commit failed → nothing landed.
    if [ "$rc" -eq 2 ]; then block "$LOCAL_BASE" "staged-scrub" 1; fi
    echo "loop_autocommit: local lane did not commit; nothing committed" >&2
    exit 5
  fi
fi

exit 0
