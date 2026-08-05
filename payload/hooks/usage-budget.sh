#!/bin/bash
# usage-budget.sh — PostToolUse hook: read the out-of-band usage poller's
# cached account-usage status and force a durable pause point before a Claude
# subscription session or weekly limit is exhausted.
#
# After every tool call, reads ONLY the cached JSON the poller last wrote
# ($METRICS_DIR/state/usage/status.json) — no network, no Playwright, no
# transcript read — and compares max(session_pct, weekly_pct) against
# USAGE_BUDGET_WARN_PCT (70) / USAGE_BUDGET_CRIT_PCT (85):
#   - at 70%: one warning per cycle — steer toward a safe pause point;
#   - at 85%: a checkpoint directive that repeats on EVERY tool call until a
#     checkpoint file exists at
#     $METRICS_DIR/state/usage/checkpoints/<session>.md with
#     mtime >= int(crit_since).
# A missing / unreadable / malformed / stale (older than
# USAGE_BUDGET_STALE_SECS, default 1800s) cache is treated as unknown and the
# hook stays silent — a stale reading must never fire a directive the live
# number may no longer support. Dropping back below the warn threshold re-arms
# both tiers. Fail-open: any internal failure degrades to silence, and the
# hook always exits 0. Kill switch: USAGE_BUDGET_DISABLE=1.
set -u

_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="usage-budget.sh" \
    python3 -c '
import os, sys
sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))
try:
    import obs_emit
    obs_emit.emit("hook.error", hook=os.environ.get("HOOK_NAME"), stage="trap")
except Exception:
    pass
' >/dev/null 2>&1 || true
}
trap _obs_hook_error ERR

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
METRICS_DIR="${METRICS_DIR:-$CLAUDE_DIR/metrics}"

if [ "${USAGE_BUDGET_DISABLE:-0}" = "1" ]; then
  exit 0
fi

INPUT="$(cat 2>/dev/null || true)"

HOOK_JSON="$INPUT" METRICS_DIR="$METRICS_DIR" python3 <<'PY' || true
import datetime
import json
import os
import re
import sys
import tempfile
import time


def bail():
    """Flush stdout and exit 0 — the hook never blocks a tool call."""
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(0)


try:
    raw = os.environ.get("HOOK_JSON", "")
    try:
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

    session_id = data.get("session_id")
    if not session_id:
        bail()

    metrics_dir = os.environ.get("METRICS_DIR", "")

    def int_env(name, default):
        try:
            return int(os.environ.get(name, ""))
        except Exception:
            return default

    warn_pct = int_env("USAGE_BUDGET_WARN_PCT", 70)
    crit_pct = int_env("USAGE_BUDGET_CRIT_PCT", 85)
    if warn_pct >= crit_pct:
        warn_pct, crit_pct = 70, 85
    check_secs = int_env("USAGE_BUDGET_CHECK_SECS", 30)
    if check_secs < 0:
        check_secs = 30
    stale_secs = int_env("USAGE_BUDGET_STALE_SECS", 1800)
    if stale_secs <= 0:
        stale_secs = 1800

    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id))[:128]
    state_dir = os.path.join(metrics_dir, "state", "usage")
    session_dir = os.path.join(state_dir, "session")
    ckpt_dir = os.path.join(state_dir, "checkpoints")
    os.makedirs(session_dir, exist_ok=True)
    os.makedirs(ckpt_dir, exist_ok=True)
    status_path = os.path.join(state_dir, "status.json")
    state_path = os.path.join(session_dir, safe + ".json")
    ckpt_path = os.path.join(ckpt_dir, safe + ".md")

    state = {"last_check_ts": 0.0, "warn_fired": False,
             "crit_since": None, "checkpoint_ack": False}
    try:
        with open(state_path) as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            if isinstance(loaded.get("last_check_ts"), (int, float)):
                state["last_check_ts"] = float(loaded["last_check_ts"])
            if isinstance(loaded.get("warn_fired"), bool):
                state["warn_fired"] = loaded["warn_fired"]
            if isinstance(loaded.get("crit_since"), (int, float)):
                state["crit_since"] = float(loaded["crit_since"])
            if isinstance(loaded.get("checkpoint_ack"), bool):
                state["checkpoint_ack"] = loaded["checkpoint_ack"]
    except Exception:
        pass

    def save_state():
        fd, tmp = tempfile.mkstemp(dir=session_dir, prefix=safe + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(state, fh)
            os.replace(tmp, state_path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except Exception:
                    pass

    def reset_state():
        state["last_check_ts"] = 0.0
        state["warn_fired"] = False
        state["crit_since"] = None
        state["checkpoint_ack"] = False

    def read_status():
        """(pct, reset_at) from a FRESH cache, or (None, None) if unknown.

        pct = max(session_pct, weekly_pct); reset_at is the reset timestamp of
        whichever ceiling is the binding (higher) one. Missing / unreadable /
        malformed / stale cache, or one carrying no usable percentage,
        -> (None, None) -> the hook stays silent.
        """
        try:
            with open(status_path) as fh:
                cache = json.load(fh)
        except Exception:
            return (None, None)
        if not isinstance(cache, dict):
            return (None, None)
        polled_at = cache.get("polled_at")
        if not isinstance(polled_at, str):
            return (None, None)
        try:
            dt = datetime.datetime.strptime(polled_at, "%Y-%m-%dT%H:%M:%SZ")
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            return (None, None)
        if time.time() - dt.timestamp() > stale_secs:
            return (None, None)
        s = cache.get("session_pct")
        w = cache.get("weekly_pct")
        s = float(s) if isinstance(s, (int, float)) and not isinstance(s, bool) else None
        w = float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else None
        if s is None and w is None:
            return (None, None)
        if w is None or (s is not None and s >= w):
            pct, reset_at = s, cache.get("session_resets_at")
        else:
            pct, reset_at = w, cache.get("weekly_resets_at")
        if pct is None or pct < 0:
            return (None, None)
        if not isinstance(reset_at, str):
            reset_at = "unknown"
        return (int(pct), reset_at)

    def emit(tier, pct, reset_at):
        if tier == "warn":
            msg = ("Usage budget: account usage at %d%% of the weekly/session "
                   "limit. Steering toward a pause point." % pct)
            ctx = ("Usage-budget warning: this account's usage is at %d%% of "
                   "its weekly/session limit. Consider steering toward a safe "
                   "pause point in the next hour." % pct)
        else:
            msg = ("Usage budget CRITICAL: account usage at %d%%. Checkpoint "
                   "required." % pct)
            ctx = ("Usage-budget CRITICAL: usage is at %d%%, close to the "
                   "account limit (resets %s). Stop new work, commit and push "
                   "what's in progress, and write a checkpoint file at %s — "
                   "this message will repeat until you do."
                   % (pct, reset_at, ckpt_path))
        out = {
            "systemMessage": msg,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": ctx,
            },
        }
        sys.stdout.write(json.dumps(out))

    pct, reset_at = read_status()
    now = time.time()

    # Critical tier active and unacknowledged: verify the checkpoint, re-arm,
    # or repeat the directive. No throttle at this tier.
    if state["crit_since"] is not None and not state["checkpoint_ack"]:
        try:
            ck_mtime = os.path.getmtime(ckpt_path)
        except Exception:
            ck_mtime = None
        if ck_mtime is not None and ck_mtime >= int(state["crit_since"]):
            state["checkpoint_ack"] = True
            save_state()
            bail()
        if pct is None:
            bail()  # fail-open: unknown/stale usage, no nag this call
        if pct < warn_pct:
            reset_state()  # usage dropped back: re-arm both tiers
            save_state()
            bail()
        emit("crit", pct, reset_at)
        bail()

    # Normal path: throttled measurement.
    if now - state["last_check_ts"] < check_secs:
        bail()
    state["last_check_ts"] = now
    if pct is None:
        save_state()
        bail()
    if pct >= crit_pct:
        if state["crit_since"] is None:
            state["crit_since"] = now
            save_state()
            emit("crit", pct, reset_at)
        else:
            # crit_since set with checkpoint_ack true: the acknowledgment
            # holds until usage drops below the warn threshold.
            save_state()
        bail()
    if pct >= warn_pct:
        if not state["warn_fired"]:
            state["warn_fired"] = True
            save_state()
            emit("warn", pct, reset_at)
        else:
            save_state()
        bail()
    if state["warn_fired"] or state["crit_since"] is not None or state["checkpoint_ack"]:
        reset_state()
    save_state()
    bail()
except Exception:
    pass
os._exit(0)
PY

exit 0
