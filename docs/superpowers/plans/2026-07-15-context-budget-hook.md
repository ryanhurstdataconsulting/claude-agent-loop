# Context-Budget Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-07-15-context-budget-hook-design.md` (commit 10d6825). The spec is authoritative; this plan reproduces every value it pins.

**Goal:** A PostToolUse hook that watches the session's context-window occupancy and steers the agent to a durable, resumable pause point before auto-compaction can destroy working state.

**Architecture:** One new hook (`payload/hooks/context-budget.sh`, bash wrapper + embedded Python heredoc in the house style) fires after every tool call, reads the newest main-loop assistant `usage` record from the session transcript's 256 KB tail, and compares occupancy against a 150k-token budget. At 70% it warns once per cycle; from 85% it repeats a checkpoint directive on every tool call until a resume-brief file verifiably exists on disk. Per-session JSON state under `$METRICS_DIR/state/budget/` carries the throttle clock, tier flags, and acknowledgment; dropping back below the warn threshold re-arms everything.

**Tech Stack:** bash (macOS 3.2-portable) + Python 3 stdlib only (`json`, `os`, `re`, `sys`, `tempfile`, `time`). No new dependencies. Tests are a plain bash script auto-discovered by `payload/tools/tests/run_all.sh`.

## Global Constraints

- **House style:** bash wrapper with `set -u`; stdin captured via `INPUT="$(cat 2>/dev/null || true)"`; Python invoked as `HOOK_JSON="$INPUT" METRICS_DIR="$METRICS_DIR" python3 <<'PY' || true`; defensive JSON parse (any failure → `{}`); Python ends with `os._exit(0)`; the script ends with `exit 0`. Model file: `payload/hooks/precompact-event.sh`.
- **Fail-open, always exit 0.** Any internal failure degrades to silence. The hook never blocks a tool call and never exits nonzero.
- **Env contract (exact defaults):** `CONTEXT_BUDGET_TOKENS=150000` (unparseable or < 1000 → default); `CONTEXT_BUDGET_WARN_PCT=70`; `CONTEXT_BUDGET_CRIT_PCT=85` (if warn ≥ crit after parsing, both reset to 70/85); `CONTEXT_BUDGET_CHECK_SECS=30` (0 disables throttling — used by tests; negative or unparseable → default); `CONTEXT_BUDGET_DISABLE=1` is the kill switch; `CLAUDE_DIR` defaults to `$HOME/.claude`; `METRICS_DIR` defaults to `$CLAUDE_DIR/metrics`.
- **Measurement:** open the transcript in binary, seek `max(0, size - 262144)`, read to end, decode UTF-8 with `errors="replace"`, split on `"\n"`, drop the first line when the seek offset was > 0, iterate the lines **in reverse**, skip records with `isSidechain` true, and take the first record with `type == "assistant"` and a dict `message.usage`. `occupancy = input_tokens + cache_read_input_tokens + cache_creation_input_tokens` (each `usage.get(field, 0) or 0`). Occupancy 0, no match, or an unreadable transcript = "no reading" → silent; never fires a tier.
- **Arithmetic:** `percent = occupancy * 100 // budget` (integer floor). `{occupancy}` and `{budget}` render as plain integers — no thousands separators. `{percent}` and `{crit_pct}` render as integers.
- **State:** `$METRICS_DIR/state/budget/<safe_session_id>.json` with `safe_session_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id))[:128]`. Schema: `{"last_check_ts": 0.0, "warn_fired": false, "crit_since": null, "checkpoint_ack": false}`. Atomic writes (temp file in the same directory + `os.replace`). Missing or corrupt state loads as defaults. Both `state/budget/` and `state/budget/checkpoints/` are created on first use.
- **Checkpoint artifact:** `$METRICS_DIR/state/budget/checkpoints/<safe_session_id>.md`. The hook only ever **stats** it — it never writes or deletes it. Acknowledgment requires `mtime >= int(crit_since)` (the `int()` floor tolerates one-second-resolution filesystems).
- **Output shape:** when firing, exactly one JSON object on stdout — `{"systemMessage": "<one-liner>", "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "<directive>"}}`. Silence = no stdout at all.
- **The four message strings are pinned verbatim** (they appear in Task 1's code and in test case 13). Changing a single character is a defect; the fixed-string grammar-regression test enforces this.
- **No changes to `precompact-event.sh`** or any other existing hook.
- **Commit protocol:** three-section body — `(1) Task & Change` / `(2) Tests created or modified` / `(3) Test results — evidence` (paste real output). Stage explicitly with `git add <paths>`; never `git add -A`. End commits with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **Grammar gate:** user-facing prose changes pass `python3 ~/.claude/tools/prose_grammar_gate.py <file>` before committing. If the gate flags a pre-existing issue in a file you touched, fix it too.

## File Structure

| File | Change | Owner task |
|---|---|---|
| `payload/hooks/context-budget.sh` | Create — the hook | Task 1 |
| `payload/tools/tests/test_context_budget.sh` | Create — 13-case suite | Task 1 |
| `payload/MANIFEST` | Add one `link-file` line to the hooks block | Task 2 |
| `payload/fragments/settings.fragment.json` | Add the `PostToolUse` group | Task 2 |
| `README.md` | Add one hooks-table row | Task 2 |
| `ARCHITECTURE.md` | Add one runtime-layer bullet | Task 2 |
| `INSTALL.md` | Add the PostToolUse line to the merge example; fix "four" → "five" | Task 2 |
| `CHANGELOG.md` | Add the `[2.1.0]` entry | Task 2 |

---

### Task 1: The hook and its 13-case test suite

**Files:**
- Create: `payload/hooks/context-budget.sh`
- Test: `payload/tools/tests/test_context_budget.sh`

**Interfaces:**
- Consumes: nothing from other tasks. Reads hook JSON (`session_id`, `transcript_path`) on stdin; honors the env contract in Global Constraints.
- Produces: an executable hook at `payload/hooks/context-budget.sh` — the exact path Task 2's MANIFEST line and settings fragment reference.

- [ ] **Step 1: Write the failing test suite**

Create `payload/tools/tests/test_context_budget.sh` with exactly this content:

```bash
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
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `cd ~/dev/claude-agent-loop && bash payload/tools/tests/test_context_budget.sh; echo "exit=$?"`

Expected: the hook file does not exist, so `bash "$HOOK"` exits 127 with empty stdout. Every check that asserts emitted output prints `FAIL - …`; checks that assert silence spuriously pass (empty output looks silent) — that is fine at this stage. The last lines are `test_context_budget: FAIL` and `exit=1`.

- [ ] **Step 3: Write the hook**

Create `payload/hooks/context-budget.sh` with exactly this content:

```bash
#!/bin/bash
# context-budget.sh — PostToolUse hook: watch the session's context-window
# occupancy and force a durable pause point before auto-compaction.
#
# After every tool call, reads the newest main-loop assistant usage record from
# the session transcript (256 KB tail) and compares occupancy
# (input_tokens + cache_read_input_tokens + cache_creation_input_tokens)
# against CONTEXT_BUDGET_TOKENS (default 150000):
#   - at CONTEXT_BUDGET_WARN_PCT (70%): one warning per cycle — steer the agent
#     toward a safe pause point;
#   - at CONTEXT_BUDGET_CRIT_PCT (85%): a checkpoint directive that repeats on
#     EVERY tool call until a resume brief exists at
#     $METRICS_DIR/state/budget/checkpoints/<session>.md with
#     mtime >= int(crit_since).
# Dropping back below the warn threshold (e.g. after a compaction) re-arms both
# tiers. Fail-open: any internal failure degrades to silence, and the hook
# always exits 0. Kill switch: CONTEXT_BUDGET_DISABLE=1.
set -u

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
METRICS_DIR="${METRICS_DIR:-$CLAUDE_DIR/metrics}"

if [ "${CONTEXT_BUDGET_DISABLE:-0}" = "1" ]; then
  exit 0
fi

INPUT="$(cat 2>/dev/null || true)"

HOOK_JSON="$INPUT" METRICS_DIR="$METRICS_DIR" python3 <<'PY' || true
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
    transcript_path = data.get("transcript_path")
    if not session_id or not transcript_path:
        bail()

    metrics_dir = os.environ.get("METRICS_DIR", "")

    def int_env(name, default):
        try:
            return int(os.environ.get(name, ""))
        except Exception:
            return default

    budget = int_env("CONTEXT_BUDGET_TOKENS", 150000)
    if budget < 1000:
        budget = 150000
    warn_pct = int_env("CONTEXT_BUDGET_WARN_PCT", 70)
    crit_pct = int_env("CONTEXT_BUDGET_CRIT_PCT", 85)
    if warn_pct >= crit_pct:
        warn_pct, crit_pct = 70, 85
    check_secs = int_env("CONTEXT_BUDGET_CHECK_SECS", 30)
    if check_secs < 0:
        check_secs = 30

    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id))[:128]
    state_dir = os.path.join(metrics_dir, "state", "budget")
    ckpt_dir = os.path.join(state_dir, "checkpoints")
    os.makedirs(ckpt_dir, exist_ok=True)
    state_path = os.path.join(state_dir, safe + ".json")
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
        fd, tmp = tempfile.mkstemp(dir=state_dir, prefix=safe + ".", suffix=".tmp")
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

    def measure():
        """Newest main-loop assistant usage record in the transcript tail, or 0."""
        try:
            size = os.path.getsize(transcript_path)
            with open(transcript_path, "rb") as fh:
                offset = max(0, size - 262144)
                fh.seek(offset)
                text = fh.read().decode("utf-8", errors="replace")
        except Exception:
            return 0
        lines = text.split("\n")
        if offset > 0 and lines:
            lines = lines[1:]  # the first line after a mid-file seek is truncated
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if not isinstance(rec, dict) or rec.get("isSidechain") is True:
                continue
            if rec.get("type") != "assistant":
                continue
            message = rec.get("message")
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            return ((usage.get("input_tokens", 0) or 0)
                    + (usage.get("cache_read_input_tokens", 0) or 0)
                    + (usage.get("cache_creation_input_tokens", 0) or 0))
        return 0

    def emit(tier, occupancy):
        percent = occupancy * 100 // budget
        if tier == "warn":
            msg = ("Context budget: %d of %d tokens used (%d%%). "
                   "Steering toward a pause point." % (occupancy, budget, percent))
            ctx = ("Context-budget warning: this session's context window is at "
                   "%d%% of its %d-token budget (%d tokens). Begin steering "
                   "toward a safe pause point: finish the current step, commit "
                   "and push work in progress, and update your ledger and todos. "
                   "A critical reminder will fire at %d%% and will repeat until "
                   "you write a checkpoint file."
                   % (percent, budget, occupancy, crit_pct))
        else:
            msg = ("Context budget CRITICAL: %d of %d tokens used (%d%%). "
                   "Checkpoint required." % (occupancy, budget, percent))
            ctx = ("Context-budget CRITICAL: this session's context window is at "
                   "%d%% of its %d-token budget (%d tokens). Reach a safe pause "
                   "point now: (1) commit and push all work in progress; "
                   "(2) update your progress ledger and todos; (3) write a resume "
                   "brief to %s covering task state, branch names, next steps, "
                   "and key file paths. This reminder repeats on every tool call "
                   "until that file exists."
                   % (percent, budget, occupancy, ckpt_path))
        out = {
            "systemMessage": msg,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": ctx,
            },
        }
        sys.stdout.write(json.dumps(out))

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
        occupancy = measure()
        if occupancy <= 0:
            bail()  # fail-open: no reading, no nag this call
        percent = occupancy * 100 // budget
        if percent < warn_pct:
            reset_state()  # compaction (or a new task) dropped occupancy: re-arm
            save_state()
            bail()
        emit("crit", occupancy)
        bail()

    # Normal path: throttled measurement.
    if now - state["last_check_ts"] < check_secs:
        bail()
    state["last_check_ts"] = now
    occupancy = measure()
    if occupancy <= 0:
        save_state()
        bail()
    percent = occupancy * 100 // budget
    if percent >= crit_pct:
        if state["crit_since"] is None:
            state["crit_since"] = now
            save_state()
            emit("crit", occupancy)
        else:
            # crit_since set with checkpoint_ack true: the acknowledgment
            # holds until occupancy drops below the warn threshold.
            save_state()
        bail()
    if percent >= warn_pct:
        if not state["warn_fired"]:
            state["warn_fired"] = True
            save_state()
            emit("warn", occupancy)
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
```

Then make it executable:

Run: `chmod +x payload/hooks/context-budget.sh payload/tools/tests/test_context_budget.sh`

- [ ] **Step 4: Run the suite to verify it passes**

Run: `cd ~/dev/claude-agent-loop && bash payload/tools/tests/test_context_budget.sh; echo "exit=$?"`

Expected — these 18 lines, then a blank line, `test_context_budget: OK`, and `exit=0`:

```
PASS - below thresholds is silent
PASS - warn fires at 73%
PASS - warn does not repeat
PASS - critical names checkpoint path
PASS - critical repeats every call
PASS - checkpoint acknowledges critical
PASS - acknowledgment holds
PASS - re-arm on drop is silent
PASS - fresh critical after re-arm
PASS - back-dated checkpoint does not silence
PASS - malformed stdin fails open
PASS - missing transcript_path is silent
PASS - nonexistent transcript is silent
PASS - sidechain usage ignored (main record wins)
PASS - CONTEXT_BUDGET_DISABLE=1 silences
PASS - emitted JSON shape
PASS - second call inside the window is throttled
PASS - grammar regression: exact strings
```

- [ ] **Step 5: Run the whole test suite**

Run: `cd ~/dev/claude-agent-loop/payload/tools/tests && bash run_all.sh > /tmp/run_all_task1.log 2>&1; tail -3 /tmp/run_all_task1.log`

Expected final line: `run_all: 29 suites, 0 failed` (28 existing suites + this one; exit 0).

- [ ] **Step 6: Commit**

```bash
cd ~/dev/claude-agent-loop
git add payload/hooks/context-budget.sh payload/tools/tests/test_context_budget.sh
git commit -F - <<'MSG'
feat(hooks): add the PostToolUse context-budget hook with a verified checkpoint

(1) Task & Change
Implements Component 1 and Component 4 of the context-budget spec
(docs/superpowers/specs/2026-07-15-context-budget-hook-design.md, 10d6825).
payload/hooks/context-budget.sh measures context-window occupancy from the
session transcript's 256 KB tail (newest non-sidechain assistant usage record),
warns once at 70% of the 150k-token budget, and from 85% repeats a checkpoint
directive on every tool call until a resume brief exists at
$METRICS_DIR/state/budget/checkpoints/<session>.md with mtime >= int(crit_since).
Dropping below the warn threshold re-arms both tiers. Fail-open, always exits 0;
kill switch CONTEXT_BUDGET_DISABLE=1.

(2) Tests created / modified
- payload/tools/tests/test_context_budget.sh — 13 cases: silence below
  thresholds, warn-once, critical naming the checkpoint path, repeat-until-
  checkpoint, mtime-verified acknowledgment, re-arm plus back-dated-checkpoint
  rejection, malformed stdin, missing transcript, sidechain skipping, the kill
  switch, emitted JSON shape, throttling, and the fixed-string grammar
  regression on both directive strings.

(3) Test results — evidence
$ bash payload/tools/tests/test_context_budget.sh
[paste the 18 PASS lines and the final "test_context_budget: OK" from the real run]
$ bash run_all.sh   # from payload/tools/tests/
run_all: 29 suites, 0 failed

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
MSG
```

Replace the bracketed line with the actual output from Steps 4–5 before committing.

---

### Task 2: Wiring and documentation

**Files:**
- Modify: `payload/MANIFEST` (the `# --- hooks/ ---` block, lines 201–205)
- Modify: `payload/fragments/settings.fragment.json` (the `"hooks"` object)
- Modify: `README.md` (the hooks table, lines 187–192)
- Modify: `ARCHITECTURE.md` (the runtime-loop bullets, lines 161–164)
- Modify: `INSTALL.md` (section 4's `hooks` bullet and JSON example, lines 100–112)
- Modify: `CHANGELOG.md` (new entry above `## [2.0.0] - 2026-07-07`)

**Interfaces:**
- Consumes: `payload/hooks/context-budget.sh` from Task 1 (the MANIFEST `link-file` target and the `$HOME/.claude/hooks/context-budget.sh` command path must resolve to it).
- Produces: nothing consumed by later tasks (this is the final task).

- [ ] **Step 1: Add the MANIFEST link-file line**

In `payload/MANIFEST`, replace:

```
link-file hooks/precompact-event.sh
link-file hooks/auto-update.sh
```

with:

```
link-file hooks/precompact-event.sh
link-file hooks/auto-update.sh
link-file hooks/context-budget.sh
```

- [ ] **Step 2: Add the PostToolUse group to the settings fragment**

In `payload/fragments/settings.fragment.json`, replace:

```json
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/hooks/precompact-event.sh"
          }
        ]
      }
    ],
```

with:

```json
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/hooks/precompact-event.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/hooks/context-budget.sh"
          }
        ]
      }
    ],
```

- [ ] **Step 3: Verify the fragment still parses**

Run: `cd ~/dev/claude-agent-loop && python3 -m json.tool payload/fragments/settings.fragment.json > /dev/null && echo FRAGMENT_OK`

Expected: `FRAGMENT_OK`

- [ ] **Step 4: Add the README hooks-table row**

In `README.md`, after the row that begins `| `harvest-metrics.sh` | SubagentStop + SessionEnd |`, add this row:

```markdown
| `context-budget.sh` | PostToolUse | Watches context-window occupancy from the session transcript; warns at 70% of the 150k budget and, from 85%, repeats a pause-point directive on every tool call until a resume-brief checkpoint file exists. |
```

- [ ] **Step 5: Add the ARCHITECTURE.md runtime-layer bullet**

In `ARCHITECTURE.md`, directly after the bullet that ends `See the metrics store contract below, and `LEARNING.md` for the whole self-learning layer.`, add:

```markdown
- **`payload/hooks/context-budget.sh`** (PostToolUse) watches the session's
  context-window occupancy from the transcript tail and steers the agent to a
  durable pause point — one warning at 70% of the token budget, then a repeating
  checkpoint directive from 85% until a resume brief exists on disk. It acts
  *before* compaction; `precompact-event.sh` records and escalates *after* it.
```

- [ ] **Step 6: Update the INSTALL.md merge example**

In `INSTALL.md`, replace:

```markdown
- **`hooks`** — add these four event groups (each only if a group with the same
  command is not already present), with `$HOME` replaced by your real home. The
  SessionStart hook injects the registry index; the other three passively
  harvest the metrics the loop learns from:
```

with:

```markdown
- **`hooks`** — add these five event groups (each only if a group with the same
  command is not already present), with `$HOME` replaced by your real home. The
  SessionStart hook injects the registry index; the PostToolUse hook watches the
  session's context budget; the other three passively harvest the metrics the
  loop learns from:
```

Then, in the JSON example just below it, replace:

```
  "PreCompact":   [ { "hooks": [ { "type": "command", "command": "$HOME/.claude/hooks/precompact-event.sh" } ] } ]
```

with:

```
  "PreCompact":   [ { "hooks": [ { "type": "command", "command": "$HOME/.claude/hooks/precompact-event.sh" } ] } ],
  "PostToolUse":  [ { "hooks": [ { "type": "command", "command": "$HOME/.claude/hooks/context-budget.sh" } ] } ]
```

- [ ] **Step 7: Add the CHANGELOG entry**

In `CHANGELOG.md`, replace:

```markdown
## [2.0.0] - 2026-07-07
```

with:

```markdown
## [2.1.0] - 2026-07-15

### Added

- **Context-budget hook** (`payload/hooks/context-budget.sh`, PostToolUse) —
  watches the session's context-window occupancy from the transcript tail and
  steers the agent to a durable pause point before auto-compaction can destroy
  working state: a single warning at 70% of the 150k-token budget, then a
  checkpoint directive from 85% that repeats on every tool call until a resume
  brief exists at `metrics/state/budget/checkpoints/<session>.md`. Fail-open,
  always exits 0; kill switch `CONTEXT_BUDGET_DISABLE=1`. Covered by the
  13-case `payload/tools/tests/test_context_budget.sh`, including a
  fixed-string grammar regression on the emitted directive prose.

## [2.0.0] - 2026-07-07
```

- [ ] **Step 8: Run the grammar gate on the four prose files**

Run: `cd ~/dev/claude-agent-loop && for f in README.md ARCHITECTURE.md INSTALL.md CHANGELOG.md; do python3 ~/.claude/tools/prose_grammar_gate.py "$f"; done`

Expected: `OK (0 issues)` for each file. If the gate flags a pre-existing issue in one of these files, fix it in this task (the grammar mandate covers pre-existing mistakes in files you touch) and re-run until clean.

- [ ] **Step 9: Re-run the whole test suite**

Run: `cd ~/dev/claude-agent-loop/payload/tools/tests && bash run_all.sh > /tmp/run_all_task2.log 2>&1; tail -3 /tmp/run_all_task2.log`

Expected final line: `run_all: 29 suites, 0 failed` — the regression net for the MANIFEST and fragment edits (the suite includes `test_install_symlinks.sh`).

- [ ] **Step 10: Commit**

```bash
cd ~/dev/claude-agent-loop
git add payload/MANIFEST payload/fragments/settings.fragment.json README.md ARCHITECTURE.md INSTALL.md CHANGELOG.md
git commit -F - <<'MSG'
feat(hooks): wire and document the context-budget hook (v2.1.0)

(1) Task & Change
Implements Components 2 and 3 of the context-budget spec
(docs/superpowers/specs/2026-07-15-context-budget-hook-design.md, 10d6825).
Adds the MANIFEST link-file line and the PostToolUse group in
payload/fragments/settings.fragment.json so install.sh links and registers the
hook; documents it in the README hooks table, the ARCHITECTURE runtime-loop
layer, the INSTALL settings-merge example (now five event groups), and a new
CHANGELOG [2.1.0] entry.

(2) Tests created / modified
- None added; no executable behavior changes in this task. Evidence:
  python3 -m json.tool parse of the fragment, the prose grammar gate on the
  four doc files, and the full suite re-run (test_install_symlinks.sh guards
  the MANIFEST edit).

(3) Test results — evidence
$ python3 -m json.tool payload/fragments/settings.fragment.json > /dev/null && echo FRAGMENT_OK
FRAGMENT_OK
$ for f in README.md ARCHITECTURE.md INSTALL.md CHANGELOG.md; do python3 ~/.claude/tools/prose_grammar_gate.py "$f"; done
[paste the four gate result lines from the real run]
$ bash run_all.sh   # from payload/tools/tests/
run_all: 29 suites, 0 failed

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
MSG
```

Replace the bracketed line with the actual output from Step 8 before committing.
