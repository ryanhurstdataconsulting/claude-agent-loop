#!/bin/bash
# test_loop_close_hook.sh — SessionEnd hook that closes the loop unattended.
#
# The hook must close every ready plan, emit precise task records, leave a
# result file for SessionStart to surface, never double-count, never touch an
# unfinished plan, and swallow every failure at exit 0. macOS bash-3.2
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
BASE="$TMP/plans"; METRICS="$TMP/metrics"; PROJECTS="$TMP/projects"
mkdir -p "$BASE" "$METRICS" "$PROJECTS"

# Fixture ids: schema-2 plans require an embedded wo-YYYYMMDD- date so
# plan_task.save()/load() can derive the date-partitioned directory. Every
# fixture below shares the same day, so its on-disk path is always
# $DAY_DIR/<task_id>.json.
DAY_DIR="$BASE/2026-07-30"
READY_ID="wo-20260730-ready-100001"
OPEN_ID="wo-20260730-open-100002"
KILLED_ID="wo-20260730-killed-100003"
LINK_ID="wo-20260730-link-100004"

# write_wo <task-id> <status1> [status2...]
# Builds a schema-2 plan (task_id/steps/id/agent/agent_score) and persists it
# through plan_task.save() itself, so the fixture lands on disk exactly where
# loop_close.ready_plans() scans for it — no hand-rolled path logic here.
write_wo() {
  python3 - "$TOOLS" "$BASE" "$@" <<'PY'
import sys
tools, base, task_id = sys.argv[1], sys.argv[2], sys.argv[3]
statuses = sys.argv[4:]
sys.path.insert(0, tools)
import plan_task as pt

plan = {"schema": pt.SCHEMA, "task_id": task_id, "task": "t", "source": "plan",
        "created": "2026-07-30T18:00:00Z", "project": "proj", "git_branch": "main",
        "steps": [{"id": "p%d" % (i + 1), "goal": "g%d" % (i + 1), "status": s,
                   "agent": "dba", "agent_score": 4,
                   "skills": ["explain-analyze-query-tuning"], "model": "sonnet",
                   "agent_task_id": None, "return": {"ok": s == "done"},
                   "assessment": None}
                  for i, s in enumerate(statuses)]}
pt.save(base, plan)
PY
}

run_hook() {
  printf '{"session_id":"%s","hook_event_name":"SessionEnd"}' "$1" \
    | env TOOLS_DIR="$TOOLS" METRICS_DIR="$METRICS" PROJECTS_DIR="$PROJECTS" \
          BASE_DIR="$BASE" CLAUDE_DIR="$TMP/claude" "${@:2}" bash "$HOOK"
}

count_records() {
  python3 -c "
import glob,sys
n=0
for f in glob.glob('$METRICS/*.jsonl'):
    n += sum(1 for l in open(f) if l.strip())
print(n)"
}

# 1. A ready plan is closed, emits a record per step, exits 0, silent.
write_wo "$READY_ID" done done
out="$(run_hook sess-1)"; rc=$?
[ $rc -eq 0 ] && pass "1 exit 0" || die "1 exit $rc"
[ -z "$out" ] && pass "1 silent on stdout" || die "1 not silent (got: $out)"
n="$(count_records)"
[ "$n" = "4" ] && pass "1 emitted 4 records (2 task + 2 run)" || die "1 emitted $n, expected 4"

# 2. Records carry precise plan attribution.
if python3 -c "
import glob,json,sys
recs=[json.loads(l) for f in glob.glob('$METRICS/*.jsonl') for l in open(f) if l.strip()]
task_recs = [r for r in recs if r['kind'] == 'task']
run_recs = [r for r in recs if r['kind'] == 'run']
assert len(task_recs) == 2, 'expected 2 task records, got %d' % len(task_recs)
assert len(run_recs) == 2, 'expected 2 run records, got %d' % len(run_recs)
assert all(r['resources_source']=='workorder' for r in task_recs), 'wrong source'
assert any('dba' in r['resources_deployed'] for r in task_recs), 'agent missing'
" 2>/dev/null; then pass "2 records are precise and task-shaped"
else die "2 record shape wrong"; fi

# 3. The plan is stamped closed.
if python3 -c "
import json; assert json.load(open('$DAY_DIR/$READY_ID.json')).get('closed_at')" 2>/dev/null
then pass "3 plan stamped closed"; else die "3 not stamped"; fi

# 4. A result file is left where SessionStart can find it.
[ -f "$METRICS/state/loop-close/sess-1.json" ] && pass "4 result file written" \
  || die "4 no result file"

# 5. Re-running closes nothing further — no double count.
run_hook sess-1b >/dev/null
n2="$(count_records)"
[ "$n2" = "4" ] && pass "5 no double count" || die "5 record count grew to $n2"

# 6. An unfinished plan is left alone.
write_wo "$OPEN_ID" done assigned
run_hook sess-2 >/dev/null
if python3 -c "
import json; assert not json.load(open('$DAY_DIR/$OPEN_ID.json')).get('closed_at')" 2>/dev/null
then pass "6 unfinished plan untouched"; else die "6 closed an open plan"; fi

# 7. Nothing ready -> no result file for that session (silence, not a stub).
run_hook sess-3 >/dev/null
[ ! -f "$METRICS/state/loop-close/sess-3.json" ] && pass "7 no-op leaves no artifact" \
  || die "7 wrote an artifact with nothing to close"

# 8. Kill switch.
write_wo "$KILLED_ID" done
out="$(run_hook sess-4 LOOP_CLOSE_DISABLE=1)"; rc=$?
[ $rc -eq 0 ] && pass "8 kill switch: exit 0" || die "8 exit $rc"
if python3 -c "
import json; assert not json.load(open('$DAY_DIR/$KILLED_ID.json')).get('closed_at')" 2>/dev/null
then pass "8 kill switch: nothing closed"; else die "8 kill switch closed anyway"; fi

# 9. Malformed hook JSON -> fails open, exit 0.
out="$(printf '{not json' | env TOOLS_DIR="$TOOLS" METRICS_DIR="$METRICS" \
  PROJECTS_DIR="$PROJECTS" BASE_DIR="$BASE" CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "9 malformed JSON: exit 0" || die "9 exit $rc"

# 10. Missing base directory -> fails open, exit 0.
out="$(printf '{"session_id":"s10"}' | env TOOLS_DIR="$TOOLS" METRICS_DIR="$METRICS" \
  PROJECTS_DIR="$PROJECTS" BASE_DIR="$TMP/gone" CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && pass "10 missing base dir: fails open" \
  || die "10 (rc=$rc out=$out)"

# 11. Unimportable tools -> fails open, exit 0.
out="$(printf '{"session_id":"s11"}' | env TOOLS_DIR="$TMP/nope" METRICS_DIR="$METRICS" \
  PROJECTS_DIR="$PROJECTS" BASE_DIR="$BASE" CLAUDE_DIR="$TMP/claude" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && [ -z "$out" ] && pass "11 missing tools: fails open" \
  || die "11 (rc=$rc out=$out)"

# 12. Linking: a step whose id appears in a subagent transcript gets resolved.
mkdir -p "$PROJECTS/proj/sid/subagents"
printf '{"text":"task_id : %s  step_id : p1"}\n' "$LINK_ID" \
  > "$PROJECTS/proj/sid/subagents/agent-deadbeef.jsonl"
write_wo "$LINK_ID" done
run_hook sess-5 >/dev/null
if python3 -c "
import json
w=json.load(open('$DAY_DIR/$LINK_ID.json'))
assert w['steps'][0]['agent_task_id']=='agent-deadbeef', w['steps'][0]['agent_task_id']
" 2>/dev/null; then pass "12 step linked to its transcript"
else die "12 linking failed"; fi

if [ "$fail" -eq 0 ]; then
  echo "test_loop_close_hook: PASS"
  exit 0
fi
echo "test_loop_close_hook: FAIL"
exit 1
