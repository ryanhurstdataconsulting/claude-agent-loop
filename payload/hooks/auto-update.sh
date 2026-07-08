#!/bin/bash
# Auto-update hook — pull the latest claude-agent-loop from git on a new/resumed
# session and after a long idle gap, then re-link any new resources.
#
# Wired to TWO events (see fragments/settings.fragment.json):
#   SessionStart      — fires on a new or resumed session (always attempts,
#                       past a small dedup window so it does not double-pull).
#   UserPromptSubmit  — catches a session left open and prompted again after a
#                       long idle gap (no SessionStart fires there); attempts
#                       only past AGENT_LOOP_UPDATE_IDLE_HOURS of idle.
#
# NEVER clobbers local work — three guarantees:
#   1. Pull is `git merge --ff-only`: it refuses any merge/rebase that would
#      rewrite local history.
#   2. PRE-FLIGHT: if the framework repo has uncommitted changes, or has
#      DIVERGED from origin (you have unpushed commits and origin advanced), it
#      SKIPS the pull and nudges instead — in-flight framework work is safe.
#   3. install.sh (run only when the MANIFEST/fragments changed) is
#      copy-if-absent + shadow-respecting + merge-only, and is invoked with
#      --no-plugins so it never nests the `claude` CLI.
#
# Always exits 0 and never blocks the session. Fail-open on offline/slow/dirty.
# Opt out with AGENT_LOOP_AUTO_UPDATE=0. All thresholds are env-overridable.
set -u

[ "${AGENT_LOOP_AUTO_UPDATE:-1}" = "0" ] && exit 0

INPUT="$(cat 2>/dev/null || true)"

HOOK_INPUT="$INPUT" \
SELF_PATH="$0" \
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}" \
AGENT_LOOP_REPO="${AGENT_LOOP_REPO:-}" \
AGENT_LOOP_STATE_DIR="${AGENT_LOOP_STATE_DIR:-}" \
AGENT_LOOP_UPDATE_IDLE_HOURS="${AGENT_LOOP_UPDATE_IDLE_HOURS:-12}" \
AGENT_LOOP_SESSION_DEDUP_SECS="${AGENT_LOOP_SESSION_DEDUP_SECS:-120}" \
AGENT_LOOP_UPDATE_RUN_INSTALL="${AGENT_LOOP_UPDATE_RUN_INSTALL:-1}" \
AGENT_LOOP_GIT_TIMEOUT="${AGENT_LOOP_GIT_TIMEOUT:-12}" \
python3 <<'PY' || true
import json, os, subprocess, sys, time


def env(k, d=""):
    v = os.environ.get(k)
    return v if v not in (None, "") else d


claude_dir = env("CLAUDE_DIR", os.path.expanduser("~/.claude"))
state_dir = env("AGENT_LOOP_STATE_DIR") or os.path.join(claude_dir, "metrics", "state")
stamp = os.path.join(state_dir, "last-pull")
idle_secs = float(env("AGENT_LOOP_UPDATE_IDLE_HOURS", "12")) * 3600.0
dedup_secs = float(env("AGENT_LOOP_SESSION_DEDUP_SECS", "120"))
run_install = env("AGENT_LOOP_UPDATE_RUN_INSTALL", "1") != "0"
git_timeout = float(env("AGENT_LOOP_GIT_TIMEOUT", "12"))

# Resolve the package repo from this script's real path (it is symlinked into
# ~/.claude/hooks/auto-update.sh -> <repo>/payload/hooks/auto-update.sh).
repo = env("AGENT_LOOP_REPO")
if not repo:
    try:
        p = os.path.realpath(env("SELF_PATH"))
        repo = os.path.dirname(os.path.dirname(os.path.dirname(p)))
    except Exception:
        repo = ""

try:
    data = json.loads(env("HOOK_INPUT") or "{}")
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}
event = data.get("hook_event_name") or data.get("hookEventName") or "SessionStart"

now = time.time()
try:
    last = float(open(stamp).read().strip())
except Exception:
    last = 0.0
elapsed = now - last

# Decide whether to attempt an update this invocation.
if event == "UserPromptSubmit":
    attempt = elapsed >= idle_secs        # only after a long idle gap
else:
    attempt = elapsed >= dedup_secs       # new/resumed session; dedup only
if not attempt:
    sys.exit(0)

if not repo or not os.path.isdir(os.path.join(repo, ".git")):
    sys.exit(0)  # cannot locate the package repo — stay silent


def emit(msg, ctx):
    out = {"systemMessage": msg,
           "hookSpecificOutput": {"hookEventName": event, "additionalContext": ctx}}
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()


def touch():
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(stamp, "w") as fh:
            fh.write(str(int(now)))
    except Exception:
        pass


def git(args):
    return subprocess.run(["git", "-C", repo] + args,
                          capture_output=True, text=True, timeout=git_timeout)


# Mark the attempt now so a dirty/diverged repo is not re-nagged every prompt.
touch()

try:
    # PRE-FLIGHT 1 — dirty working tree: never pull over local edits.
    st = git(["status", "--porcelain"])
    if st.returncode == 0 and st.stdout.strip():
        emit("claude-agent-loop auto-update paused — the package repo has uncommitted "
             "local changes. Commit or stash them to resume automatic updates.",
             "Auto-update skipped: the framework repo working tree is dirty, so pulling "
             "could touch local edits. Do not pull; if relevant, tell the user their "
             "package repo has uncommitted changes.")
        sys.exit(0)

    fe = git(["fetch", "--quiet"])  # bounded; failure just means we stay put
    up = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if up.returncode != 0:
        sys.exit(0)  # no upstream configured — nothing to pull from
    upstream = up.stdout.strip()

    behind = int((git(["rev-list", "--count", "HEAD..%s" % upstream]).stdout or "0").strip() or "0")
    ahead = int((git(["rev-list", "--count", "%s..HEAD" % upstream]).stdout or "0").strip() or "0")
    old = git(["rev-parse", "--short", "HEAD"]).stdout.strip()

    if behind == 0:
        sys.exit(0)  # already up to date (or only ahead) — nothing to fast-forward

    # PRE-FLIGHT 2 — diverged: unpushed local commits AND origin advanced.
    if ahead > 0:
        emit("claude-agent-loop auto-update paused — you have %d unpushed local commit(s) "
             "in the package repo and origin has %d new one(s). Push your work (for example "
             "at digest review) to resume clean fast-forward updates." % (ahead, behind),
             "Auto-update skipped: the framework repo has diverged (%d ahead, %d behind). A "
             "fast-forward-only pull would fail, and merging/rebasing could disturb local "
             "commits, so nothing was pulled. Nudge the user to push at digest review." % (ahead, behind))
        sys.exit(0)

    # Clean fast-forward.
    mg = git(["merge", "--ff-only", upstream])
    if mg.returncode != 0:
        sys.exit(0)  # unexpected — fail open, stay silent
    new = git(["rev-parse", "--short", "HEAD"]).stdout.strip()

    changed = git(["diff", "--name-only", "%s..%s" % (old, new)]).stdout
    needs_install = ("payload/MANIFEST" in changed
                     or "settings.fragment.json" in changed
                     or "fragments/CLAUDE" in changed)
    installed = False
    if needs_install and run_install:
        try:
            subprocess.run(["bash", os.path.join(repo, "install.sh"), "--no-plugins"],
                           capture_output=True, text=True, timeout=180)
            installed = True
        except Exception:
            installed = False

    plural = "s" if behind != 1 else ""
    if needs_install and installed:
        tail = " New resources were linked via install.sh --no-plugins."
        ctx_tail = " install.sh --no-plugins re-linked new resources (local overrides and diverged seeds untouched)."
    elif needs_install:
        tail = " New resources were added — run `bash install.sh` to link them."
        ctx_tail = " The MANIFEST changed; new resources need `bash install.sh` before they are usable."
    else:
        tail = " Symlinked content is already live."
        ctx_tail = " Framework content is symlinked, so the changes are already live."

    emit("claude-agent-loop updated: %s..%s (%d commit%s)." % (old, new, behind, plural) + tail,
         "The claude-agent-loop package was auto-updated by fast-forward (%s..%s, %d commit%s)."
         % (old, new, behind, plural) + ctx_tail + " Continue normally.")
except subprocess.TimeoutExpired:
    sys.exit(0)  # network too slow — never block the session
except Exception:
    sys.exit(0)
PY

exit 0
