#!/bin/bash
# test_hooks_harvest.sh — exercises the two metrics hooks in isolation.
#
# Both hooks resolve their tool + write path from $HOME/.claude, so every case
# runs under an isolated HOME=$TMP; the real ~/.claude is NEVER touched. Hooks
# must ALWAYS exit 0 (a broken hook must never break a session) and never write
# anything when the input is malformed or points nowhere.
#
# macOS bash-3.2 portable: set -u, a fails counter, PASS/FAIL lines, non-zero
# exit if anything fails.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"           # payload/tools
HOOKS="$(cd "$HERE/../../hooks" && pwd)"  # payload/hooks
HARVEST="$HOOKS/harvest-metrics.sh"
PRECOMPACT="$HOOKS/precompact-event.sh"

fails=0
pass() { printf 'PASS - %s\n' "$1"; }
fail() { printf 'FAIL - %s\n' "$1"; fails=$((fails + 1)); }

for f in "$HARVEST" "$PRECOMPACT"; do
  if [ ! -f "$f" ]; then
    echo "FAIL - hook not found: $f (RED: build it first)"
    exit 1
  fi
done

# bash -n (syntax) on both hooks.
bash -n "$HARVEST" && pass "harvest-metrics.sh parses (bash -n)" || fail "harvest-metrics.sh syntax"
bash -n "$PRECOMPACT" && pass "precompact-event.sh parses (bash -n)" || fail "precompact-event.sh syntax"

SANDBOX="$(mktemp -d 2>/dev/null || mktemp -d -t calhooks)"
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

# Each case gets a clean HOME with the tools copied to $HOME/.claude/tools.
# Copy every sibling tool module, not a hand-picked subset: harvest_metrics.py
# now imports obs_emit and assess_task (which itself imports plan_task, which
# imports route_role, which imports lint_roles) — a hardcoded two-file list
# silently bit-rots every time such a same-directory import is added. This
# mirrors the real installed layout, where every payload/tools/*.py lands in
# ~/.claude/tools/ together (see the "copy-if-absent seeds" test elsewhere in
# this suite).
fresh_home() {
  h="$SANDBOX/$1"
  rm -rf "$h"
  mkdir -p "$h/.claude/tools" "$h/.claude/metrics"
  cp "$TOOLS"/*.py "$h/.claude/tools/"
  printf '%s' "$h"
}

# A minimal but valid subagent transcript (one assistant turn with usage).
write_fixture() {
  ft="$1"
  mkdir -p "$(dirname "$ft")"
  cat > "$ft" <<'JSONL'
{"type":"user","sessionId":"hooksid","gitBranch":"main","timestamp":"2026-06-11T02:00:00.000Z","message":{"role":"user","content":"go"}}
{"type":"assistant","sessionId":"hooksid","gitBranch":"main","timestamp":"2026-06-11T02:00:01.000Z","message":{"role":"assistant","model":"claude-opus-4-8","id":"h1","usage":{"input_tokens":10,"output_tokens":3,"cache_read_input_tokens":0,"cache_creation_input_tokens":0},"content":[{"type":"tool_use","name":"Bash","id":"ht1","input":{}}]}}
{"type":"user","sessionId":"hooksid","gitBranch":"main","timestamp":"2026-06-11T02:00:02.000Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"ht1","is_error":false,"content":"7 passed"}]},"toolUseResult":{"stdout":"7 passed","interrupted":false}}
JSONL
}

metrics_lines() {
  # Count JSONL records across all month shards under $1/.claude/metrics.
  # Python keeps this a single clean integer even when no shard exists.
  python3 - "$1/.claude/metrics" <<'PY'
import glob, os, sys
d = sys.argv[1]
n = 0
for f in glob.glob(os.path.join(d, "*.jsonl")):
    with open(f) as fh:
        n += sum(1 for line in fh if line.strip())
print(n)
PY
}

# --- Case 1: valid hook JSON pointing at an agent transcript -----------------
H="$(fresh_home valid)"
FX="$H/projects/slug/hooksid/subagents/agent-hooktest.jsonl"
write_fixture "$FX"
JSON="$(printf '{"hook_event_name":"SubagentStop","session_id":"hooksid","transcript_path":"%s"}' "$FX")"
out="$(printf '%s' "$JSON" | env HOME="$H" bash "$HARVEST" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && pass "harvest: valid input exits 0" || fail "harvest: valid input exit $rc"
n="$(metrics_lines "$H")"
[ "$n" -ge 1 ] 2>/dev/null && pass "harvest: a metrics record was appended ($n)" || fail "harvest: no record appended ($n)"
# The appended record is a task record for our agent.
find "$H/.claude/metrics" -name '*.jsonl' -exec grep -l '"task_id":"agent-hooktest"' {} \; 2>/dev/null | grep -q . \
  && pass "harvest: record carries the agent task_id" || fail "harvest: task_id missing from record"

# --- Case 2: malformed stdin -> exit 0, nothing written ----------------------
H="$(fresh_home malformed)"
out="$(printf 'this is { not json' | env HOME="$H" bash "$HARVEST" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && pass "harvest: malformed stdin exits 0" || fail "harvest: malformed stdin exit $rc"
n="$(metrics_lines "$H")"
[ "$n" -eq 0 ] 2>/dev/null && pass "harvest: malformed stdin writes nothing" || fail "harvest: malformed stdin wrote $n record(s)"

# --- Case 3: empty stdin -> exit 0, nothing written --------------------------
H="$(fresh_home empty)"
out="$(printf '' | env HOME="$H" bash "$HARVEST" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && pass "harvest: empty stdin exits 0" || fail "harvest: empty stdin exit $rc"
[ "$(metrics_lines "$H")" -eq 0 ] 2>/dev/null && pass "harvest: empty stdin writes nothing" || fail "harvest: empty stdin wrote a record"

# --- Case 4: transcript path that does not exist -> exit 0, nothing written --
H="$(fresh_home missingfile)"
JSON="$(printf '{"hook_event_name":"SubagentStop","session_id":"x","transcript_path":"%s/nope/agent-x.jsonl"}' "$H")"
out="$(printf '%s' "$JSON" | env HOME="$H" bash "$HARVEST" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && pass "harvest: missing transcript exits 0" || fail "harvest: missing transcript exit $rc"
[ "$(metrics_lines "$H")" -eq 0 ] 2>/dev/null && pass "harvest: missing transcript writes nothing" || fail "harvest: missing transcript wrote a record"

# --- Case 5: precompact-event.sh appends a compaction record -----------------
H="$(fresh_home precompact)"
JSON='{"hook_event_name":"PreCompact","session_id":"compact-sid"}'
out="$(printf '%s' "$JSON" | env HOME="$H" bash "$PRECOMPACT" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && pass "precompact: exits 0" || fail "precompact: exit $rc"
find "$H/.claude/metrics" -name '*.jsonl' -exec grep -l '"kind":"compaction"' {} \; 2>/dev/null | grep -q . \
  && pass "precompact: compaction record appended" || fail "precompact: no compaction record"
find "$H/.claude/metrics" -name '*.jsonl' -exec grep -l '"session_id":"compact-sid"' {} \; 2>/dev/null | grep -q . \
  && pass "precompact: record carries session_id" || fail "precompact: session_id missing"

# --- Case 6: precompact with malformed stdin still exits 0 -------------------
H="$(fresh_home precompact_bad)"
out="$(printf 'garbage' | env HOME="$H" bash "$PRECOMPACT" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && pass "precompact: malformed stdin exits 0" || fail "precompact: malformed stdin exit $rc"

echo "---"
if [ "$fails" -eq 0 ]; then
  echo "hook harvest tests: OK"
  exit 0
else
  echo "hook harvest tests: $fails FAILED"
  exit 1
fi
