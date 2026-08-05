#!/bin/bash
# test_loop_close_hook.sh — SessionEnd hook that closes the loop unattended.
#
# The hook must close every ready work order, emit precise task records, leave a
# result file for SessionStart to surface, never double-count, never touch an
# unfinished work order, and swallow every failure at exit 0. macOS bash-3.2
# portable. Modeled on test_workorder_gate.sh.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$(cd "$HERE/../../hooks" && pwd)/loop-close.sh"
TOOLS="$(cd "$HERE/.." && pwd)"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
STATE="$TMP/state"; METRICS="$TMP/metrics"; PROJECTS="$TMP/projects"
mkdir -p "$STATE" "$METRICS" "$PROJECTS"

# write_wo <plan-id> <status1> [status2]
write_wo() {
  python3 - "$STATE" "$@" <<'PY'
import json, os, sys
state, pid = sys.argv[1], sys.argv[2]
statuses = sys.argv[3:]
wo = {"schema": 1, "plan_id": pid, "task": "t", "source": "plan",
      "created": "2026-07-30T18:00:00Z", "project": "proj", "git_branch": "main",
      "parts": [{"part_id": "p%d" % (i+1), "goal": "g%d" % (i+1), "status": s,
                 "role": "dba", "role_score": 4,
                 "skills": ["explain-analyze-query-tuning"], "model": "sonnet",
                 "agent_task_id": None, "log": {"ok": s == "done"},
                 "evidence": None, "verdict": None, "score": None}
                for i, s in enumerate(statuses)]}
os.makedirs(state, exist_ok=True)
open(os.path.join(state, pid + ".json"), "w").write(json.dumps(wo))
PY
}

run_hook() {
  printf '{"session_id":"%s","hook_event_name":"SessionEnd"}' "$1" \
    | env TOOLS_DIR="$TOOLS" METRICS_DIR="$METRICS" PROJECTS_DIR="$PROJECTS" \
          STATE_DIR="$STATE" CLAUDE_DIR="$TMP/claude" "${@:2}" bash "$HOOK"
}

count_records() {
  python3 -c "
import glob,sys
n=0
for f in glob.glob('$METRICS/*.jsonl'):
    n += sum(1 for l in open(f) if l.strip())
print(n)"
}

# 1. A ready work order is closed, emits a record per part, exits 0, silent.
write_wo wo-ready done done
out="$(run_hook sess-1)"; rc=$?
[ $rc -eq 0 ] && pass "1 exit 0" || die "1 exit $rc"
[ -z "$out" ] && pass "1 silent on stdout" || die "1 not silent (got: $out)"
n="$(count_records)"
[ "$n" = "4" ] && pass "1 emitted 4 records (2 task + 2 run)" || die "1 emitted $n, expected 4"

# 2. Records carry precise work-order attribution.
if python3 -c "
import glob,json,sys
recs=[json.loads(l) for f in glob.glob('$METRICS/*.jsonl') for l in open(f) if l.strip()]
task_recs = [r for r in recs if r['kind'] == 'task']
run_recs = [r for r in recs if r['kind'] == 'run']
assert len(task_recs) == 2, 'expected 2 task records, got %d' % len(task_recs)
assert len(run_recs) == 2, 'expected 2 run records, got %d' % len(run_recs)
assert all(r['resources_source']=='workorder' for r in task_recs), 'wrong source'
assert any('dba' in r['resources_deployed'] for r in task_recs), 'role missing'
" 2>/dev/null; then pass "2 records are precise and task-shaped"
else die "2 record shape wrong"; fi

# 3. The work order is stamped closed.
if python3 -c "
import json; assert json.load(open('$STATE/wo-ready.json')).get('closed_at')" 2>/dev/null
then pass "3 work order stamped closed"; else die "3 not stamped"; fi

# 4. A result file is left where SessionStart can find it.
[ -f "$METRICS/state/loop-close/sess-1.json" ] && pass "4 result file written" \
  || die "4 no result file"

# 5. Re-running closes nothing further — no double count.
run_hook sess-1b >/dev/null
n2="$(count_records)"
[ "$n2" = "4" ] && pass "5 no double count" || die "5 record count grew to $n2"

# 6. An unfinished work order is left alone.
write_wo wo-open done assigned
run_hook sess-2 >/dev/null
if python3 -c "
import json; assert not json.load(open('$STATE/wo-open.json')).get('closed_at')" 2>/dev/null
then pass "6 unfinished work order untouched"; else die "6 closed an open work order"; fi

# 7. Nothing ready -> no result file for that session (silence, not a stub).
run_hook sess-3 >/dev/null
[ ! -f "$METRICS/state/loop-close/sess-3.json" ] && pass "7 no-op leaves no artifact" \
  || die "7 wrote an artifact with nothing to close"

# 8. Kill switch.
write_wo wo-killed done
out="$(run_hook sess-4 LOOP_CLOSE_DISABLE=1)"; rc=$?
[ $rc -eq 0 ] && pass "8 kill switch: exit 0" || die "8 exit $rc"
if python3 -c "
import json; assert not json.load(open('$STATE/wo-killed.json')).get('closed_at')" 2>/dev/null
then pass "8 kill switch: nothing closed"; else die "8 kill switch closed anyway"; fi

# 9. Malformed hook JSON -> fails open, exit 0.
out="$(printf '{not json' | env TOOLS_DIR="$TOOLS" METRICS_DIR="$METRICS" \
  PROJECTS_DIR="$PROJECTS" STATE_DIR="$STATE" CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "9 malformed JSON: exit 0" || die "9 exit $rc"

# 10. Missing state directory -> fails open, exit 0.
out="$(printf '{"session_id":"s10"}' | env TOOLS_DIR="$TOOLS" METRICS_DIR="$METRICS" \
  PROJECTS_DIR="$PROJECTS" STATE_DIR="$TMP/gone" CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && pass "10 missing state dir: fails open" \
  || die "10 (rc=$rc out=$out)"

# 11. Unimportable tools -> fails open, exit 0.
out="$(printf '{"session_id":"s11"}' | env TOOLS_DIR="$TMP/nope" METRICS_DIR="$METRICS" \
  PROJECTS_DIR="$PROJECTS" STATE_DIR="$STATE" CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && pass "11 missing tools: fails open" \
  || die "11 (rc=$rc out=$out)"

# 12. Linking: a part whose id appears in a subagent transcript gets resolved.
mkdir -p "$PROJECTS/proj/sid/subagents"
printf '{"text":"plan_id : wo-link  part_id : p1"}\n' \
  > "$PROJECTS/proj/sid/subagents/agent-deadbeef.jsonl"
write_wo wo-link done
run_hook sess-5 >/dev/null
if python3 -c "
import json
w=json.load(open('$STATE/wo-link.json'))
assert w['parts'][0]['agent_task_id']=='agent-deadbeef', w['parts'][0]['agent_task_id']
" 2>/dev/null; then pass "12 part linked to its transcript"
else die "12 linking failed"; fi

if [ "$fail" -eq 0 ]; then
  echo "test_loop_close_hook: PASS"
  exit 0
fi
echo "test_loop_close_hook: FAIL"
exit 1
