#!/bin/bash
# test_context_budget.sh — PostToolUse context-budget hook: measurement,
# warn/critical tiers, checkpoint acknowledgment, re-arm, throttling,
# fail-open, and the fixed-string grammar regression on the directive prose.
set -u

HOOK="$(cd "$(dirname "$0")/../../hooks" && pwd)/context-budget.sh"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export CLAUDE_DIR="$TMP/claude"
export METRICS_DIR="$TMP/metrics"
export CONTEXT_BUDGET_CHECK_SECS=0   # disable throttling unless a case overrides it

TRANSCRIPT="$TMP/transcript.jsonl"
CKPT_DIR="$METRICS_DIR/state/budget/checkpoints"

# write_transcript INPUT CACHE_READ CACHE_CREATION — a user record, then one
# main-loop assistant record whose usage fields sum to the target occupancy.
write_transcript() {
  printf '%s\n%s\n' \
    '{"type":"user","isSidechain":false,"message":{"role":"user","content":"x"}}' \
    "{\"type\":\"assistant\",\"isSidechain\":false,\"message\":{\"usage\":{\"input_tokens\":$1,\"cache_read_input_tokens\":$2,\"cache_creation_input_tokens\":$3}}}" \
    > "$TRANSCRIPT"
}

# run SESSION_ID — invoke the hook with a well-formed payload; prints stdout.
run() {
  printf '{"session_id":"%s","transcript_path":"%s"}' "$1" "$TRANSCRIPT" | bash "$HOOK"
}

# --- 1. below both thresholds: silent, exit 0 --------------------------------
write_transcript 20000 30000 10000   # 60,000 = 40%
out="$(run s1)"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "below thresholds is silent"; else die "below thresholds: rc=$rc out=$out"; fi

# --- 2. warn fires once per cycle ---------------------------------------------
write_transcript 10000 90000 10000   # 110,000 = 73%
out="$(run s2)"
case "$out" in *"Steering toward a pause point."*) pass "warn fires at 73%";; *) die "warn missing: $out";; esac
out2="$(run s2)"
if [ -z "$out2" ]; then pass "warn does not repeat"; else die "warn repeated: $out2"; fi

# --- 3. critical names the checkpoint path ------------------------------------
write_transcript 30000 90000 10000   # 130,000 = 86%
out="$(run s3)"
case "$out" in *"CRITICAL"*"$CKPT_DIR/s3.md"*) pass "critical names checkpoint path";; *) die "critical wrong: $out";; esac

# --- 4. critical repeats while no checkpoint exists ---------------------------
out="$(run s3)"
out2="$(run s3)"
case "$out" in *"CRITICAL"*) : ;; *) out="" ;; esac
case "$out2" in *"CRITICAL"*) : ;; *) out2="" ;; esac
if [ -n "$out" ] && [ -n "$out2" ]; then pass "critical repeats every call"; else die "critical did not repeat"; fi

# --- 5. a checkpoint written after crit_since silences the nag ----------------
echo "resume brief" > "$CKPT_DIR/s3.md"
out="$(run s3)"
if [ -z "$out" ]; then pass "checkpoint acknowledges critical"; else die "not silenced: $out"; fi
out="$(run s3)"
if [ -z "$out" ]; then pass "acknowledgment holds"; else die "ack did not hold: $out"; fi

# --- 6. re-arm on drop; fresh critical; back-dated checkpoint rejected --------
write_transcript 20000 30000 10000   # 60,000 = 40%: drops below the warn threshold
out="$(run s3)"
if [ -z "$out" ]; then pass "re-arm on drop is silent"; else die "re-arm not silent: $out"; fi
touch -t 202601010000 "$CKPT_DIR/s3.md"   # back-date the old resume brief
write_transcript 30000 90000 10000   # climb back to 130,000 = 86%
out="$(run s3)"
case "$out" in *"CRITICAL"*) pass "fresh critical after re-arm";; *) die "no fresh critical: $out";; esac
out="$(run s3)"
case "$out" in *"CRITICAL"*) pass "back-dated checkpoint does not silence";; *) die "back-dated checkpoint silenced: $out";; esac

# --- 7. malformed stdin: silent, exit 0 ----------------------------------------
out="$(printf 'not json' | bash "$HOOK")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "malformed stdin fails open"; else die "malformed stdin: rc=$rc out=$out"; fi

# --- 8. missing transcript_path / nonexistent file: silent ---------------------
out="$(printf '{"session_id":"s8"}' | bash "$HOOK")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "missing transcript_path is silent"; else die "missing transcript_path: rc=$rc out=$out"; fi
out="$(printf '{"session_id":"s8","transcript_path":"%s"}' "$TMP/nope.jsonl" | bash "$HOOK")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "nonexistent transcript is silent"; else die "nonexistent transcript: rc=$rc out=$out"; fi

# --- 9. sidechain records are skipped; the main-loop record wins ----------------
{
  printf '%s\n' '{"type":"assistant","isSidechain":false,"message":{"usage":{"input_tokens":20000,"cache_read_input_tokens":30000,"cache_creation_input_tokens":10000}}}'
  printf '%s\n' '{"type":"assistant","isSidechain":true,"message":{"usage":{"input_tokens":140000,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}}'
  printf '%s\n' '{"type":"assistant","isSidechain":true,"message":{"usage":{"input_tokens":145000,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}}'
} > "$TRANSCRIPT"
out="$(run s9)"
if [ -z "$out" ]; then pass "sidechain usage ignored (main record wins)"; else die "sidechain leaked: $out"; fi

# --- 10. kill switch -------------------------------------------------------------
write_transcript 30000 90000 10000   # 130,000 = 86%
out="$(printf '{"session_id":"s10","transcript_path":"%s"}' "$TRANSCRIPT" | CONTEXT_BUDGET_DISABLE=1 bash "$HOOK")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "CONTEXT_BUDGET_DISABLE=1 silences"; else die "kill switch failed: rc=$rc out=$out"; fi

# --- 11. emitted JSON shape -------------------------------------------------------
write_transcript 10000 90000 10000   # 110,000 = 73%
out="$(run s11)"
if printf '%s' "$out" | python3 -c '
import json, sys
d = json.load(sys.stdin)
assert isinstance(d["systemMessage"], str) and d["systemMessage"]
h = d["hookSpecificOutput"]
assert h["hookEventName"] == "PostToolUse"
assert isinstance(h["additionalContext"], str) and h["additionalContext"]
' 2>/dev/null; then pass "emitted JSON shape"; else die "bad JSON shape: $out"; fi

# --- 12. throttling ----------------------------------------------------------------
write_transcript 20000 30000 10000   # 60,000: first call measures and stamps the clock
out="$(printf '{"session_id":"s12","transcript_path":"%s"}' "$TRANSCRIPT" | CONTEXT_BUDGET_CHECK_SECS=3600 bash "$HOOK")"
write_transcript 30000 90000 10000   # 130,000: would be critical if measured
out2="$(printf '{"session_id":"s12","transcript_path":"%s"}' "$TRANSCRIPT" | CONTEXT_BUDGET_CHECK_SECS=3600 bash "$HOOK")"
if [ -z "$out" ] && [ -z "$out2" ]; then pass "second call inside the window is throttled"; else die "throttle failed: out=$out out2=$out2"; fi

# --- 13. grammar regression: exact directive strings --------------------------------
write_transcript 10000 90000 10000   # 110,000 = 73%
warn_out="$(run s13w)"
write_transcript 30000 90000 10000   # 130,000 = 86%
crit_out="$(run s13c)"
if python3 - "$warn_out" "$crit_out" "$CKPT_DIR/s13c.md" <<'PYEOF'
import json, sys
warn = json.loads(sys.argv[1])
crit = json.loads(sys.argv[2])
ckpt = sys.argv[3]
w_expected = (
    "Context-budget warning: this session's context window is at 73% of its "
    "150000-token budget (110000 tokens). Begin steering toward a safe pause "
    "point: finish the current step, commit and push work in progress, and "
    "update your ledger and todos. A critical reminder will fire at 85% and "
    "will repeat until you write a checkpoint file."
)
c_expected = (
    "Context-budget CRITICAL: this session's context window is at 86% of its "
    "150000-token budget (130000 tokens). Reach a safe pause point now: "
    "(1) commit and push all work in progress; (2) update your progress ledger "
    "and todos; (3) write a resume brief to " + ckpt + " covering task state, "
    "branch names, next steps, and key file paths. This reminder repeats on "
    "every tool call until that file exists."
)
assert warn["hookSpecificOutput"]["additionalContext"] == w_expected, "warn text drifted"
assert crit["hookSpecificOutput"]["additionalContext"] == c_expected, "critical text drifted"
assert warn["systemMessage"] == "Context budget: 110000 of 150000 tokens used (73%). Steering toward a pause point."
assert crit["systemMessage"] == "Context budget CRITICAL: 130000 of 150000 tokens used (86%). Checkpoint required."
PYEOF
then pass "grammar regression: exact strings"; else die "directive prose drifted from spec"; fi

echo ""
if [ "$fail" -eq 0 ]; then
  echo "test_context_budget: OK"
  exit 0
else
  echo "test_context_budget: FAIL"
  exit 1
fi
