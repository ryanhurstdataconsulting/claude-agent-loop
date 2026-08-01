#!/bin/bash
# audit_run.sh — one package, one unattended security audit, zero disturbance.
#
# usage: audit_run.sh <package-path> <store-root> [--dry-run]
#
# Runs the repo-security-auditor agent headlessly against ONE package and
# leaves the findings on an `audit/security-<date>` branch that is never
# pushed. It is invoked nightly by the scheduler, against repositories the
# developer may have open with uncommitted work, so the whole design turns on
# one property: the live checkout is never touched. The audit happens inside a
# throwaway `git worktree` checked out detached at HEAD; the developer's
# branch, index, and dirty files are never so much as read by the agent's
# tooling. A trap registered BEFORE the worktree is created removes it on any
# exit path, including a signal — a run interrupted between `worktree add` and
# the next line is precisely how a stale worktree gets orphaned.
#
# Exit codes (the scheduler distinguishes them):
#   - 0 — success: audit committed to the branch, run log written
#   - 1 — run failure: the CLI failed, or produced no findings file
#   - 2 — usage error: bad arguments, missing package, not a git repository
#   - 3 — gate abort: a safety gate found something; nothing was created
#   - 4 — the `claude` CLI is absent or not executable
#
# Writes <store>/audit/runs/<pkg>/<date>.json every run, and
# <store>/audit/runs/<pkg>/state.json (last_audit_date, last_audited_sha) on
# success only. Those two state keys are the scheduler's skip-if-unchanged
# contract: a blocked or failed run deliberately records neither, so the
# package stays due rather than being silently marked audited.
#
# Environment overrides (all optional, all for testing or calibration):
#   - AUDIT_CLAUDE_BIN — path to the CLI (default: `command -v claude`)
#   - AUDIT_GATE_DIR — directory holding the two gate scripts
#   - AUDIT_MAX_TURNS — agent turn cap (calibrated against a real run)
#   - AUDIT_TIMEOUT — wall-clock seconds for the CLI, when a timeout binary is
# available
#
# macOS bash-3.2 portable: no mapfile, no associative arrays, and no `set -e`
# — gate handling reads exit codes, which `set -e` would turn into an abort
# before the blocked run log could be written.
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- gate location ------------------------------------------------------------
# The gates sit beside this script both in the framework checkout and in the
# installed ~/.claude/tools tree, so a sibling lookup covers both; the explicit
# fallback covers an unusual install, and the env override keeps tests hermetic.
GATE_DIR="${AUDIT_GATE_DIR:-}"
if [ -z "$GATE_DIR" ]; then
  if [ -f "$SELF_DIR/secret_pii_scrub_gate.py" ]; then
    GATE_DIR="$SELF_DIR"
  else
    GATE_DIR="$HOME/.claude/tools"
  fi
fi

MAX_TURNS="${AUDIT_MAX_TURNS:-40}"
TIMEOUT_SECONDS="${AUDIT_TIMEOUT:-3600}"

usage() {
  cat >&2 <<'EOF'
usage: audit_run.sh <package-path> <store-root> [--dry-run]

  <package-path> — a git repository to audit; never modified
  <store-root> — the consolidated store (run logs land under audit/runs/)
  --dry-run — resolve and print the plan; create and launch nothing
EOF
}

usage_err() {
  echo "audit_run: $1" >&2
  usage
  exit 2
}

# --- OS notification (Darwin + osascript only; never fails the run) -----------
_notify() {
  msg="$(printf '%s' "$1" | tr -d '"')"
  [ "${AUDIT_NOTIFY:-1}" = "0" ] && return 0
  [ "$(uname 2>/dev/null)" = "Darwin" ] || return 0
  command -v osascript >/dev/null 2>&1 || return 0
  osascript -e "display notification \"$msg\" with title \"claude-agent-loop\"" \
    >/dev/null 2>&1 || true
}

# --- arguments ----------------------------------------------------------------
PKG=""
STORE=""
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) usage_err "unknown flag: $1" ;;
    *)
      if [ -z "$PKG" ]; then
        PKG="$1"
      elif [ -z "$STORE" ]; then
        STORE="$1"
      else
        usage_err "unexpected argument: $1"
      fi
      shift
      ;;
  esac
done

[ -n "$PKG" ] || usage_err "missing <package-path>"
[ -n "$STORE" ] || usage_err "missing <store-root>"
[ -d "$PKG" ] || usage_err "package path is not a directory: $PKG"
[ -d "$STORE" ] || usage_err "store root is not a directory: $STORE"

PKG="$(cd "$PKG" && pwd)"
STORE="$(cd "$STORE" && pwd)"

git -C "$PKG" rev-parse --git-dir >/dev/null 2>&1 \
  || usage_err "not a git repository: $PKG"
HEAD_SHA="$(git -C "$PKG" rev-parse HEAD 2>/dev/null)"
[ -n "$HEAD_SHA" ] || usage_err "package has no commits: $PKG"

PKG_NAME="$(basename "$PKG")"
DATE="$(date +%F)"
BRANCH="audit/security-$DATE"
RUN_DIR="$STORE/audit/runs/$PKG_NAME"

# --- the CLI ------------------------------------------------------------------
# Resolved through AUDIT_CLAUDE_BIN so tests can inject a stub; never call
# `claude` directly. A missing CLI is exit 4 and nothing else happens — no
# worktree, no temp directory, no run log.
# `${VAR-default}`, not `${VAR:-default}`: an override that is set but EMPTY
# must fail, not fall through to the real CLI. A harness that computes an empty
# path would otherwise launch a live, billed session in place of its stub.
CLAUDE_BIN="${AUDIT_CLAUDE_BIN-$(command -v claude)}"
if [ -z "$CLAUDE_BIN" ] || [ ! -x "$CLAUDE_BIN" ]; then
  echo "audit_run: claude CLI not found or not executable: ${CLAUDE_BIN:-<unset>}" >&2
  exit 4
fi

TIMEOUT_BIN=""
if command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_BIN="$(command -v gtimeout)"
elif command -v timeout >/dev/null 2>&1; then
  TIMEOUT_BIN="$(command -v timeout)"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  # printf pads the labels at run time, so the aligned output costs the source
  # no double spaces for the grammar gate to trip over.
  echo "audit_run: dry run — nothing created, nothing launched"
  printf '  %-10s %s\n' "package" "$PKG"
  printf '  %-10s %s\n' "head" "$HEAD_SHA"
  printf '  %-10s %s\n' "branch" "$BRANCH (would be created in the worktree)"
  printf '  %-10s %s\n' "store" "$STORE"
  printf '  %-10s %s\n' "run log" "$RUN_DIR/$DATE.json"
  printf '  %-10s %s\n' "cli" "$CLAUDE_BIN"
  printf '  %-10s %s\n' "max turns" "$MAX_TURNS"
  exit 0
fi

# --- run-log writer -----------------------------------------------------------
# Values cross into Python through the environment, never through the script
# text, so a package name or a gate line can hold any character without
# breaking quoting. Python owns the JSON so nothing is hand-escaped in shell.
# Echoes "<critical> <high>" for the caller's notification decision.
_write_run_log() {
  AUDIT_LOG_RUN_DIR="$RUN_DIR" \
  AUDIT_LOG_DATE="$DATE" \
  AUDIT_LOG_PKG="$PKG_NAME" \
  AUDIT_LOG_PKG_PATH="$PKG" \
  AUDIT_LOG_HEAD="$HEAD_SHA" \
  AUDIT_LOG_VERDICT="$1" \
  AUDIT_LOG_BRANCH="${2:-}" \
  AUDIT_LOG_COMMIT="${3:-}" \
  AUDIT_LOG_NOTE="${4:-}" \
  AUDIT_LOG_CLI_OUT="${CLI_OUT:-}" \
  AUDIT_LOG_CLI_RC="${CLI_RC:-}" \
  AUDIT_LOG_DURATION="${DURATION:-}" \
  AUDIT_LOG_MAX_TURNS="$MAX_TURNS" \
  AUDIT_LOG_TIMEOUT="$TIMEOUT_SECONDS" \
  AUDIT_LOG_GATE_SECRET="${GATE_SECRET:-skipped}" \
  AUDIT_LOG_GATE_PROSE="${GATE_PROSE:-skipped}" \
  AUDIT_LOG_GATE_FINDINGS="${GATE_FINDINGS_FILE:-}" \
  python3 - <<'PY'
import datetime
import json
import os
import pathlib

SEVERITIES = ("critical", "high", "medium", "low")


def env(name, default=""):
    return os.environ.get("AUDIT_LOG_" + name, default)


def as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def find_findings(node, depth=0):
    """Return the first severity-shaped ``findings`` object in the CLI payload.

    The stub prints ``findings`` at the top level; the real CLI wraps its
    result in an envelope and may hand back the agent's JSON as a string. Both
    shapes are searched, and anything unrecognised yields None rather than a
    guess — a fabricated zero-count would read as "clean" in the digest.
    """
    if depth > 8:
        return None
    if isinstance(node, dict):
        candidate = node.get("findings")
        if isinstance(candidate, dict) and any(s in candidate for s in SEVERITIES):
            return candidate
        for value in node.values():
            found = find_findings(value, depth + 1)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find_findings(value, depth + 1)
            if found is not None:
                return found
    elif isinstance(node, str) and node.strip()[:1] in ("{", "["):
        try:
            return find_findings(json.loads(node), depth + 1)
        except ValueError:
            return None
    return None


def parse_cli(path):
    """Return (findings|None, num_turns|None) from the CLI's JSON output."""
    if not path:
        return None, None
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None
    payload = None
    try:
        payload = json.loads(text)
    except ValueError:
        # Streamed output: the last complete JSON object line is the result.
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
                break
            except ValueError:
                continue
    if payload is None:
        return None, None
    findings = find_findings(payload)
    turns = payload.get("num_turns") if isinstance(payload, dict) else None
    return findings, as_int(turns)


findings, num_turns = parse_cli(env("CLI_OUT"))
counts = None
if findings is not None:
    counts = {}
    for severity in SEVERITIES:
        counts[severity] = as_int(findings.get(severity)) or 0

verdict = env("VERDICT")
run_dir = pathlib.Path(env("RUN_DIR"))
run_dir.mkdir(parents=True, exist_ok=True)
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

record = {
    "schema": 1,
    "package": env("PKG"),
    "package_path": env("PKG_PATH"),
    "date": env("DATE"),
    "verdict": verdict,
    "head_sha": env("HEAD"),
    "branch": env("BRANCH") or None,
    "commit": env("COMMIT") or None,
    "findings": counts,
    "run_at": stamp,
    "duration_seconds": as_int(env("DURATION")),
    "num_turns": num_turns,
    "max_turns": as_int(env("MAX_TURNS")),
    "timeout_seconds": as_int(env("TIMEOUT")),
    "cli_exit": as_int(env("CLI_RC")),
    "gates": {
        "secret_pii_scrub": env("GATE_SECRET"),
        "prose_grammar": env("GATE_PROSE"),
    },
    "note": env("NOTE") or None,
}

gate_findings_file = env("GATE_FINDINGS")
if gate_findings_file:
    try:
        lines = pathlib.Path(gate_findings_file).read_text(
            encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    record["gate_findings"] = [line for line in lines if line.strip()]

# last_audit_date / last_audited_sha are the scheduler's due-check keys. They
# are written ONLY for a successful audit: recording them for a blocked or
# failed run would mark the package audited and silently drop it from the
# rotation until the interval elapsed again.
if verdict == "ok":
    record["last_audit_date"] = stamp
    record["last_audited_sha"] = env("HEAD")
    state = {
        "last_audit_date": stamp,
        "last_audited_sha": env("HEAD"),
        "package": env("PKG"),
        "branch": env("BRANCH") or None,
        "verdict": verdict,
    }
    (run_dir / "state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

(run_dir / (env("DATE") + ".json")).write_text(
    json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print("%d %d" % ((counts or {}).get("critical", 0), (counts or {}).get("high", 0)))
PY
}

# --- worktree, and the trap that guarantees its removal -----------------------
# The trap is registered BEFORE `worktree add`. An interrupt landing between
# the two would otherwise leave a worktree registered against the developer's
# repository with nothing to clean it up. Removal is belt-and-braces: the
# proper `worktree remove`, then `rm -rf`, then a name-matched drop of our own
# registration — so a failure of any one of them still leaves nothing behind,
# and none of the three can reach a worktree that is not ours.
TMPROOT="$(mktemp -d)"
# The worktree DIRECTORY name has to be unique per run, not merely per package
# and date. Two runs against the same package on the same day get different
# temp roots but would otherwise land on an identical basename, and the
# name-matched cleanup below would then let one run drop the other's live
# registration — worse than the `git worktree prune` it replaced, which never
# touched a registration whose directory still existed. `mktemp -d` has already
# handed us a token that is unique by construction, so reuse it rather than
# inventing a second source of uniqueness.
#
# The BRANCH name is deliberately left alone: `audit/security-<date>` is what
# makes the output findable and reviewable by a human afterwards, and it lives
# in the package repo where no two runs share it.
WT_TAG="$(basename "$TMPROOT")"
WT="$TMPROOT/audit-$PKG_NAME-$DATE-$WT_TAG"
CLI_OUT="$TMPROOT/cli-output.json"
CLI_ERR="$TMPROOT/cli-error.log"
_CLEANUP_DONE=0

# Drop the administrative registration for OUR worktree and nothing else.
#
# `git worktree prune` would be simpler and is what the obvious version of this
# script reaches for, but it is repo-GLOBAL: it drops every registration whose
# directory is currently missing, which includes an unlocked worktree the
# developer keeps on a volume that happens to be unmounted tonight. Deleting
# that is precisely the kind of damage this whole task exists to prevent. So
# the match is by name — the registration whose recorded path ends in our own
# `audit-<pkg>-<date>-<tag>` directory, where the tag makes the name unique to
# this run — and a registration belonging to anyone else is left untouched
# however stale it looks.
#
# A missing directory is deliberately NOT the matching criterion, because that
# is exactly what an unmounted volume looks like. It is used only as a second
# gate underneath the name: a registration whose directory is still present is
# a live worktree, not a stale one, and `git worktree prune` would not have
# removed it either.
_drop_own_registration() {
  common_dir="$(git -C "$PKG" rev-parse --git-common-dir 2>/dev/null)"
  [ -n "$common_dir" ] || return 0
  case "$common_dir" in
    /*) ;;
    *) common_dir="$PKG/$common_dir" ;;
  esac
  wt_name="$(basename "$WT")"
  for admin in "$common_dir"/worktrees/*; do
    [ -d "$admin" ] || continue
    [ -f "$admin/gitdir" ] || continue
    recorded="$(cat "$admin/gitdir" 2>/dev/null)"
    [ -n "$recorded" ] || continue
    # `gitdir` holds "<worktree path>/.git" — compare the worktree's own name.
    [ "$(basename "$(dirname "$recorded")")" = "$wt_name" ] || continue
    # Never unregister a worktree whose directory is still there.
    [ -d "$(dirname "$recorded")" ] && continue
    rm -rf "$admin" >/dev/null 2>&1
  done
  return 0
}

_cleanup() {
  [ "$_CLEANUP_DONE" -eq 1 ] && return 0
  _CLEANUP_DONE=1
  git -C "$PKG" worktree remove --force "$WT" >/dev/null 2>&1
  rm -rf "$WT" >/dev/null 2>&1
  _drop_own_registration
  rm -rf "$TMPROOT" >/dev/null 2>&1
  return 0
}

_cleanup_signal() {
  # Kill the agent session first — otherwise the cleanup below would race a
  # process that is still writing into the worktree it is removing.
  [ -n "${CLI_PID:-}" ] && kill -TERM "$CLI_PID" 2>/dev/null
  _cleanup
  exit "$1"
}

trap _cleanup EXIT
trap '_cleanup_signal 130' INT
trap '_cleanup_signal 143' TERM

_fail_run() {
  echo "audit_run: $1" >&2
  _write_run_log "failed" "" "" "$1" >/dev/null
  _notify "audit failed: $PKG_NAME — $1"
  exit 1
}

if ! git -C "$PKG" worktree add -q --detach "$WT" "$HEAD_SHA" 2>"$TMPROOT/worktree.err"; then
  _fail_run "worktree add failed: $(tr '\n' ' ' < "$TMPROOT/worktree.err")"
fi

# --- the headless agent run ---------------------------------------------------
PROMPT="Audit the package at $WT for security and production-readiness.

This is a scheduled, unattended run against a throwaway git worktree checked
out detached at $HEAD_SHA. The developer's live checkout is elsewhere and must
not be touched: read and write only inside $WT.

Follow your standard method — stack-appropriate scanners, the manual category
checklist, severity classification — and apply only the pre-approved low-risk
fixes. Write the findings to $WT/SECURITY_AUDIT.md.

Do not create a branch, do not commit, and do not push. The caller commits
whatever you leave in the working tree, after its own safety gates run.

End your run with a JSON object carrying a \"findings\" object whose keys are
critical, high, medium, and low, each an integer count."

# The git allowlist names read-only subcommands one at a time. A blanket
# `Bash(git:*)` would be a hole straight through this script's isolation:
# --add-dir constrains the file tools, not Bash, and the live repository path
# is one `git rev-parse --git-common-dir` away from inside the worktree — so
# the agent could check out, reset, or push in the developer's checkout, with
# nothing but prompt text discouraging it. Prompt text is not a control for an
# unattended auditor reading potentially adversarial repository content.
set -- \
  -p "$PROMPT" \
  --agent repo-security-auditor \
  --add-dir "$WT" \
  --allowedTools Read Grep Glob Edit Write \
                 'Bash(pip-audit:*)' 'Bash(npm audit:*)' \
                 'Bash(gitleaks:*)' 'Bash(semgrep:*)' \
                 'Bash(git log:*)' 'Bash(git diff:*)' 'Bash(git ls-files:*)' \
                 'Bash(git status:*)' 'Bash(git rev-parse:*)' \
  --permission-mode acceptEdits \
  --output-format json \
  --max-turns "$MAX_TURNS"

_run_cli() {
  if [ -n "$TIMEOUT_BIN" ]; then
    ( cd "$WT" && exec "$TIMEOUT_BIN" "$TIMEOUT_SECONDS" "$CLAUDE_BIN" "$@" )
  else
    ( cd "$WT" && exec "$CLAUDE_BIN" "$@" )
  fi
}

# Backgrounded and waited on, rather than run in the foreground: bash defers a
# trapped signal until the current foreground command returns, so a TERM from
# launchd during a long — or hung — agent session would not reach the cleanup
# trap until the session ended on its own. `wait` is interruptible, so the
# worktree is removed promptly however the run is cut short.
STARTED="$(date +%s)"
_run_cli "$@" >"$CLI_OUT" 2>"$CLI_ERR" &
CLI_PID=$!
wait "$CLI_PID"
CLI_RC=$?
CLI_PID=""
DURATION=$(( $(date +%s) - STARTED ))

if [ "$CLI_RC" -ne 0 ]; then
  _fail_run "claude exited $CLI_RC: $(tail -1 "$CLI_ERR" 2>/dev/null)"
fi

AUDIT_FILE="$WT/SECURITY_AUDIT.md"
[ -f "$AUDIT_FILE" ] || _fail_run "the agent wrote no SECURITY_AUDIT.md"

# --- safety gates, before anything is created ---------------------------------
# Both gates run on the findings document BEFORE the branch exists, so an abort
# leaves the package repository exactly as it was — no branch to delete, no
# commit to revert. Any non-zero exit blocks, including a gate that crashed:
# an unverified findings document is not a passed one.
GATE_FINDINGS_FILE="$TMPROOT/gate-findings.log"
: > "$GATE_FINDINGS_FILE"
SECRET_LOG="$TMPROOT/gate-secret.log"
PROSE_LOG="$TMPROOT/gate-prose.log"
CHANGED_PATHS="$TMPROOT/changed-paths.z"

# Enumerate what the agent touched ONCE, before the branch exists, and use that
# one list for both gating and staging. Enumerating twice would let the two
# drift, and the gap between them is where an ungated file reaches a commit.
# NUL-delimited so a path holding a space or a newline survives.
_enumerate_changed_paths() {
  : > "$CHANGED_PATHS"
  while IFS= read -r -d '' entry; do
    code="${entry:0:2}"
    path="${entry:3}"
    case "$code" in
      R*|C*)
        # A rename/copy record carries the source path in the next field; both
        # sides belong in the commit.
        if IFS= read -r -d '' origin; then
          [ -n "$origin" ] && printf '%s\0' "$origin" >> "$CHANGED_PATHS"
        fi
        ;;
    esac
    [ -n "$path" ] || continue
    case "$path" in
      .git/*) continue ;;
    esac
    printf '%s\0' "$path" >> "$CHANGED_PATHS"
  done < <(git -C "$WT" status --porcelain -z --untracked-files=all)
}

_enumerate_changed_paths

# The secret gate covers EVERY path that will be staged, not just the findings
# document. The auditor applies its own pre-approved low-risk fixes, and a
# credential introduced by one of those would otherwise ride into the commit
# completely unscanned. The grammar gate stays on the Markdown alone — it
# reasons about prose, and source files are not prose.
#
# The audit file leads the list explicitly: when a re-audit rewrites it
# byte-identically it does not appear in `status` at all, and an empty argument
# list would silently turn the gate into a scan of the staging area of whatever
# directory this script happens to be running in.
set -- "$AUDIT_FILE"
while IFS= read -r -d '' rel; do
  [ "$rel" = "SECURITY_AUDIT.md" ] && continue
  set -- "$@" "$WT/$rel"
done < "$CHANGED_PATHS"

python3 "$GATE_DIR/secret_pii_scrub_gate.py" "$@" >"$SECRET_LOG" 2>&1
SECRET_RC=$?
python3 "$GATE_DIR/prose_grammar_gate.py" "$AUDIT_FILE" >"$PROSE_LOG" 2>&1
PROSE_RC=$?

GATE_SECRET="pass"
GATE_PROSE="pass"
[ "$SECRET_RC" -eq 0 ] || GATE_SECRET="fail"
[ "$PROSE_RC" -eq 0 ] || GATE_PROSE="fail"

if [ "$SECRET_RC" -ne 0 ] || [ "$PROSE_RC" -ne 0 ]; then
  [ "$SECRET_RC" -eq 0 ] || cat "$SECRET_LOG" >> "$GATE_FINDINGS_FILE"
  [ "$PROSE_RC" -eq 0 ] || cat "$PROSE_LOG" >> "$GATE_FINDINGS_FILE"
  BLOCKED_BY=""
  [ "$SECRET_RC" -eq 0 ] || BLOCKED_BY="secret_pii_scrub_gate"
  if [ "$PROSE_RC" -ne 0 ]; then
    [ -n "$BLOCKED_BY" ] && BLOCKED_BY="$BLOCKED_BY and "
    BLOCKED_BY="${BLOCKED_BY}prose_grammar_gate"
  fi
  echo "audit_run: blocked — $BLOCKED_BY refused the audit output" >&2
  cat "$GATE_FINDINGS_FILE" >&2
  _write_run_log "blocked" "" "" "$BLOCKED_BY refused the audit output" >/dev/null
  _notify "audit blocked: $PKG_NAME — $BLOCKED_BY refused the audit output"
  exit 3
fi

# --- branch, stage, commit ----------------------------------------------------
git -C "$WT" checkout -q -b "$BRANCH" 2>"$TMPROOT/branch.err" \
  || _fail_run "could not create $BRANCH: $(tr '\n' ' ' < "$TMPROOT/branch.err")"

# Explicit paths only, never `git add -A`, and every one of them came from the
# list the secret gate just cleared — nothing reaches the index that was not
# scanned.
git -C "$WT" add -- "SECURITY_AUDIT.md" 2>/dev/null
while IFS= read -r -d '' rel; do
  git -C "$WT" add -- "$rel" 2>/dev/null
done < "$CHANGED_PATHS"

if git -C "$WT" diff --cached --quiet; then
  # Nothing changed — a re-audit that found exactly what the last one did.
  # Discard the branch rather than leave an empty one behind, and record the
  # run as a success so the rotation moves on.
  git -C "$WT" checkout -q --detach "$HEAD_SHA" 2>/dev/null
  git -C "$PKG" branch -D "$BRANCH" >/dev/null 2>&1
  COUNTS="$(_write_run_log "ok" "" "" "audit produced no change")"
  echo "audit_run: $PKG_NAME audited at ${HEAD_SHA:0:8} — no change to commit"
  exit 0
fi

SECRET_SUMMARY="$(tail -1 "$SECRET_LOG" 2>/dev/null)"
PROSE_SUMMARY="$(tail -1 "$PROSE_LOG" 2>/dev/null)"
MSG_FILE="$TMPROOT/commit-message.txt"
cat > "$MSG_FILE" <<EOF
audit(security): scheduled audit of $PKG_NAME — $DATE

(1) Task & Change
Scheduled, unattended repo-security audit of $PKG_NAME at ${HEAD_SHA:0:8}, run
by audit_run.sh inside a throwaway git worktree so the live checkout was never
touched. SECURITY_AUDIT.md records the findings and their severities; any other
file in this commit is a pre-approved low-risk fix the auditor applied itself.
The branch is created for review only and is never pushed.

(2) Tests created / modified
None. This commit is a generated findings artifact rather than a code change,
so the evidence that replaces a test is the two safety gates below, both of
which had to pass before this commit could be created at all.

(3) Test results — evidence
python3 secret_pii_scrub_gate.py SECURITY_AUDIT.md
$SECRET_SUMMARY
python3 prose_grammar_gate.py SECURITY_AUDIT.md
$PROSE_SUMMARY
EOF

git -C "$WT" commit -q -F "$MSG_FILE" 2>"$TMPROOT/commit.err" || {
  # A failed commit must not leave a branch behind either.
  git -C "$WT" checkout -q --detach "$HEAD_SHA" 2>/dev/null
  git -C "$PKG" branch -D "$BRANCH" >/dev/null 2>&1
  _fail_run "commit failed: $(tr '\n' ' ' < "$TMPROOT/commit.err")"
}

COMMIT_SHA="$(git -C "$WT" rev-parse HEAD 2>/dev/null)"
COUNTS="$(_write_run_log "ok" "$BRANCH" "$COMMIT_SHA")"
CRITICAL="${COUNTS%% *}"
HIGH="${COUNTS##* }"

echo "audit_run: $PKG_NAME audited at ${HEAD_SHA:0:8} — committed to $BRANCH"

# Severity-gated notification: a Critical or High must not wait for the digest;
# anything quieter is left to it, so routine runs never train the owner to
# ignore the alert.
case "$CRITICAL$HIGH" in
  00) ;;
  *) _notify "audit: $PKG_NAME — $CRITICAL critical, $HIGH high (branch $BRANCH)" ;;
esac

exit 0
