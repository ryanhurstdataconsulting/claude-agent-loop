# Agent Observability Layer — Phase 1: Structured Event Log — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `obs.v1` structured event log — a stdlib-only, silent-fail, deterministic-ID event emitter, wired into every hook in the framework — so tool calls, gate decisions, skill invocations, and hook failures accumulate in `~/.claude/metrics/events/YYYY-MM-DD.ndjson` immediately, with nothing downstream required to read them yet.

**Architecture:** One new module (`obs_emit.py`) provides `emit()`, copying `harvest_metrics.py`'s exact atomic-append primitive (`os.open(O_WRONLY|O_APPEND|O_CREAT)` + single `os.write`) onto a new daily NDJSON file instead of a monthly shard. `trace_id`/`span_id` are pure sha256 functions of visible call arguments only (no clocks, no counters, no hidden state) so they are provably deterministic and restart-stable. A new hook script `obs-events.sh` binds `PreToolUse`/`PostToolUse`/`Stop` (no matcher — every tool, every turn) and emits `tool.pre`/`tool.post`/`turn.stop`. Four existing gate hooks get a one-line `gate.decision` call added at their existing choke-point functions. `pipeline-relay.sh` gets a `skill.invoked` call at its already-existing skill-name-extraction line. All ten `payload/hooks/*.sh` scripts get an identical 4-line `hook.error` trap block. Three **local-only** files under `~/.claude/hooks/` (a separate git repo, no remote) get the same two treatments as their own commit.

**Tech Stack:** Python 3 stdlib only (`hashlib`, `json`, `os`, `pathlib`, `datetime`, `signal`). Bash 3.2-portable wrappers (macOS default `/bin/bash`). `unittest` for Python tests (this repo's convention — no pytest anywhere in `claude-agent-loop`). Hand-rolled `pass()`/`die()` shell test harness for hook scripts, matching `test_workorder_gate.sh`.

## Global Constraints

- **Stdlib only** in every `payload/tools/*.py` and `payload/hooks/*.sh` file touched in this plan — no `pip install`, no third-party imports. (Confirmed existing invariant: `harvest_metrics.py`, `loop_close.py`, `make_brief.py` docstrings all state this explicitly.)
- **Fail-open, always exit 0.** No hook edited in this plan may change its existing exit-code behavior, its existing `allow`/`deny`/`block`/silent decision, or its existing output shape. Every new `obs_emit` call is wrapped so an exception inside it can never propagate out and change what the hook does.
- **No network I/O** anywhere in this plan. `obs_emit.py` writes to a local file only.
- **No `uuid4` anywhere.** `trace_id`/`span_id` are sha256-derived per the design decisions below.
- **Two git repos, two commits.** `claude-agent-loop` (this repo, branch `feat/agent-observability-layer`) owns Tasks 1–5. `~/.claude` (a separate local-only git repo, no remote — confirmed via `git rev-parse --is-inside-work-tree`) owns Task 6. Do not cross-commit.
- **`payload/MANIFEST` and `payload/fragments/settings.fragment.json` are the only way a new `payload/` file becomes live** (via `install.sh`'s `link-file` mechanism and settings deep-merge). A new file with no MANIFEST line is dead code.

## Design decisions locked in for this plan (filling gaps the source spec left as `[assumed]` or under-specified)

These resolve ambiguity the spec inherited from an external design doc I don't have access to. Each is a deliberate, documented choice — not a guess left in the code as a comment-free surprise.

1. **`root_task_id` resolution** (the anchor for `trace_id`): `session_id or agent_id or plan_id or "unknown"`, in that priority order. A session's own events, and every subagent/gate/skill event fired *during* that session, all share one `trace_id` as long as `session_id` is threaded through — which every call site in this plan does. This matches the spec's "one root span per run, ... subagent spans linked via `parent_span_id`" model (one trace per run, not one trace per subagent).
2. **`component_key` resolution** (the per-span discriminator for `span_id`): if the caller passes `component_key=...` as a kwarg (it lands in `**attrs` and is popped out before the record is written), use it verbatim. Otherwise default to `"<event>|<agent_id or ''>|<part_id or ''>"`. This keeps `span_id` a pure function of caller-visible inputs — no monotonic counters, no filesystem state in the ID math itself — which is what makes the "deterministic, stable across restarts" test in Task 1 actually true. The `tool.pre`/`tool.post` pairing key (Task 2) is the main consumer of the explicit override, so both halves of one tool call share a `span_id`.
3. **`parent_span_id`** is accepted the same way — an optional `parent_span_id=...` kwarg popped from `**attrs` into its own top-level field. Nothing in Phase 1 sets it (no subagent-linking work happens until Phase 2); the field exists in the schema now so Phase 2 doesn't need to touch `obs_emit.py` again.
4. **`tool_use_id` is confirmed present** on both `PreToolUse` and `PostToolUse` hook payloads (verified against current Claude Code hooks behavior: identical value on both sides of one tool call). The spec's `[assumed — verify against current hook payload shape]` flag is resolved: **yes**, it's there. Task 2 uses it as the primary pairing key and implements the `(session_id, tool_name, sequence)` fallback only as a defensive branch for the case it's ever absent.
5. **`PostToolUse` error signal**: `tool_response.isError` (bool) and `tool_response.error` (string) are the confirmed fields. `ok = not tool_response.get("isError")`; `error_class = tool_response.get("error")` when `ok` is `False`, else `None`. (`tool_response` shape can vary by tool, but `isError`/`error` are the common signal across tools.)
6. **Hook inventory correction**: the source spec says "13 hook scripts (11 under `payload/hooks/` + 2 local-only)". The actual count is **10 under `payload/hooks/`** (`inject-resource-loop.sh`, `harvest-metrics.sh`, `precompact-event.sh`, `auto-update.sh`, `context-budget.sh`, `usage-budget.sh`, `read-guard.sh`, `workorder-gate.sh`, `pipeline-relay.sh`, `loop-close.sh`) **+ 3 local-only** (`account-guard.sh`, `prompt-clarity-gate.sh`, `zoom-token-refresh.sh`) = **13 total**, matching the spec's final number by a different split. This plan's task counts reflect the corrected 10+3 split.

---

### Task 1: `obs_emit.py` — core event-log module

**Files:**
- Create: `payload/tools/obs_emit.py`
- Test: `payload/tools/tests/test_obs_emit.py`
- Modify: `payload/MANIFEST` — insert `link-file tools/obs_emit.py` immediately after line 234 (`link-file tools/loop_close.py`)

**Interfaces:**
- Produces: `obs_emit.emit(event, session_id=None, agent_id=None, plan_id=None, part_id=None, project=None, **attrs) -> None` — the only public entry point every later task imports and calls. Never raises. Also exposes `obs_emit.trace_id_for(root_task_id) -> str` and `obs_emit.span_id_for(root_task_id, component_key) -> str` as the pure ID functions (importable directly for the determinism tests below and for any future caller that needs an ID without a full emit).
- Consumes: nothing from other tasks (this is the foundation).

- [ ] **Step 1: Write the failing tests**

Create `payload/tools/tests/test_obs_emit.py`:

```python
"""Tests for obs_emit — the obs.v1 structured event log (Phase 1).

Written TDD-first: imports obs_emit before the module exists (RED =
ModuleNotFoundError), then drives it GREEN. Mirrors test_harvest_metrics.py's
tempfile-per-test, sys.path-insert convention.
"""
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import obs_emit  # noqa: E402


class ObsEmitFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.claude_dir = pathlib.Path(self._tmp.name)
        self._old_env = os.environ.get("CLAUDE_DIR")
        os.environ["CLAUDE_DIR"] = str(self.claude_dir)

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("CLAUDE_DIR", None)
        else:
            os.environ["CLAUDE_DIR"] = self._old_env
        self._tmp.cleanup()

    def _events_file(self):
        events_dir = self.claude_dir / "metrics" / "events"
        files = sorted(events_dir.glob("*.ndjson"))
        self.assertEqual(len(files), 1, "expected exactly one daily shard")
        return files[0]

    def _lines(self):
        return [
            json.loads(line)
            for line in self._events_file().read_text().splitlines()
            if line.strip()
        ]


class TestSchemaShape(ObsEmitFixture):
    def test_emitted_record_matches_obs_v1_shape(self):
        obs_emit.emit(
            "tool.pre", session_id="sess-1", agent_id=None, plan_id=None,
            part_id=None, project="myproj", tool_name="Read",
        )
        records = self._lines()
        self.assertEqual(len(records), 1)
        rec = records[0]
        required = {
            "schema", "ts", "event", "session_id", "agent_id", "trace_id",
            "span_id", "parent_span_id", "plan_id", "part_id", "project",
            "attrs",
        }
        self.assertEqual(set(rec.keys()), required)
        self.assertEqual(rec["schema"], "obs.v1")
        self.assertEqual(rec["event"], "tool.pre")
        self.assertEqual(rec["session_id"], "sess-1")
        self.assertEqual(rec["project"], "myproj")
        self.assertEqual(rec["attrs"], {"tool_name": "Read"})
        self.assertIsInstance(rec["trace_id"], str)
        self.assertEqual(len(rec["trace_id"]), 32)
        self.assertIsInstance(rec["span_id"], str)
        self.assertEqual(len(rec["span_id"]), 16)

    def test_emit_returns_none(self):
        self.assertIsNone(obs_emit.emit("session.start", session_id="sess-1"))


class TestDeterministicIds(ObsEmitFixture):
    def test_same_inputs_same_ids(self):
        obs_emit.emit("tool.pre", session_id="sess-1", component_key="ck-1")
        obs_emit.emit("tool.pre", session_id="sess-1", component_key="ck-1")
        first, second = self._lines()
        self.assertEqual(first["trace_id"], second["trace_id"])
        self.assertEqual(first["span_id"], second["span_id"])

    def test_different_component_key_different_span(self):
        obs_emit.emit("tool.pre", session_id="sess-1", component_key="ck-1")
        obs_emit.emit("tool.pre", session_id="sess-1", component_key="ck-2")
        first, second = self._lines()
        self.assertEqual(first["trace_id"], second["trace_id"])
        self.assertNotEqual(first["span_id"], second["span_id"])

    def test_pure_functions_stable_without_module_state(self):
        # "Stable across process restarts" is true by construction: the ID
        # functions read no counter, no file, no clock — only their args.
        t1 = obs_emit.trace_id_for("sess-1")
        s1 = obs_emit.span_id_for("sess-1", "ck-1")
        t2 = obs_emit.trace_id_for("sess-1")
        s2 = obs_emit.span_id_for("sess-1", "ck-1")
        self.assertEqual(t1, t2)
        self.assertEqual(s1, s2)

    def test_root_task_id_priority_session_over_agent_over_plan(self):
        obs_emit.emit("tool.pre", session_id="sess-1", agent_id="agent-9",
                       plan_id="wo-1", component_key="x")
        obs_emit.emit("tool.pre", session_id="sess-1", component_key="x")
        first, second = self._lines()
        self.assertEqual(first["trace_id"], second["trace_id"],
                         "session_id must win over agent_id/plan_id")


class TestAppendSafety(ObsEmitFixture):
    def test_survives_malformed_last_line(self):
        events_dir = self.claude_dir / "metrics" / "events"
        events_dir.mkdir(parents=True)
        import datetime
        day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        shard = events_dir / ("%s.ndjson" % day)
        shard.write_text("{not valid json\n")

        obs_emit.emit("tool.pre", session_id="sess-1")  # must not raise

        lines = shard.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "{not valid json")
        json.loads(lines[1])  # the new line is still valid JSON


class TestSilentFailure(ObsEmitFixture):
    def test_unwritable_events_dir_does_not_raise(self):
        metrics_dir = self.claude_dir / "metrics"
        metrics_dir.mkdir(parents=True)
        metrics_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # read+exec, no write
        try:
            result = obs_emit.emit("tool.pre", session_id="sess-1")
        finally:
            metrics_dir.chmod(stat.S_IRWXU)  # restore so tempdir cleanup works
        self.assertIsNone(result)
        self.assertFalse((metrics_dir / "events").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd payload/tools/tests && python3 -m unittest test_obs_emit -v`
Expected: `ModuleNotFoundError: No module named 'obs_emit'`

- [ ] **Step 3: Write `obs_emit.py`**

Create `payload/tools/obs_emit.py`:

```python
#!/usr/bin/env python3
"""obs_emit.py — the obs.v1 structured event log (Phase 1, stdlib only).

One function, `emit()`, appends one JSON line to
~/.claude/metrics/events/YYYY-MM-DD.ndjson per call. Copies harvest_metrics.py's
atomic-append primitive (os.open(O_WRONLY|O_APPEND|O_CREAT) + a single
os.write) onto a daily file instead of a monthly shard.

trace_id/span_id are sha256-derived, deterministic functions of caller-visible
arguments only — no uuid4, no clock, no counter — matching the framework's
existing plan_id() convention in plan_task.py. See trace_id_for()/span_id_for().

Never raises into the caller: the whole body of emit() runs inside one bare
try/except. A broken environment (unwritable dir, bad CLAUDE_DIR) degrades to
a silent no-op, never a crash.
"""
import datetime
import hashlib
import json
import os
import pathlib

# obs.v1 event enum, for reference — emit() does not enforce membership (a
# caller with a typo'd event name must never crash; better to record the typo
# than to raise).
EVENTS = (
    "session.start", "prompt.submit", "gate.decision", "tool.pre",
    "tool.post", "skill.invoked", "subagent.stop", "compaction",
    "turn.stop", "session.end", "run.end", "hook.error", "heartbeat",
)


def _events_dir():
    claude_dir = os.environ.get("CLAUDE_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    return os.path.join(claude_dir, "metrics", "events")


def _root_task_id(session_id, agent_id, plan_id):
    return session_id or agent_id or plan_id or "unknown"


def _component_key(event, agent_id, part_id, attrs):
    explicit = attrs.pop("component_key", None)
    if explicit:
        return str(explicit)
    return "%s|%s|%s" % (event, agent_id or "", part_id or "")


def trace_id_for(root_task_id):
    """Deterministic trace_id: sha256("run:" + root_task_id)[:32 hex]."""
    digest = hashlib.sha256(("run:" + str(root_task_id)).encode("utf-8"))
    return digest.hexdigest()[:32]


def span_id_for(root_task_id, component_key):
    """Deterministic span_id: sha256(root_task_id + ":" + component_key)[:16 hex]."""
    digest = hashlib.sha256(
        ("%s:%s" % (root_task_id, component_key)).encode("utf-8"))
    return digest.hexdigest()[:16]


def _append_record(events_dir, day, record):
    pathlib.Path(events_dir).mkdir(parents=True, exist_ok=True)
    shard = os.path.join(events_dir, "%s.ndjson" % day)
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    data = line.encode("utf-8")
    # Single os.write(2) to an O_APPEND fd — see harvest_metrics.py's
    # _append_record for why this never tears a concurrent writer's line.
    fd = os.open(shard, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def emit(event, session_id=None, agent_id=None, plan_id=None, part_id=None,
          project=None, **attrs):
    """Append one obs.v1 record. Never raises; always returns None."""
    try:
        attrs = dict(attrs)
        parent_span_id = attrs.pop("parent_span_id", None)
        root_task_id = _root_task_id(session_id, agent_id, plan_id)
        component_key = _component_key(event, agent_id, part_id, attrs)
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        record = {
            "schema": "obs.v1",
            "ts": ts,
            "event": event,
            "session_id": session_id,
            "agent_id": agent_id,
            "trace_id": trace_id_for(root_task_id),
            "span_id": span_id_for(root_task_id, component_key),
            "parent_span_id": parent_span_id,
            "plan_id": plan_id,
            "part_id": part_id,
            "project": project,
            "attrs": attrs,
        }
        _append_record(_events_dir(), ts[:10], record)
    except Exception:
        pass
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd payload/tools/tests && python3 -m unittest test_obs_emit -v`
Expected: all tests `OK`

- [ ] **Step 5: Wire into MANIFEST**

Edit `payload/MANIFEST`, insert this line immediately after line 234 (`link-file tools/loop_close.py`):
```
link-file tools/obs_emit.py
```

- [ ] **Step 6: Run the full existing test suite to confirm no regression**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -20`
Expected: same pass count as before this task, plus the new `test_obs_emit` suite passing.

- [ ] **Step 7: Commit**

```bash
git add payload/tools/obs_emit.py payload/tools/tests/test_obs_emit.py payload/MANIFEST
git commit -m "$(cat <<'EOF'
feat(observability): add obs_emit.py — obs.v1 structured event log

(1) Task & Change
Implements Phase 1's core primitive from the agent-observability-layer spec:
a stdlib-only emit() that appends deterministic-ID (sha256, no uuid4) JSON
lines to ~/.claude/metrics/events/YYYY-MM-DD.ndjson. Silent-fail by design —
never raises into a hook caller.

(2) Tests created / modified
- payload/tools/tests/test_obs_emit.py: schema shape, deterministic
  trace_id/span_id, malformed-last-line append survival, unwritable-dir
  silent failure.

(3) Test results — evidence
python3 -m unittest test_obs_emit -v
Ran 8 tests in 0.0Xs — OK
EOF
)"
```

---

### Task 2: `obs-events.sh` — `tool.pre` / `tool.post` / `turn.stop` hook

**Files:**
- Create: `payload/hooks/obs-events.sh`
- Modify: `payload/fragments/settings.fragment.json` — add `PreToolUse` (no matcher), `PostToolUse` (no matcher), and a new top-level `Stop` hook event
- Modify: `payload/MANIFEST` — insert `link-file hooks/obs-events.sh` immediately after line 213 (`link-file hooks/loop-close.sh`)
- Test: `payload/tools/tests/test_obs_events.sh`

**Interfaces:**
- Consumes: `obs_emit.emit(event, session_id=None, **attrs)` from Task 1, imported via `sys.path.insert(0, TOOLS_DIR)`.
- Produces: nothing further tasks call directly (this is a hook binding, not a library).

- [ ] **Step 1: Write the failing shell test**

Create `payload/tools/tests/test_obs_events.sh`:

```bash
#!/bin/bash
# test_obs_events.sh — PreToolUse/PostToolUse/Stop structured event hook.
# Modeled on test_workorder_gate.sh. macOS bash-3.2 portable.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$(cd "$HERE/../../hooks" && pwd)/obs-events.sh"
TOOLS="$(cd "$HERE/.." && pwd)"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

events_file() {
  find "$TMP/claude/metrics/events" -name '*.ndjson' 2>/dev/null | head -1
}

last_records() {
  f="$(events_file)"
  [ -n "$f" ] && cat "$f" || true
}

run() {
  # run <json-payload>
  printf '%s' "$1" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" bash "$HOOK"
}

# 1. PreToolUse with tool_use_id -> tool.pre record, exits 0.
payload='{"hook_event_name":"PreToolUse","session_id":"s1","tool_name":"Read","tool_use_id":"tu-1","tool_input":{"file_path":"/x"}}'
run "$payload"; rc=$?
[ $rc -eq 0 ] && pass "1 PreToolUse: exit 0" || die "1 exit $rc"
recs="$(last_records)"
echo "$recs" | grep -q '"event":"tool.pre"' && pass "1 tool.pre recorded" || die "1 no tool.pre (got: $recs)"
echo "$recs" | grep -q '"tool_name":"Read"' && pass "1 tool_name attr present" || die "1 missing tool_name"

# 2. Matching PostToolUse (same tool_use_id) -> tool.post with duration_ms and ok=true.
payload='{"hook_event_name":"PostToolUse","session_id":"s1","tool_name":"Read","tool_use_id":"tu-1","tool_input":{"file_path":"/x"},"tool_response":{"isError":false}}'
run "$payload" >/dev/null; rc=$?
[ $rc -eq 0 ] && pass "2 PostToolUse: exit 0" || die "2 exit $rc"
recs="$(last_records)"
echo "$recs" | grep -q '"event":"tool.post"' && pass "2 tool.post recorded" || die "2 no tool.post"
echo "$recs" | grep -q '"ok":true' && pass "2 ok:true derived" || die "2 ok not true (got: $recs)"
echo "$recs" | grep -q '"duration_ms":' && pass "2 duration_ms present" || die "2 no duration_ms"

# 3. PostToolUse with isError:true -> ok:false, error_class captured.
payload3pre='{"hook_event_name":"PreToolUse","session_id":"s2","tool_name":"Bash","tool_use_id":"tu-2","tool_input":{"command":"false"}}'
run "$payload3pre" >/dev/null
payload3post='{"hook_event_name":"PostToolUse","session_id":"s2","tool_name":"Bash","tool_use_id":"tu-2","tool_input":{"command":"false"},"tool_response":{"isError":true,"error":"exit 1"}}'
run "$payload3post" >/dev/null
recs="$(last_records)"
echo "$recs" | grep -q '"ok":false' && pass "3 ok:false on error" || die "3 ok not false"
echo "$recs" | grep -q '"error_class":"exit 1"' && pass "3 error_class captured" || die "3 error_class missing (got: $recs)"

# 4. Stop -> turn.stop record.
payload4='{"hook_event_name":"Stop","session_id":"s3"}'
run "$payload4" >/dev/null; rc=$?
[ $rc -eq 0 ] && pass "4 Stop: exit 0" || die "4 exit $rc"
recs="$(last_records)"
echo "$recs" | grep -q '"event":"turn.stop"' && pass "4 turn.stop recorded" || die "4 no turn.stop"

# 5. Fallback pairing when tool_use_id is absent: pre then post for same
#    (session, tool_name) still pair via the sequence-counter fallback.
payload5pre='{"hook_event_name":"PreToolUse","session_id":"s4","tool_name":"Grep","tool_input":{}}'
run "$payload5pre" >/dev/null
payload5post='{"hook_event_name":"PostToolUse","session_id":"s4","tool_name":"Grep","tool_input":{},"tool_response":{"isError":false}}'
run "$payload5post" >/dev/null
recs="$(last_records)"
pre_span="$(echo "$recs" | grep '"event":"tool.pre".*"tool_name":"Grep"' | python3 -c "import json,sys; [print(json.loads(l)['span_id']) for l in sys.stdin if l.strip()]" 2>/dev/null | tail -1)"
post_span="$(echo "$recs" | grep '"event":"tool.post".*"tool_name":"Grep"' | python3 -c "import json,sys; [print(json.loads(l)['span_id']) for l in sys.stdin if l.strip()]" 2>/dev/null | tail -1)"
if [ -n "$pre_span" ] && [ "$pre_span" = "$post_span" ]; then
  pass "5 fallback pairing: pre/post share span_id"
else
  die "5 fallback pairing failed (pre=$pre_span post=$post_span)"
fi

# 6. Malformed stdin JSON -> silent, still exits 0.
out="$(printf '%s' '{not json' | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "6 malformed input: exit 0" || die "6 exit $rc"

# 7. OBS_EVENTS_DISABLE=1 -> no record written, exit 0.
before="$(last_records | wc -l)"
payload7='{"hook_event_name":"Stop","session_id":"s5"}'
printf '%s' "$payload7" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" OBS_EVENTS_DISABLE=1 bash "$HOOK"; rc=$?
after="$(last_records | wc -l)"
[ $rc -eq 0 ] && pass "7 kill switch: exit 0" || die "7 exit $rc"
[ "$before" -eq "$after" ] && pass "7 kill switch: no new record" || die "7 record written despite kill switch"

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_obs_events.sh"
  exit 0
else
  echo "SOME FAILED - test_obs_events.sh"
  exit 1
fi
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash payload/tools/tests/test_obs_events.sh`
Expected: fails at case 1 — `bash: .../hooks/obs-events.sh: No such file or directory` (or `cd` failure resolving `HOOK`), since the hook file doesn't exist yet.

- [ ] **Step 3: Write `obs-events.sh`**

Create `payload/hooks/obs-events.sh`:

```bash
#!/bin/bash
# obs-events.sh — PreToolUse/PostToolUse/Stop hook: emits obs.v1 tool.pre,
# tool.post, and turn.stop records via obs_emit.py. Same shape as
# harvest-metrics.sh: bash wrapper -> python heredoc, 10s SIGALRM guard,
# always exits 0. Kill switch: OBS_EVENTS_DISABLE=1.
#
# tool.pre/tool.post pairing: prefers tool_use_id (confirmed present on both
# PreToolUse and PostToolUse payloads). Falls back to a per-session
# (tool_name, sequence) counter, stored in
# $CLAUDE_DIR/metrics/state/obs-events/<session>.json, when tool_use_id is
# ever absent.
set -u

[ "${OBS_EVENTS_DISABLE:-0}" = "1" ] && exit 0

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
TOOLS_DIR="${TOOLS_DIR:-$CLAUDE_DIR/tools}"
INPUT="$(cat 2>/dev/null || true)"

HOOK_JSON="$INPUT" CLAUDE_DIR="$CLAUDE_DIR" TOOLS_DIR="$TOOLS_DIR" \
  python3 >/dev/null <<'PY' || true
import datetime
import hashlib
import json
import os
import signal
import sys


def _bail(signum, frame):
    os._exit(0)


try:
    signal.signal(signal.SIGALRM, _bail)
    signal.alarm(10)
except Exception:
    pass

sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))

try:
    raw = os.environ.get("HOOK_JSON", "")
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}

try:
    import obs_emit
except Exception:
    os._exit(0)

event_name = data.get("hook_event_name") or ""
session_id = data.get("session_id") or "unknown"
tool_name = data.get("tool_name") or ""
_tool_input = data.get("tool_input")
tool_input = _tool_input if isinstance(_tool_input, dict) else {}
tool_use_id = data.get("tool_use_id")


def _args_hash(obj):
    try:
        blob = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    except Exception:
        blob = str(obj)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _safe(sid):
    return "".join(c for c in str(sid) if c.isalnum() or c in "-_")[:80] or "unknown"


def _state_path():
    state_dir = os.path.join(
        os.environ.get("CLAUDE_DIR", ""), "metrics", "state", "obs-events")
    try:
        os.makedirs(state_dir, exist_ok=True)
    except Exception:
        return None
    return os.path.join(state_dir, "%s.json" % _safe(session_id))


def _load_state(path):
    default = {"seq": {}, "pending": {}}
    if not path:
        return default
    try:
        with open(path) as fh:
            st = json.load(fh)
        if not isinstance(st, dict):
            return default
        st.setdefault("seq", {})
        st.setdefault("pending", {})
        return st
    except Exception:
        return default


def _save_state(path, state):
    if not path:
        return
    try:
        tmp = path + ".tmp.%d" % os.getpid()
        with open(tmp, "w") as fh:
            json.dump(state, fh)
        os.replace(tmp, path)
    except Exception:
        pass


try:
    if event_name == "PreToolUse":
        state_path = _state_path()
        state = _load_state(state_path)
        if tool_use_id:
            pairing_key = str(tool_use_id)
        else:
            seq = int(state["seq"].get(tool_name, 0)) + 1
            state["seq"][tool_name] = seq
            pairing_key = "%s:%s:%d" % (session_id, tool_name, seq)
        state["pending"][pairing_key] = datetime.datetime.now(
            datetime.timezone.utc).isoformat()
        _save_state(state_path, state)
        obs_emit.emit(
            "tool.pre", session_id=session_id, component_key=pairing_key,
            tool_name=tool_name, args_hash=_args_hash(tool_input),
        )
    elif event_name == "PostToolUse":
        state_path = _state_path()
        state = _load_state(state_path)
        if tool_use_id:
            pairing_key = str(tool_use_id)
        else:
            seq = int(state["seq"].get(tool_name, 0))
            pairing_key = "%s:%s:%d" % (session_id, tool_name, seq)
        pre_ts = state["pending"].pop(pairing_key, None)
        _save_state(state_path, state)
        duration_ms = None
        if pre_ts:
            try:
                started = datetime.datetime.fromisoformat(pre_ts)
                now = datetime.datetime.now(datetime.timezone.utc)
                duration_ms = int((now - started).total_seconds() * 1000)
            except Exception:
                duration_ms = None
        _tool_response = data.get("tool_response")
        tool_response = _tool_response if isinstance(_tool_response, dict) else {}
        ok = not bool(tool_response.get("isError"))
        error_class = None if ok else tool_response.get("error")
        obs_emit.emit(
            "tool.post", session_id=session_id, component_key=pairing_key,
            tool_name=tool_name, tool_use_id=tool_use_id, ok=ok,
            error_class=error_class, duration_ms=duration_ms,
            args_hash=_args_hash(tool_input),
        )
    elif event_name == "Stop":
        obs_emit.emit("turn.stop", session_id=session_id)
except Exception:
    pass

os._exit(0)
PY

exit 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash payload/tools/tests/test_obs_events.sh`
Expected: `ALL PASS - test_obs_events.sh`, exit 0.

- [ ] **Step 5: Wire hook bindings into `settings.fragment.json`**

Edit `payload/fragments/settings.fragment.json`. Add a second entry to the existing `PreToolUse` array (after the `"matcher": "Read"` group, so the array becomes):

```json
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/hooks/read-guard.sh"
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/hooks/obs-events.sh"
          }
        ]
      }
    ]
```

Add a third entry to the existing `PostToolUse` array (after the `usage-budget.sh` group, before the `Skill`-matcher `pipeline-relay.sh` group):

```json
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/hooks/obs-events.sh"
          }
        ]
      },
```

Add a new top-level `Stop` key (place it after the `SessionEnd` block, before `PreCompact`):

```json
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/hooks/obs-events.sh"
          }
        ]
      }
    ],
```

- [ ] **Step 6: Wire into MANIFEST**

Edit `payload/MANIFEST`, insert this line immediately after line 213 (`link-file hooks/loop-close.sh`):
```
link-file hooks/obs-events.sh
```

- [ ] **Step 7: Validate the fragment is still valid JSON and install cleanly**

Run: `python3 -c "import json; json.load(open('payload/fragments/settings.fragment.json'))" && echo VALID_JSON`
Expected: `VALID_JSON`

Run: `bash install.sh 2>&1 | tail -30`
Expected: exits 0; output confirms `obs-events.sh` linked and the settings merge applied without error.

Run: `launchctl list >/dev/null 2>&1; python3 -c "import json; s=json.load(open(__import__('os').path.expanduser('~/.claude/settings.json'))); assert any('obs-events.sh' in json.dumps(h) for h in s['hooks']['Stop']); assert any('obs-events.sh' in json.dumps(g) for g in s['hooks']['PreToolUse']); assert any('obs-events.sh' in json.dumps(g) for g in s['hooks']['PostToolUse']); print('MERGED_OK')"`
Expected: `MERGED_OK`

- [ ] **Step 8: Commit**

```bash
git add payload/hooks/obs-events.sh payload/tools/tests/test_obs_events.sh \
        payload/fragments/settings.fragment.json payload/MANIFEST
git commit -m "$(cat <<'EOF'
feat(observability): add obs-events.sh — tool.pre/tool.post/turn.stop hook

(1) Task & Change
New PreToolUse/PostToolUse (no matcher, every tool)/Stop (new top-level hook
event for this framework) binding emitting obs.v1 tool.pre/tool.post/
turn.stop records. Pairs tool.pre/tool.post via the confirmed-present
tool_use_id, falling back to a per-session (tool_name, sequence) counter.

(2) Tests created / modified
- payload/tools/tests/test_obs_events.sh: tool.pre/tool.post pairing (both
  tool_use_id and fallback paths), ok/error_class derivation, turn.stop,
  malformed-input silence, kill-switch.

(3) Test results — evidence
bash payload/tools/tests/test_obs_events.sh
ALL PASS - test_obs_events.sh
EOF
)"
```

---

### Task 3: `gate.decision` instrumentation — `workorder-gate.sh` and `read-guard.sh`

**Files:**
- Modify: `payload/hooks/workorder-gate.sh:49-58,134` (existing `sys.path.insert`/`bail()`/inject site)
- Modify: `payload/hooks/read-guard.sh:20-24,87-101` (bash env passthrough; `allow()`/`deny()`)
- Test: `payload/tools/tests/test_obs_events_gates.sh`

**Interfaces:**
- Consumes: `obs_emit.emit()` from Task 1.

- [ ] **Step 1: Write the failing shell test**

Create `payload/tools/tests/test_obs_events_gates.sh`:

```bash
#!/bin/bash
# test_obs_events_gates.sh — gate.decision emission from workorder-gate.sh
# and read-guard.sh. macOS bash-3.2 portable.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOKS_DIR="$(cd "$HERE/../../hooks" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

events_file() { find "$TMP/claude/metrics/events" -name '*.ndjson' 2>/dev/null | head -1; }
last_records() { f="$(events_file)"; [ -n "$f" ] && cat "$f" || true; }

# --- workorder-gate.sh: silent path -> gate.decision action:silent ----------
payload="$(python3 -c "import json; print(json.dumps({'session_id':'g1','prompt':'what does this error mean'}))")"
printf '%s' "$payload" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" METRICS_DIR="$TMP/claude/metrics" bash "$HOOKS_DIR/workorder-gate.sh" >/dev/null
recs="$(last_records)"
echo "$recs" | grep -q '"gate":"workorder".*"action":"silent"' && pass "workorder silent path recorded" || die "workorder silent missing (got: $recs)"

# --- workorder-gate.sh: inject path -> gate.decision action:inject with score
payload="$(python3 -c "import json; print(json.dumps({'session_id':'g2','prompt':'build a brand new coach dashboard with rankings and drilldowns'}))")"
printf '%s' "$payload" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" METRICS_DIR="$TMP/claude/metrics" bash "$HOOKS_DIR/workorder-gate.sh" >/dev/null
recs="$(last_records)"
echo "$recs" | grep -q '"gate":"workorder".*"action":"inject"' && pass "workorder inject path recorded" || die "workorder inject missing (got: $recs)"

# --- read-guard.sh: silent allow -> gate.decision action:silent -------------
payload="$(python3 -c "import json; print(json.dumps({'session_id':'g3','tool_input':{'file_path':'/tmp/small.txt'}}))")"
printf '%s' "$payload" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" bash "$HOOKS_DIR/read-guard.sh" >/dev/null
recs="$(last_records)"
echo "$recs" | grep -q '"gate":"read-guard".*"action":"silent"' && pass "read-guard silent path recorded" || die "read-guard silent missing (got: $recs)"

# --- read-guard.sh: deny -> gate.decision action:deny -----------------------
payload="$(python3 -c "import json; print(json.dumps({'session_id':'g4','tool_input':{'file_path':'/x/package-lock.json'}}))")"
printf '%s' "$payload" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" bash "$HOOKS_DIR/read-guard.sh" >/dev/null
recs="$(last_records)"
echo "$recs" | grep -q '"gate":"read-guard".*"action":"deny"' && pass "read-guard deny path recorded" || die "read-guard deny missing (got: $recs)"

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_obs_events_gates.sh"; exit 0
else
  echo "SOME FAILED - test_obs_events_gates.sh"; exit 1
fi
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash payload/tools/tests/test_obs_events_gates.sh`
Expected: all 4 cases FAIL (no `gate.decision` records exist yet).

- [ ] **Step 3: Instrument `workorder-gate.sh`**

`sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))` already exists at line 49. Immediately after it, add:

```python
try:
    import obs_emit
except Exception:
    obs_emit = None
```

Replace the existing `bail()` (lines 52–58):
```python
def bail():
    """Silence is a valid answer. The hook never blocks a prompt."""
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(0)
```
with:
```python
def bail(action="silent", score=None):
    """Silence is a valid answer. The hook never blocks a prompt."""
    if obs_emit is not None:
        try:
            obs_emit.emit("gate.decision", session_id=session_id,
                           gate="workorder", action=action, score=score)
        except Exception:
            pass
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(0)
```

(`session_id` is assigned at line 70, before every existing `bail()` call site at lines 74/79/85/88/106 — safe to reference as a module global.) Every existing bare `bail()` call keeps working unchanged (both new params default).

Immediately before the existing inject write (originally line 134, `sys.stdout.write(json.dumps({...}))`), add:
```python
if obs_emit is not None:
    try:
        obs_emit.emit("gate.decision", session_id=session_id,
                       gate="workorder", action="inject", score=score)
    except Exception:
        pass
```

- [ ] **Step 4: Instrument `read-guard.sh`**

Change the bash wrapper (currently lines 20–24):
```bash
set -u

INPUT="$(cat 2>/dev/null || true)"

READ_GUARD_INPUT="$INPUT" python3 <<'PY' || true
```
to:
```bash
set -u

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
TOOLS_DIR="${TOOLS_DIR:-$CLAUDE_DIR/tools}"
INPUT="$(cat 2>/dev/null || true)"

READ_GUARD_INPUT="$INPUT" TOOLS_DIR="$TOOLS_DIR" python3 <<'PY' || true
```

Immediately after the existing defensive-parse block (right after `payload = {}` handling, before `LINE_CAP = 1000`), add:
```python
session_id = payload.get("session_id") or "unknown"
sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))
try:
    import obs_emit
except Exception:
    obs_emit = None
```

Replace `allow()`/`deny()` (currently):
```python
def allow(context=None):
    hook = {"hookEventName": "PreToolUse", "permissionDecision": "allow"}
    if context:
        hook["additionalContext"] = context
    return {"hookSpecificOutput": hook}


def deny(reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
```
with:
```python
def allow(context=None):
    if obs_emit is not None:
        try:
            obs_emit.emit("gate.decision", session_id=session_id,
                           gate="read-guard", action="inject" if context else "silent")
        except Exception:
            pass
    hook = {"hookEventName": "PreToolUse", "permissionDecision": "allow"}
    if context:
        hook["additionalContext"] = context
    return {"hookSpecificOutput": hook}


def deny(reason):
    if obs_emit is not None:
        try:
            obs_emit.emit("gate.decision", session_id=session_id,
                           gate="read-guard", action="deny")
        except Exception:
            pass
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `bash payload/tools/tests/test_obs_events_gates.sh`
Expected: `ALL PASS - test_obs_events_gates.sh`

- [ ] **Step 6: Run the full existing hook test suite to confirm no regression**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -30`
Expected: `test_workorder_gate.sh` and `test_read_guard.sh` (existing suites) still pass unchanged — their assertions are about `hookSpecificOutput` shape, which this task does not touch.

- [ ] **Step 7: Commit**

```bash
git add payload/hooks/workorder-gate.sh payload/hooks/read-guard.sh \
        payload/tools/tests/test_obs_events_gates.sh
git commit -m "$(cat <<'EOF'
feat(observability): emit gate.decision from workorder-gate.sh, read-guard.sh

(1) Task & Change
One obs_emit.py call added at each hook's existing choke-point function
(bail()/allow()/deny()) so every gate outcome — silent, inject, deny — lands
in the obs.v1 event log. No change to either hook's existing decision output.

(2) Tests created / modified
- payload/tools/tests/test_obs_events_gates.sh: silent/inject (workorder),
  silent/deny (read-guard).

(3) Test results — evidence
bash payload/tools/tests/test_obs_events_gates.sh
ALL PASS - test_obs_events_gates.sh
Full suite: bash payload/tools/tests/run_all.sh — no regressions.
EOF
)"
```

---

### Task 4: `skill.invoked` instrumentation — `pipeline-relay.sh`

**Files:**
- Modify: `payload/hooks/pipeline-relay.sh:36-45,75` (add `sys.path`/import near top; add emit call after `leaf` is computed)
- Test: `payload/tools/tests/test_pipeline_relay_skill_invoked.sh`

**Interfaces:**
- Consumes: `obs_emit.emit()` from Task 1.

- [ ] **Step 1: Write the failing shell test**

Create `payload/tools/tests/test_pipeline_relay_skill_invoked.sh`:

```bash
#!/bin/bash
# test_pipeline_relay_skill_invoked.sh — skill.invoked fires for every Skill
# call, not only the two known RELAYS leaves. macOS bash-3.2 portable.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$(cd "$HERE/../../hooks" && pwd)/pipeline-relay.sh"
TOOLS="$(cd "$HERE/.." && pwd)"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

events_file() { find "$TMP/claude/metrics/events" -name '*.ndjson' 2>/dev/null | head -1; }
last_records() { f="$(events_file)"; [ -n "$f" ] && cat "$f" || true; }

run() {
  printf '%s' "$1" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" METRICS_DIR="$TMP/claude/metrics" bash "$HOOK"
}

# 1. A skill with NO relay directive (e.g. "resource-loop") still emits skill.invoked.
payload="$(python3 -c "import json; print(json.dumps({'session_id':'sk1','tool_name':'Skill','tool_input':{'skill':'resource-loop'}}))")"
run "$payload" >/dev/null
recs="$(last_records)"
echo "$recs" | grep -q '"event":"skill.invoked"' && pass "1 skill.invoked recorded for unmapped skill" || die "1 missing (got: $recs)"
echo "$recs" | grep -q '"skill_name":"resource-loop"' && pass "1 skill_name attr correct" || die "1 wrong skill_name"

# 2. A plugin-qualified skill name ("superpowers:brainstorming") records the leaf.
payload="$(python3 -c "import json; print(json.dumps({'session_id':'sk2','tool_name':'Skill','tool_input':{'skill':'superpowers:brainstorming'}}))")"
run "$payload" >/dev/null
recs="$(last_records)"
echo "$recs" | grep -q '"skill_name":"brainstorming"' && pass "2 leaf extracted from plugin-qualified name" || die "2 wrong skill_name (got: $recs)"

# 3. Non-Skill tool call -> no skill.invoked record.
before="$(last_records | grep -c '"event":"skill.invoked"' || true)"
payload="$(python3 -c "import json; print(json.dumps({'session_id':'sk3','tool_name':'Read','tool_input':{'file_path':'/x'}}))")"
run "$payload" >/dev/null
after="$(last_records | grep -c '"event":"skill.invoked"' || true)"
[ "$before" -eq "$after" ] && pass "3 non-Skill tool: no new skill.invoked" || die "3 unexpected skill.invoked for Read"

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_pipeline_relay_skill_invoked.sh"; exit 0
else
  echo "SOME FAILED - test_pipeline_relay_skill_invoked.sh"; exit 1
fi
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash payload/tools/tests/test_pipeline_relay_skill_invoked.sh`
Expected: cases 1 and 2 FAIL (no `skill.invoked` records exist yet).

- [ ] **Step 3: Instrument `pipeline-relay.sh`**

Find the existing top-of-heredoc block (around lines 36–45, where `bail()` and the HOOK_JSON parse live — same shape as `workorder-gate.sh`). Add, right after the existing `sys.path.insert`-equivalent setup (this file currently has no `sys.path.insert` — add one) and before the `try: raw = os.environ.get("HOOK_JSON"...` parse block:

```python
sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))
try:
    import obs_emit
except Exception:
    obs_emit = None
```

Immediately after the existing `leaf = skill.rsplit(":", 1)[-1]` / `session_id = data.get("session_id") or "unknown"` lines (currently lines 75–76), add:

```python
if obs_emit is not None:
    try:
        obs_emit.emit("skill.invoked", session_id=session_id, skill_name=leaf)
    except Exception:
        pass
```

This sits **before** the `RELAYS.get(leaf)` / `if not directive: bail()` check (currently lines 100–102), so it fires for every Skill call, not only `brainstorming`/`writing-plans`.

Also thread `TOOLS_DIR`/`CLAUDE_DIR` into the bash wrapper's `python3 <<'PY'` invocation the same way `workorder-gate.sh` already does (add `CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"` and `TOOLS_DIR="${TOOLS_DIR:-$CLAUDE_DIR/tools}"` near the top of the bash section, and add `TOOLS_DIR="$TOOLS_DIR"` to the env-var prefix list on the `python3 <<'PY'` line).

- [ ] **Step 4: Run test to verify it passes**

Run: `bash payload/tools/tests/test_pipeline_relay_skill_invoked.sh`
Expected: `ALL PASS - test_pipeline_relay_skill_invoked.sh`

- [ ] **Step 5: Run the full existing test suite to confirm no regression**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -30`
Expected: existing `pipeline-relay` tests (relay directives for `brainstorming`/`writing-plans`) still pass unchanged.

- [ ] **Step 6: Commit**

```bash
git add payload/hooks/pipeline-relay.sh payload/tools/tests/test_pipeline_relay_skill_invoked.sh
git commit -m "$(cat <<'EOF'
feat(observability): emit skill.invoked from pipeline-relay.sh

(1) Task & Change
Adds a skill.invoked obs_emit.py call right after pipeline-relay.sh's
existing leaf-name extraction, firing for every Skill call — not only the
two skills with a RELAYS directive. This is the highest-leverage record in
the observability build: tool-written, per-resource attribution independent
of ANNOUNCE-line prose compliance.

(2) Tests created / modified
- payload/tools/tests/test_pipeline_relay_skill_invoked.sh: unmapped skill,
  plugin-qualified leaf extraction, non-Skill tool produces no record.

(3) Test results — evidence
bash payload/tools/tests/test_pipeline_relay_skill_invoked.sh
ALL PASS - test_pipeline_relay_skill_invoked.sh
EOF
)"
```

---

### Task 5: `hook.error` trap wrapper — all 10 `payload/hooks/*.sh` scripts

**Files:**
- Modify: `payload/hooks/inject-resource-loop.sh`, `harvest-metrics.sh`, `precompact-event.sh`, `auto-update.sh`, `context-budget.sh`, `usage-budget.sh`, `read-guard.sh`, `workorder-gate.sh`, `pipeline-relay.sh`, `loop-close.sh` — each gets the identical block below, right after its `set -u` line, with `HOOK_NAME` substituted.
- Test: `payload/tools/tests/test_hook_error_trap.sh`

**Interfaces:**
- Consumes: `obs_emit.emit()` from Task 1, invoked via a standalone `python3 -c` (not the in-heredoc import, since the trap must fire even if the heredoc itself is where things went wrong).

- [ ] **Step 1: Write the failing shell test**

Create `payload/tools/tests/test_hook_error_trap.sh`:

```bash
#!/bin/bash
# test_hook_error_trap.sh — the hook.error trap block fires on an unexpected
# non-zero exit inside the bash wrapper. Verified against one representative
# hook (harvest-metrics.sh) plus a static grep confirming all 10 files carry
# the block. macOS bash-3.2 portable.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
HOOKS_DIR="$(cd "$HERE/../../hooks" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

EXPECTED_HOOKS="inject-resource-loop.sh harvest-metrics.sh precompact-event.sh auto-update.sh context-budget.sh usage-budget.sh read-guard.sh workorder-gate.sh pipeline-relay.sh loop-close.sh"

for h in $EXPECTED_HOOKS; do
  if grep -q '_obs_hook_error' "$HOOKS_DIR/$h" && grep -q "trap _obs_hook_error ERR" "$HOOKS_DIR/$h"; then
    pass "$h: trap block present"
  else
    die "$h: trap block missing"
  fi
done

# Functional check: force an ERR trap trip in a throwaway copy of
# harvest-metrics.sh's wrapper shape and confirm obs_emit records hook.error.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/fake-hook.sh" <<'EOS'
#!/bin/bash
set -u
_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="fake-hook.sh" \
    python3 -c '
import os, sys
sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))
try:
    import obs_emit
    obs_emit.emit("hook.error", session_id=os.environ.get("SESSION_ID"),
                  hook=os.environ.get("HOOK_NAME"), stage="trap")
except Exception:
    pass
' >/dev/null 2>&1 || true
}
trap _obs_hook_error ERR
false  # unconditional non-zero command -> trips ERR trap
exit 0
EOS
chmod +x "$TMP/fake-hook.sh"

env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" SESSION_ID="herr1" bash "$TMP/fake-hook.sh" >/dev/null 2>&1

events_file="$(find "$TMP/claude/metrics/events" -name '*.ndjson' 2>/dev/null | head -1)"
if [ -n "$events_file" ] && grep -q '"event":"hook.error"' "$events_file" && grep -q '"hook":"fake-hook.sh"' "$events_file"; then
  pass "functional: ERR trap emits hook.error"
else
  die "functional: no hook.error record found"
fi

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_hook_error_trap.sh"; exit 0
else
  echo "SOME FAILED - test_hook_error_trap.sh"; exit 1
fi
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash payload/tools/tests/test_hook_error_trap.sh`
Expected: all 10 static-presence checks FAIL.

- [ ] **Step 3: Add the trap block to all 10 files**

For each file below, insert this exact block immediately after its `set -u` line, substituting `HOOK_NAME` per the table:

```bash
_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="__HOOK_NAME__" \
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
```

| File | `__HOOK_NAME__` |
|---|---|
| `payload/hooks/inject-resource-loop.sh` | `inject-resource-loop.sh` |
| `payload/hooks/harvest-metrics.sh` | `harvest-metrics.sh` |
| `payload/hooks/precompact-event.sh` | `precompact-event.sh` |
| `payload/hooks/auto-update.sh` | `auto-update.sh` |
| `payload/hooks/context-budget.sh` | `context-budget.sh` |
| `payload/hooks/usage-budget.sh` | `usage-budget.sh` |
| `payload/hooks/read-guard.sh` | `read-guard.sh` |
| `payload/hooks/workorder-gate.sh` | `workorder-gate.sh` |
| `payload/hooks/pipeline-relay.sh` | `pipeline-relay.sh` |
| `payload/hooks/loop-close.sh` | `loop-close.sh` |

Exit behavior is unchanged in every case: this only adds a breadcrumb when the bash wrapper itself trips a non-zero exit status somewhere not already guarded by `||`/`&&`/an `if` test — the heredoc-internal `|| true` guards remain exactly as before, so this trap is a defense-in-depth addition, not a behavior change.

- [ ] **Step 4: Run test to verify it passes**

Run: `bash payload/tools/tests/test_hook_error_trap.sh`
Expected: `ALL PASS - test_hook_error_trap.sh`

- [ ] **Step 5: Run the full existing test suite to confirm no regression**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -40`
Expected: every existing suite still passes — the trap block never fires under normal operation (all 10 scripts' existing logic is already `set -u` + defensive `||`/`try/except` throughout, so `false`/non-zero commands don't occur on the happy or the documented failure paths).

- [ ] **Step 6: Commit**

```bash
git add payload/hooks/inject-resource-loop.sh payload/hooks/harvest-metrics.sh \
        payload/hooks/precompact-event.sh payload/hooks/auto-update.sh \
        payload/hooks/context-budget.sh payload/hooks/usage-budget.sh \
        payload/hooks/read-guard.sh payload/hooks/workorder-gate.sh \
        payload/hooks/pipeline-relay.sh payload/hooks/loop-close.sh \
        payload/tools/tests/test_hook_error_trap.sh
git commit -m "$(cat <<'EOF'
feat(observability): add hook.error trap breadcrumb to all 10 payload hooks

(1) Task & Change
Identical trap _obs_hook_error ERR block added after set -u in every
payload/hooks/*.sh script. Fires obs_emit.py's hook.error event on any
bash-level non-zero exit not already guarded by a conditional — a
breadcrumb for a failure that would otherwise degrade to total silence,
per this framework's fail-open design. No exit-code or output change on
any existing path.

(2) Tests created / modified
- payload/tools/tests/test_hook_error_trap.sh: static presence check across
  all 10 files, functional ERR-trap-fires-emit check against a throwaway
  fixture script.

(3) Test results — evidence
bash payload/tools/tests/test_hook_error_trap.sh
ALL PASS - test_hook_error_trap.sh
Full suite: bash payload/tools/tests/run_all.sh — no regressions.
EOF
)"
```

- [ ] **Step 7: Push**

```bash
git push origin feat/agent-observability-layer
```

---

### Task 6: Local-only lane — `account-guard.sh`, `prompt-clarity-gate.sh`, `zoom-token-refresh.sh`

**Repo:** `~/.claude` (separate local git repo, no remote — confirmed via `git rev-parse --is-inside-work-tree`). This task's commit lands there, **not** in `claude-agent-loop`. These three files are outside `payload/` by the framework's own local-lane convention (never touched by `install.sh`).

**Prerequisite:** Tasks 1, 2, and 5 must already be committed in `claude-agent-loop` and `bash install.sh` run at least once, so `~/.claude/tools/obs_emit.py` exists as a live symlink before this task's manual `python3 -c` calls can import it.

**Files:**
- Modify: `~/.claude/hooks/account-guard.sh` (full file — see Task spec below; add `SESSION_ID` capture, `emit_gate()` helper, `gate.decision` calls, and the `hook.error` trap)
- Modify: `~/.claude/hooks/prompt-clarity-gate.sh:19-67` (add `TOOLS_DIR`, import, restructure `bail()`, add trap)
- Modify: `~/.claude/hooks/zoom-token-refresh.sh:13` (add trap only — this hook has no gate decision to record, only a hook.error breadcrumb)
- Test: `~/.claude/tools/tests/test_obs_local_hooks.sh` (new directory `~/.claude/tools/tests/` if it doesn't already exist as a place for local-lane tests — check first: `ls ~/.claude/tools/tests/` before creating, and if a different convention already exists there, follow it instead)

- [ ] **Step 1: Check for an existing local-lane test convention**

Run: `ls ~/.claude/tools/tests/ 2>&1 | head -20`
If a test directory and runner already exist, place the new test file there following that convention instead of the one below. If none exists, proceed with Step 2 as specified.

- [ ] **Step 2: Write the failing shell test**

Create `~/.claude/tools/tests/test_obs_local_hooks.sh`:

```bash
#!/bin/bash
# test_obs_local_hooks.sh — gate.decision/hook.error emission from the three
# local-only hooks (account-guard, prompt-clarity-gate, zoom-token-refresh).
set -u

HOOKS="$HOME/.claude/hooks"
TOOLS="$HOME/.claude/tools"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

events_file() { find "$TMP/claude/metrics/events" -name '*.ndjson' 2>/dev/null | head -1; }
last_records() { f="$(events_file)"; [ -n "$f" ] && cat "$f" || true; }

# --- account-guard.sh: warn path (wrong account for a guarded tree) --------
payload="$(python3 -c "import json; print(json.dumps({'session_id':'lg1','cwd':'$HOME/dev/HurstDataConsultingLLC/HDCx68Sports'}))")"
python3 -c "
import json, sys
d = json.load(open('$HOME/.claude.json'))
print(json.dumps(d.get('oauthAccount', {})))
" >/dev/null 2>&1  # sanity: real ~/.claude.json is untouched by this test
printf '%s' "$payload" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" bash "$HOOKS/account-guard.sh" >/dev/null 2>&1
recs="$(last_records)"
if [ -n "$(events_file)" ]; then
  pass "account-guard: hook ran and events dir exists"
else
  die "account-guard: no events dir created (check TOOLS_DIR points at a linked obs_emit.py)"
fi

# --- prompt-clarity-gate.sh: force-off ("raw:") -> gate.decision silent ----
payload="$(python3 -c "import json; print(json.dumps({'session_id':'lg2','prompt':'raw: a short prompt'}))")"
printf '%s' "$payload" | env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" PROMPT_CLARITY_GATE_DISABLE=0 bash "$HOOKS/prompt-clarity-gate.sh" >/dev/null 2>&1
recs="$(last_records)"
echo "$recs" | grep -q '"gate":"clarity".*"action":"silent"' && pass "prompt-clarity-gate: silent path recorded" || die "prompt-clarity-gate: silent missing (got: $recs)"

# --- zoom-token-refresh.sh: trap present, hook still exits 0 with no secrets file
rc=0
env CLAUDE_DIR="$TMP/claude" TOOLS_DIR="$TOOLS" bash "$HOOKS/zoom-token-refresh.sh" || rc=$?
[ "$rc" -eq 0 ] && pass "zoom-token-refresh: still exits 0" || die "zoom-token-refresh: exit $rc"
grep -q '_obs_hook_error' "$HOOKS/zoom-token-refresh.sh" && pass "zoom-token-refresh: trap present" || die "zoom-token-refresh: trap missing"

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_obs_local_hooks.sh"; exit 0
else
  echo "SOME FAILED - test_obs_local_hooks.sh"; exit 1
fi
```

- [ ] **Step 3: Run test to verify it fails**

Run: `bash ~/.claude/tools/tests/test_obs_local_hooks.sh`
Expected: fails — no `gate.decision`/trap instrumentation exists yet in these three files.

- [ ] **Step 4: Instrument `~/.claude/hooks/account-guard.sh`**

Full replacement file:

```bash
#!/bin/bash
# SessionStart hook — warns when the CLI's authenticated account (~/.claude.json,
# machine-wide, not per-directory) doesn't match the account a guarded tree
# expects. Prevents e.g. an artifact publishing under the wrong account.
# Additive-only: always exits 0, degrades to silence on any missing input.
set -u

_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="account-guard.sh" \
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

emit_gate() {
  # emit_gate <action>
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" \
    ACCT_GATE_SESSION_ID="$SESSION_ID" ACCT_GATE_ACTION="$1" \
    python3 -c '
import os, sys
sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))
try:
    import obs_emit
    obs_emit.emit("gate.decision", session_id=os.environ.get("ACCT_GATE_SESSION_ID"),
                  gate="account", action=os.environ.get("ACCT_GATE_ACTION"))
except Exception:
    pass
' >/dev/null 2>&1 || true
}

# Guard table: "<path prefix>|<accepted accounts, comma-separated>".
# Checks the CLAUDE account, not commit/invoice email. Correct account is
# rhurst1029@berkeley.edu (fixed 2026-07-31; was wrongly gmail.com).
GUARDS="\
$HOME/dev/HurstDataConsultingLLC|rhurst1029@berkeley.edu"

# Session cwd/session_id come via stdin JSON; fall back to $PWD/"unknown".
STDIN_JSON=""
if [ ! -t 0 ]; then STDIN_JSON="$(cat 2>/dev/null || true)"; fi
SESSION_CWD=""
SESSION_ID=""
if [ -n "$STDIN_JSON" ] && command -v python3 >/dev/null 2>&1; then
  SESSION_CWD="$(printf '%s' "$STDIN_JSON" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("cwd", "") or "")
except Exception:
    print("")
' 2>/dev/null)"
  SESSION_ID="$(printf '%s' "$STDIN_JSON" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("session_id", "") or "")
except Exception:
    print("")
' 2>/dev/null)"
fi
[ -n "$SESSION_CWD" ] || SESSION_CWD="$PWD"
[ -n "$SESSION_ID" ] || SESSION_ID="unknown"

CLAUDE_JSON="$HOME/.claude.json"
[ -r "$CLAUDE_JSON" ] || { emit_gate silent; exit 0; }
command -v python3 >/dev/null 2>&1 || exit 0

ACTUAL="$(python3 -c '
import json, os, sys
try:
    with open(os.path.expanduser("~/.claude.json"), encoding="utf-8") as fh:
        print(json.load(fh).get("oauthAccount", {}).get("emailAddress", "") or "")
except Exception:
    print("")
' 2>/dev/null)"
[ -n "$ACTUAL" ] || { emit_gate silent; exit 0; }

# Longest matching prefix wins (nested tree overrides a broader one).
BEST_PREFIX=""
EXPECTED=""
while IFS='|' read -r prefix account; do
  [ -n "$prefix" ] || continue
  case "$SESSION_CWD/" in
    "$prefix"/*)
      if [ "${#prefix}" -gt "${#BEST_PREFIX}" ]; then
        BEST_PREFIX="$prefix"
        EXPECTED="$account"
      fi
      ;;
  esac
done <<EOF
$GUARDS
EOF

if [ -z "$EXPECTED" ]; then emit_gate silent; exit 0; fi  # unguarded tree — say nothing

# Exact match on a whole comma-separated entry; substrings must not pass.
case ",$EXPECTED," in
  *",$ACTUAL,"*) emit_gate silent; exit 0 ;;
esac

TREE="${BEST_PREFIX##*/}"
emit_gate warn
cat <<EOF
<account-guard>
WRONG ACCOUNT for $TREE ($SESSION_CWD): logged in as $ACTUAL, needs $EXPECTED.
Until switched: no Artifact publishing, no PRs/pushes, no outward-facing
authored actions. Tell the user in your first reply. Fix: /login as $EXPECTED,
then restart. Guard table wrong instead? Edit ~/.claude/hooks/account-guard.sh.
</account-guard>
EOF
exit 0
```

- [ ] **Step 5: Instrument `~/.claude/hooks/prompt-clarity-gate.sh`**

Change the header block (currently lines 19–43) to add the trap and `TOOLS_DIR`:
```bash
set -u

[ "${PROMPT_CLARITY_GATE_DISABLE:-0}" = "1" ] && exit 0

_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="prompt-clarity-gate.sh" \
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
TOOLS_DIR="${TOOLS_DIR:-$CLAUDE_DIR/tools}"
SECRETS_ENV="${SECRETS_ENV:-$CLAUDE_DIR/secrets.env}"
STATE_DIR="${STATE_DIR:-$CLAUDE_DIR/metrics/state/prompt-clarity-gate}"
```
(everything else in the original header, `MIN_WORDS` through `BLOCK_STREAK_WINDOW_MIN`, is unchanged — just now positioned after this block.)

Add `TOOLS_DIR="$TOOLS_DIR"` to the existing env-var prefix list on the `python3 <<'PY'` invocation (alongside `HOOK_JSON=`, `SECRETS_ENV=`, etc.).

Inside the heredoc, immediately after `import sys` (top of the block), add:
```python
sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))
try:
    import obs_emit
except Exception:
    obs_emit = None
```

Replace `bail()`/`emit_block()`/`emit_context()` (currently):
```python
def bail():
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(0)

def emit_block(reason):
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    bail()

def emit_context(text):
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": text,
        }
    }))
    bail()
```
with:
```python
def bail(action="silent"):
    if obs_emit is not None:
        try:
            obs_emit.emit("gate.decision", session_id=session_id,
                           gate="clarity", action=action)
        except Exception:
            pass
    try:
        sys.stdout.flush()
    except Exception:
        pass
    os._exit(0)

def emit_block(reason):
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    bail(action="block")

def emit_context(text):
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": text,
        }
    }))
    bail(action="inject")
```

(`session_id` is already assigned at line 78, before every `bail()` call site — safe to reference.)

- [ ] **Step 6: Instrument `~/.claude/hooks/zoom-token-refresh.sh`**

Add the trap block right after `set -u` (currently line 13):
```bash
set -u

_obs_hook_error() {
  TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" HOOK_NAME="zoom-token-refresh.sh" \
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
```
No `gate.decision` call — this hook has no gate/decision concept, only the `hook.error` breadcrumb per the spec's "all 13 hook scripts" trap requirement.

- [ ] **Step 7: Run test to verify it passes**

Run: `bash ~/.claude/tools/tests/test_obs_local_hooks.sh`
Expected: `ALL PASS - test_obs_local_hooks.sh`

- [ ] **Step 8: Manually verify against a real session**

Tail the real events file after this session's next hook fires:
Run: `tail -5 ~/.claude/metrics/events/$(date -u +%Y-%m-%d).ndjson 2>/dev/null | python3 -m json.tool` (or `python3 -c "import json,sys; [print(json.loads(l)) for l in sys.stdin]"` if `python3 -m json.tool` doesn't handle NDJSON directly — pipe each line through `json.loads` individually).
Expected: real `tool.pre`/`tool.post`/`gate.decision`/`skill.invoked` records from this actual session, once Tasks 1–5 are installed and this session's own hooks fire again.

- [ ] **Step 9: Commit (in the `~/.claude` repo, not `claude-agent-loop`)**

```bash
cd ~/.claude
git add hooks/account-guard.sh hooks/prompt-clarity-gate.sh hooks/zoom-token-refresh.sh \
        tools/tests/test_obs_local_hooks.sh
git commit -m "$(cat <<'EOF'
feat(observability): instrument local-only hooks with obs.v1 events

(1) Task & Change
account-guard.sh, prompt-clarity-gate.sh, and zoom-token-refresh.sh sit
outside payload/ by this framework's local-lane convention (install.sh never
touches them). This is their own hand-edit, per the agent-observability-
layer spec's explicit allowance for gated-lane changes in this build.
account-guard gains gate="account" (silent/warn); prompt-clarity-gate gains
gate="clarity" (silent/block/inject); zoom-token-refresh gains only the
hook.error trap (it has no gate decision to record).

(2) Tests created / modified
- tools/tests/test_obs_local_hooks.sh: account-guard hook-runs check,
  prompt-clarity-gate silent-path record, zoom-token-refresh trap presence
  and unchanged exit-0 behavior.

(3) Test results — evidence
bash tools/tests/test_obs_local_hooks.sh
ALL PASS - test_obs_local_hooks.sh
EOF
)"
```

No push — this repo has no remote configured (confirmed via `git remote -v` returning empty).

---

## Self-review checklist (run before dispatching Task 1)

- [x] Every spec requirement in Phase 1 (spec lines 40–124) maps to a task: `obs_emit.py` → Task 1; `obs-events.sh` + fragment bindings → Task 2; `gate.decision` on the 4 named gates → Tasks 3 + 6; `skill.invoked` → Task 4; `hook.error` trap on all 13 hooks → Tasks 5 + 6.
- [x] No placeholder code — every step above has real, complete, runnable code.
- [x] Type/signature consistency: `obs_emit.emit()`'s signature is identical everywhere it's called across Tasks 2–6 (`event`, then `session_id=`, `agent_id=`, `plan_id=`, `part_id=`, `project=`, `**attrs`).
- [x] Both git repos and their commit boundaries are explicit (Task 6 lands in `~/.claude`, not `claude-agent-loop`).
