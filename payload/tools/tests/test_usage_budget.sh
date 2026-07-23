#!/bin/bash
# test_usage_budget.sh — PostToolUse usage-budget hook: cached-status read,
# warn/critical tiers, checkpoint acknowledgment, re-arm, throttling,
# staleness and fail-open behavior, session-id sanitization, and the
# fixed-string grammar regression on the emitted directive prose.
# macOS bash-3.2 portable.
set -u

HOOK="$(cd "$(dirname "$0")/../../hooks" && pwd)/usage-budget.sh"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CLAUDE_DIR="$TMP/claude"
export METRICS_DIR="$TMP/metrics"
export USAGE_BUDGET_CHECK_SECS=0   # disable throttling unless a case overrides it

STATUS_DIR="$METRICS_DIR/state/usage"
SESSION_DIR="$STATUS_DIR/session"
CKPT_DIR="$STATUS_DIR/checkpoints"
STATUS="$STATUS_DIR/status.json"
mkdir -p "$STATUS_DIR"

# write_status SESSION_PCT WEEKLY_PCT — a FRESH cache (polled_at = now), with
# fixed, distinct session/weekly reset timestamps.
write_status() {
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '{"polled_at":"%s","session_pct":%s,"weekly_pct":%s,"session_resets_at":"2026-07-17T19:00:00Z","weekly_resets_at":"2026-07-21T00:00:00Z"}' \
    "$now" "$1" "$2" > "$STATUS"
}

# run SESSION_ID — invoke the hook with a well-formed payload; prints stdout.
run() {
  printf '{"session_id":"%s"}' "$1" | bash "$HOOK"
}

# --- 1. below the warn threshold: silent, exit 0 ----------------------------
write_status 40 40
out="$(run s1)"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "below thresholds is silent"; else die "below thresholds: rc=$rc out=$out"; fi

# --- 2. warn fires once per cycle -------------------------------------------
write_status 70 10
out="$(run s2)"
case "$out" in *"usage is at 70%"*) pass "warn fires at 70%";; *) die "warn missing: $out";; esac
out2="$(run s2)"
if [ -z "$out2" ]; then pass "warn does not repeat"; else die "warn repeated: $out2"; fi

# --- 3. above warn, below crit: warn (not critical) -------------------------
write_status 10 84
out="$(run s3)"
case "$out" in
  *CRITICAL*) die "critical fired below crit threshold: $out";;
  *"usage is at 84%"*) pass "84% fires warn, not critical";;
  *) die "no warn at 84%: $out";;
esac

# --- 4. critical fires and names the checkpoint path ------------------------
write_status 86 10
out="$(run s4)"
case "$out" in *CRITICAL*"$CKPT_DIR/s4.md"*) pass "critical names checkpoint path";; *) die "critical wrong: $out";; esac

# --- 5. critical repeats while no checkpoint exists -------------------------
out="$(run s4)"; out2="$(run s4)"
case "$out" in *CRITICAL*) : ;; *) out="";; esac
case "$out2" in *CRITICAL*) : ;; *) out2="";; esac
if [ -n "$out" ] && [ -n "$out2" ]; then pass "critical repeats every call"; else die "critical did not repeat"; fi

# --- 6. a checkpoint written after crit_since silences the nag; ack holds ---
echo "resume brief" > "$CKPT_DIR/s4.md"
out="$(run s4)"
if [ -z "$out" ]; then pass "checkpoint acknowledges critical"; else die "not silenced: $out"; fi
out="$(run s4)"
if [ -z "$out" ]; then pass "acknowledgment holds"; else die "ack did not hold: $out"; fi

# --- 7. re-arm on drop; fresh critical; back-dated checkpoint rejected -------
write_status 40 40
out="$(run s4)"
if [ -z "$out" ]; then pass "re-arm on drop is silent"; else die "re-arm not silent: $out"; fi
touch -t 202601010000 "$CKPT_DIR/s4.md"
write_status 86 10
out="$(run s4)"
case "$out" in *CRITICAL*) pass "fresh critical after re-arm";; *) die "no fresh critical: $out";; esac
out="$(run s4)"
case "$out" in *CRITICAL*) pass "back-dated checkpoint does not silence";; *) die "back-dated checkpoint silenced: $out";; esac

# --- 8. metric = max(session_pct, weekly_pct); binding reset time -----------
write_status 10 88   # weekly is the binding ceiling
out="$(run s8)"
case "$out" in
  *CRITICAL*"88%"*"2026-07-21T00:00:00Z"*) pass "max() picks weekly; weekly reset time used";;
  *) die "max/reset selection wrong: $out";;
esac

# --- 9. stale cache: silent even at 95% -------------------------------------
printf '{"polled_at":"2000-01-01T00:00:00Z","session_pct":95,"weekly_pct":95,"session_resets_at":"2026-07-17T19:00:00Z","weekly_resets_at":"2026-07-21T00:00:00Z"}' > "$STATUS"
out="$(run s9)"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "stale cache is silent"; else die "stale cache fired: rc=$rc out=$out"; fi

# --- 10. missing cache file: silent -----------------------------------------
rm -f "$STATUS"
out="$(run s10)"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "missing cache is silent"; else die "missing cache: rc=$rc out=$out"; fi

# --- 11. malformed JSON cache: silent, no crash -----------------------------
printf 'not json at all' > "$STATUS"
out="$(run s11)"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "malformed cache fails open"; else die "malformed cache: rc=$rc out=$out"; fi

# --- 12. missing session_id: silent -----------------------------------------
write_status 90 90
out="$(printf '{}' | bash "$HOOK")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "missing session_id is silent"; else die "missing session_id: rc=$rc out=$out"; fi

# --- 13. kill switch ---------------------------------------------------------
write_status 90 90
out="$(printf '{"session_id":"s13"}' | USAGE_BUDGET_DISABLE=1 bash "$HOOK")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "USAGE_BUDGET_DISABLE=1 silences"; else die "kill switch failed: rc=$rc out=$out"; fi

# --- 14. emitted JSON shape --------------------------------------------------
write_status 70 10
out="$(run s14)"
if printf '%s' "$out" | python3 -c '
import json, sys
d = json.load(sys.stdin)
assert isinstance(d["systemMessage"], str) and d["systemMessage"]
h = d["hookSpecificOutput"]
assert h["hookEventName"] == "PostToolUse"
assert isinstance(h["additionalContext"], str) and h["additionalContext"]
' 2>/dev/null; then pass "emitted JSON shape"; else die "bad JSON shape: $out"; fi

# --- 15. throttling ----------------------------------------------------------
write_status 40 40   # first call stamps the throttle clock
out="$(printf '{"session_id":"s15"}' | USAGE_BUDGET_CHECK_SECS=3600 bash "$HOOK")"
write_status 90 90   # would be critical if measured
out2="$(printf '{"session_id":"s15"}' | USAGE_BUDGET_CHECK_SECS=3600 bash "$HOOK")"
if [ -z "$out" ] && [ -z "$out2" ]; then pass "second call inside the window is throttled"; else die "throttle failed: out=$out out2=$out2"; fi

# --- 16. session-id sanitization ---------------------------------------------
write_status 40 40
printf '{"session_id":"%s"}' 'a/b c:d' | bash "$HOOK" >/dev/null
if [ -f "$SESSION_DIR/a_b_c_d.json" ]; then pass "session-id sanitized into state path"; else die "state file not at sanitized path"; fi

# --- 17. grammar regression: exact directive strings -------------------------
write_status 70 10
warn_out="$(run s17w)"
write_status 10 86
crit_out="$(run s17c)"
if python3 - "$warn_out" "$crit_out" "$CKPT_DIR/s17c.md" <<'PYEOF'
import json, sys
warn = json.loads(sys.argv[1])
crit = json.loads(sys.argv[2])
ckpt = sys.argv[3]
w_ctx = (
    "Usage-budget warning: this account's usage is at 70% of its weekly/session "
    "limit. Consider steering toward a safe pause point in the next hour."
)
c_ctx = (
    "Usage-budget CRITICAL: usage is at 86%, close to the account limit "
    "(resets 2026-07-21T00:00:00Z). Stop new work, commit and push what's in "
    "progress, and write a checkpoint file at " + ckpt + " — this message will "
    "repeat until you do."
)
assert warn["hookSpecificOutput"]["additionalContext"] == w_ctx, "warn text drifted"
assert crit["hookSpecificOutput"]["additionalContext"] == c_ctx, "critical text drifted"
assert warn["systemMessage"] == "Usage budget: account usage at 70% of the weekly/session limit. Steering toward a pause point."
assert crit["systemMessage"] == "Usage budget CRITICAL: account usage at 86%. Checkpoint required."
PYEOF
then pass "grammar regression: exact strings"; else die "directive prose drifted from spec"; fi

echo ""
if [ "$fail" -eq 0 ]; then
  echo "test_usage_budget: OK"
  exit 0
else
  echo "test_usage_budget: FAIL"
  exit 1
fi
