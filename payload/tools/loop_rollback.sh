#!/bin/bash
# loop_rollback.sh — revert a loop-authored auto-commit (P5).
#
# Usage:
#   loop_rollback.sh <sha> [--repo framework|local]
#   loop_rollback.sh --last [N]
#
# Reverts a single commit by sha (default repo: framework), or the most recent N
# loop-commit GROUPS recorded in AUTO_COMMITS.log across both repos, newest
# group first. A mixed two-lane commit writes two ledger lines that share a
# GROUP id (the 6th tab field); `--last N` operates on N logical GROUPS, so it
# reverts BOTH halves of such a pair together — a single-lane commit is a group
# of one. Uses `git revert --no-edit`. It REFUSES (exit 4) to revert any commit
# whose
# subject lacks the `loop: ` prefix — human commits are never touched by the
# loop's rollback. After a revert that touched the registry or SCALES.md, the
# matching linter is re-run as a guard (a lint failure is WARNED, never
# undoes the revert). Each revert appends `REVERT <revert-sha> of <original-sha>`
# to AUTO_COMMITS.log. This tool NEVER pushes.
#
# Exit codes: 0 ok · 2 usage error · 4 refused (target is not a loop: commit).
#
# macOS bash-3.2 portable; no `set -e`.
set -u

_selfsrc="${BASH_SOURCE[0]}"
while [ -h "$_selfsrc" ]; do
  _dir="$(cd -P "$(dirname "$_selfsrc")" && pwd)"
  _selfsrc="$(readlink "$_selfsrc")"
  case "$_selfsrc" in /*) : ;; *) _selfsrc="$_dir/$_selfsrc" ;; esac
done
SELF="$(cd -P "$(dirname "$_selfsrc")" && pwd)"

PY="$(command -v python3 || true)"
realpath_of() {
  if [ -n "$PY" ]; then "$PY" -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$1"
  else (cd "$1" 2>/dev/null && pwd) || printf '%s' "$1"; fi
}

LINT_REGISTRY="$SELF/lint_registry.py"
LINT_SCALES="$SELF/lint_scales.py"

HOME_CLAUDE="$(realpath_of "$HOME/.claude")"
LEARNING_DIR="$HOME_CLAUDE/learning"
AUTOLOG="$LEARNING_DIR/AUTO_COMMITS.log"

FRAMEWORK_REPO="${LOOP_FRAMEWORK_REPO:-}"
if [ -z "$FRAMEWORK_REPO" ]; then
  FRAMEWORK_REPO="$(git -C "$SELF" rev-parse --show-toplevel 2>/dev/null || true)"
fi
[ -n "$FRAMEWORK_REPO" ] && FRAMEWORK_REPO="$(realpath_of "$FRAMEWORK_REPO")"

FW_BASE="$(basename "$FRAMEWORK_REPO")"
LOCAL_BASE="$(basename "$HOME_CLAUDE")"

iso_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# --- arg parse ---------------------------------------------------------------
MODE="single"; SHA=""; REPO_SEL="framework"; LAST_N=1
while [ "$#" -gt 0 ]; do
  case "$1" in
    --last) MODE="last"
            case "${2:-}" in ''|-*) LAST_N=1 ;; *) LAST_N="$2"; shift ;; esac
            shift ;;
    --repo) REPO_SEL="${2:-framework}"; shift 2 ;;
    -*) echo "loop_rollback: unknown flag $1" >&2; exit 2 ;;
    *)  SHA="$1"; shift ;;
  esac
done

repo_root_for_sel() {
  case "$1" in
    framework) printf '%s' "$FRAMEWORK_REPO" ;;
    local)     printf '%s' "$HOME_CLAUDE" ;;
    *) return 1 ;;
  esac
}

repo_root_for_base() {
  # Map a logged repo-basename back to a repo root.
  if [ "$1" = "$FW_BASE" ]; then printf '%s' "$FRAMEWORK_REPO"
  elif [ "$1" = "$LOCAL_BASE" ]; then printf '%s' "$HOME_CLAUDE"
  else return 1; fi
}

# Re-lint guard after a revert: warn on failure, never undo the revert. A
# revert that restored the pre-commit registry/scales state must still leave the
# linters clean; if it does not, the human is warned but the revert stands.
relint_touched() {
  repo="$1"; sha="$2"
  [ -n "$PY" ] || return 0
  touched="$(git -C "$repo" diff-tree --no-commit-id --name-only -r "$sha" 2>/dev/null)"
  seen_reg=""
  printf '%s\n' "$touched" | while IFS= read -r f; do
    [ -n "$f" ] || continue
    case "$f" in
      registry/*|*/registry/*)
        reg_root="$repo/${f%%/registry/*}/registry"
        if [ "$seen_reg" != "$reg_root" ]; then
          seen_reg="$reg_root"
          "$PY" "$LINT_REGISTRY" "$reg_root" >&2 \
            || echo "loop_rollback: WARNING lint_registry failed after revert (not undone)" >&2
        fi ;;
    esac
    case "$(basename "$f")" in
      SCALES.md)
        "$PY" "$LINT_SCALES" "$repo/$f" >&2 \
          || echo "loop_rollback: WARNING lint_scales failed after revert (not undone)" >&2 ;;
    esac
  done
}

# Revert one sha in one repo. Refuses a non-loop commit (exit 4 in single mode;
# in --last mode a stray non-loop sha is skipped with a warning). Returns 0 on a
# successful revert.
do_revert() {
  repo="$1"; sha="$2"; strict="$3"
  subject="$(git -C "$repo" log -1 --format=%s "$sha" 2>/dev/null)"
  if [ -z "$subject" ]; then
    echo "loop_rollback: sha $sha not found in $(basename "$repo")" >&2
    if [ "$strict" = "strict" ]; then exit 2; else return 1; fi
  fi
  case "$subject" in
    "loop: "*) : ;;
    *)
      echo "loop_rollback: REFUSED — $sha is not a loop: commit (subject: $subject)" >&2
      if [ "$strict" = "strict" ]; then exit 4; else return 1; fi ;;
  esac
  if ! git -C "$repo" revert --no-edit "$sha" >&2; then
    git -C "$repo" revert --abort >/dev/null 2>&1 || true
    echo "loop_rollback: revert of $sha failed (conflict?) — aborted, tree clean" >&2
    if [ "$strict" = "strict" ]; then exit 1; else return 1; fi
  fi
  rev_sha="$(git -C "$repo" rev-parse HEAD)"
  mkdir -p "$LEARNING_DIR" 2>/dev/null || true
  printf '%s\t%s\t%s\tREVERT %s of %s\t-\n' \
    "$(iso_now)" "$(basename "$repo")" "$rev_sha" "$rev_sha" "$sha" >> "$AUTOLOG"
  relint_touched "$repo" "$sha"
  echo "loop_rollback: reverted $sha in $(basename "$repo") (revert $rev_sha)"
  return 0
}

if [ "$MODE" = "single" ]; then
  [ -n "$SHA" ] || { echo "loop_rollback: a <sha> or --last is required" >&2; exit 2; }
  root="$(repo_root_for_sel "$REPO_SEL")" \
    || { echo "loop_rollback: --repo must be framework or local" >&2; exit 2; }
  do_revert "$root" "$SHA" strict
  exit 0
fi

# --- --last N: newest-first across repos, from AUTO_COMMITS.log --------------
if [ ! -f "$AUTOLOG" ]; then
  echo "loop_rollback: no AUTO_COMMITS.log at $AUTOLOG — nothing to roll back" >&2
  exit 0
fi
# Loop commits only (subject starts 'loop: '); exclude REVERT/PARTIAL/other
# lines. Group the loop lines by their GROUP id (6th tab field; legacy 5-field
# lines fall back to the sha's first 8 chars = a group of one). Select the last
# N GROUPS by newest appearance, and within each group emit `repo<TAB>sha`
# newest-line-first. tac is absent on macOS, so the ordering is done in awk.
selected="$(awk -F'\t' -v N="$LAST_N" '
  $4 ~ /^loop: / {
    n++
    grp = $6
    if (grp == "") grp = substr($3, 1, 8)
    line_grp[n]  = grp
    line_repo[n] = $2
    line_sha[n]  = $3
    last_seen[grp] = n
    if (!(grp in seen)) { seen[grp] = 1; gc++; gname[gc] = grp }
  }
  END {
    # Order group names by last appearance, descending (newest group first).
    for (i = 1; i <= gc; i++) {
      max = i
      for (j = i + 1; j <= gc; j++)
        if (last_seen[gname[j]] > last_seen[gname[max]]) max = j
      t = gname[i]; gname[i] = gname[max]; gname[max] = t
    }
    take = (N < gc ? N : gc)
    for (k = 1; k <= take; k++) {
      g = gname[k]
      for (idx = n; idx >= 1; idx--)
        if (line_grp[idx] == g) print line_repo[idx] "\t" line_sha[idx]
    }
  }
' "$AUTOLOG")"
if [ -z "$(printf '%s' "$selected" | tr -d '[:space:]')" ]; then
  echo "loop_rollback: no loop commits in AUTO_COMMITS.log to roll back" >&2
  exit 0
fi
printf '%s\n' "$selected" | while IFS= read -r line; do
  [ -n "$line" ] || continue
  rbase="$(printf '%s' "$line" | awk -F'\t' '{print $1}')"
  rsha="$(printf '%s' "$line" | awk -F'\t' '{print $2}')"
  rroot="$(repo_root_for_base "$rbase")" || {
    echo "loop_rollback: unknown repo '$rbase' in log — skipping $rsha" >&2; continue; }
  do_revert "$rroot" "$rsha" lenient || true
done
exit 0
