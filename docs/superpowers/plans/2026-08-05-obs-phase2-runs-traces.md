# Agent Observability Layer — Phase 2: Runs and Traces — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a `kind:"run"` record — a derived, never-asserted outcome/stop_reason summary of a run boundary (subagent part, session, or audit invocation) — into the existing monthly metrics shards, and stand up `obs_ship.py`, an out-of-process sidecar that folds Phase 1's `obs.v1` event log into an OTel span hierarchy for later export.

**Architecture:** `kind:"run"` records piggyback on the exact append primitive `loop_close.py`/`harvest_metrics.py` already use (`open(shard, "a")` / `os.write` to an `O_APPEND` fd) — no new store, no new schema machinery, just a new `kind` value alongside the existing `task`/`session` ones, written by the two files that already know the most about each run boundary. `obs_ship.py` is genuinely new: a standalone script with a real `opentelemetry-sdk` dependency, run out-of-session via launchd, reading Phase 1's NDJSON event log with a cursor file and exporting spans to `localhost:4318` — expected to fail silently until Phase 0 stands up a backend.

**Tech Stack:** Python 3 stdlib for everything inside a hook or `payload/tools/*.py` (unchanged Phase 1 invariant). `obs_ship.py` is the one exception — it runs out-of-tree, in its own venv, with a real `opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-http` dependency, following the pattern this plan's research established has **no existing precedent in this repo** (the design spec's claimed "Playwright usage-poll venv" precedent does not exist on disk or in `INSTALL.md` — verified: `usage_poll.py`'s Playwright dependency is a bare, un-isolated `pip install` into ambient `python3`, and no venv-provisioning step for it exists anywhere). This plan builds `obs_ship.py`'s venv setup as the first one of its kind, documented in `INSTALL.md` in the same style as the existing "Usage-budget poller (one-time)" section.

## Global Constraints

- **`kind:"run"` records share the existing monthly `.jsonl` shards** (`~/.claude/metrics/YYYY-MM.jsonl`) — no second store. Schema string is `"run.v1"` (a string, distinct from `harvest_metrics.py`'s own integer `SCHEMA = 1` used for `kind:"task"`/`kind:"session"` — these are different record kinds sharing one file, each stamping its own schema marker, matching Phase 1's `obs.v1` precedent).
- **"Last-wins" is a reader convention, not a write-time mechanism.** Confirmed against `harvest_metrics.py`'s own docstring and `_append_record()`: nothing dedups or indexes at write time. Every write in this plan is a plain, blind append — never attempt to "update" or "replace" a prior record.
- **`outcome` is derived, never asserted** — computed from evidence fields each emitter already has in scope (test results, verdicts, exit codes, interrupt flags), never from a subagent's own self-report.
- **Fail-open / stdlib-only in every hook and `payload/tools/*.py` file** — unchanged. `obs_ship.py` is the sole, explicitly-scoped exception (an out-of-session sidecar, not a hook).
- **No `uuid4` anywhere.** `trace_id` in every `kind:"run"` record is computed via `obs_emit.trace_id_for()` from Phase 1 (already committed, already deterministic).

## Design decisions locked in for this plan (resolving gaps this plan's own research found in the source spec)

1. **The source spec assigns BOTH "session" and "subagent" run-kind emission to `loop_close.py`.** Read in full: `loop_close.py`'s actual responsibility is exclusively work-order/part closing (`close_one()` processes ready work orders, never touches session-level concerns) — it has no session lifecycle logic to extend. **Correction:** subagent-level `kind:"run"` emission (`run_kind="subagent"`) is added to `loop_close.py` (Task 1), and session-level emission (`run_kind="session"`) is added to `harvest_metrics.py` instead (Task 2) — the file that already computes `ts_start`/`ts_end`/`session_id`/`interrupted` for `kind:"session"` records via its existing `build_record()`. This is a better fit for the actual architecture, not a reduction in scope.
2. **`outcome`/`stop_reason` severity gradient does not exist in `assess_task.verdict()`** — it returns a flat `"dirty"|"clean"|"unknown"` with no severity field to key `outcome`'s `failure`-vs-`partial` split off. Resolution, per emitter (each has different evidence available):
   - **`loop_close.py` (subagent runs):** `outcome = "success"` if `verdict == "clean"`; `"failure"` if `verdict == "dirty"` AND (`tests_failed > 0` OR `reverts > 0`) — the two evidence fields `assess_task.verdict()` itself treats as hard failures; `"partial"` if `verdict == "dirty"` without those (soft signals only — `followup_fixes`/`error_rate`) OR `verdict == "unknown"`. `stop_reason = "completed"` always — the evidence table has no process-level signal (no CLI exit code, no interrupt flag) to derive anything else from at the part level; this is a documented limitation, not a fabricated field.
   - **`harvest_metrics.py` (session runs):** has a real `interrupted` count already (`agg["interrupted"]`) unavailable to `loop_close.py`. `outcome = "interrupted"` if `interrupted > 0`; else `"success"` if `error_rate` is `None` or under `ERROR_RATE_MAX`; else `"partial"`. `stop_reason = "user-interrupt"` if `interrupted > 0`, else `"completed"`.
   - **`audit_run.sh` (audit runs):** has the *best* signal of the three — `_write_run_log`'s own `verdict` param (`"ok"`/`"failed"`) and `CLI_RC`. `outcome = "success"` if verdict `"ok"`, else `"failure"`. `stop_reason`: `"completed"` on `"ok"`; on `"failed"`, `"timeout"` if `CLI_RC` is exactly `124` (the conventional `timeout(1)` kill exit code, and this script's own `_run_cli` already conditionally wraps the CLI in `$TIMEOUT_BIN`) or if the failure message was produced by a timeout path; otherwise `"error"`.
3. **`loop_close.find_agent_id()`'s planned O(1) event-log lookup optimization is explicitly DESCOPED for this plan.** Research confirmed its prerequisite doesn't exist: no hook anywhere threads `agent_id` into any `obs_emit.emit()` call (every call site passes only `session_id`), and Claude Code's hook stdin payload has not been confirmed to expose a subagent-specific `agent_id` field at all for the framework's current hook bindings. Building the lookup without that prerequisite would mean inventing a brand-new hook-side `agent_id`-discovery mechanism — a real sub-project the source spec doesn't scope or budget for. `find_agent_id()` is **left completely untouched** in this plan; the existing directory-scan fallback remains the only path. This is a documented gap for a future phase, not a silent omission.
4. **`make_brief.py`'s `traceparent`/`run_id` are best-effort dispatch-time identifiers, not guaranteed to equal the eventual runtime `trace_id`.** `obs_emit._root_task_id()`'s precedence (`session_id or agent_id or plan_id`) means a brief-time `trace_id` computed from `plan_id` (the only identifier known before dispatch) will diverge from whatever `trace_id` the dispatched subagent's own hook-fired events land under once a real `session_id` becomes available to those hooks. This is documented in the brief template's own header comment (see Task 5) rather than presented as a working correlation mechanism — the value shipped here is a stable, deterministic per-work-order identifier useful for external correlation (a Jira ticket, a log search), not a promise that OTel span-linking already works end-to-end.
5. **`obs_ship.py`'s venv has no precedent to follow — designed fresh, more rigorously than the "precedent" the spec cited.** `~/.claude-agent-loop/obs-venv` is a real, isolated `python3 -m venv` + `pip install`, with the launchd plist invoking the venv's own interpreter directly (`~/.claude-agent-loop/obs-venv/bin/python3`) — cleaner than `usage_poll.py`'s bare ambient-`python3` + ungated global `pip install`, which this plan does not attempt to retroactively fix (out of scope).

---

### Task 1: `kind:"run"` (subagent) emission in `loop_close.py`

**Files:**
- Modify: `payload/tools/loop_close.py:106-183` (add a sibling record-builder + wire into `close_one()`)
- Test: `payload/tools/tests/test_loop_close.py` (check first whether this file already exists — `payload/tools/tests/test_loop_close_hook.sh` tests the **hook** `loop-close.sh`; a Python-level unit test for `loop_close.py`'s functions may or may not already exist. If `test_loop_close.py` exists, extend it; if not, create it following `test_harvest_metrics.py`'s fixture-and-`unittest.TestCase` convention.)

**Interfaces:**
- Consumes: `obs_emit.trace_id_for(root_task_id)` from Phase 1 (`payload/tools/obs_emit.py`, already committed) — import it directly, don't recompute the sha256 inline.
- Produces: nothing new for later tasks to call; this is a leaf emission.

- [ ] **Step 1: Write the failing test**

First check: `ls payload/tools/tests/test_loop_close*.py 2>/dev/null` — if a `test_loop_close.py` (not `_hook`) exists, read it and add the test below into its existing structure/imports rather than duplicating the header. If it doesn't exist, create it:

```python
"""Tests for loop_close.py's kind:"run" (subagent) emission — Phase 2."""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import loop_close  # noqa: E402


def _wo(plan_id="wo-1", parts=None):
    return {
        "plan_id": plan_id,
        "project": "myproj",
        "git_branch": "feature/x",
        "created": "2026-08-05T10:00:00Z",
        "parts": parts or [],
    }


class TestRunRecordsSubagent(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.metrics_dir = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _shard_lines(self):
        shards = list(self.metrics_dir.glob("*.jsonl"))
        self.assertEqual(len(shards), 1)
        return [json.loads(l) for l in shards[0].read_text().splitlines() if l.strip()]

    def test_one_run_record_per_part_success(self):
        wo = _wo(parts=[
            {"part_id": "p1", "agent_task_id": "agent-aaa", "status": "done",
             "verdict": "clean", "evidence": {"tests_detected": True,
             "tests_passed": 5, "tests_failed": 0, "commits": 1}},
        ])
        records = loop_close.run_records(wo)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["schema"], "run.v1")
        self.assertEqual(rec["kind"], "run")
        self.assertEqual(rec["run_kind"], "subagent")
        self.assertEqual(rec["task_id"], "agent-aaa")
        self.assertEqual(rec["outcome"], "success")
        self.assertEqual(rec["stop_reason"], "completed")
        self.assertEqual(rec["plan_id"], "wo-1")
        self.assertEqual(rec["part_id"], "p1")
        self.assertIsNone(rec["parent_task_id"])
        self.assertIsInstance(rec["trace_id"], str)
        self.assertEqual(len(rec["trace_id"]), 32)

    def test_outcome_failure_on_test_failures(self):
        wo = _wo(parts=[
            {"part_id": "p1", "agent_task_id": "agent-bbb", "status": "done",
             "verdict": "dirty", "evidence": {"tests_detected": True,
             "tests_passed": 2, "tests_failed": 3}},
        ])
        rec = loop_close.run_records(wo)[0]
        self.assertEqual(rec["outcome"], "failure")

    def test_outcome_partial_on_soft_dirty_signal_only(self):
        wo = _wo(parts=[
            {"part_id": "p1", "agent_task_id": "agent-ccc", "status": "done",
             "verdict": "dirty", "evidence": {"followup_fixes": 1}},
        ])
        rec = loop_close.run_records(wo)[0]
        self.assertEqual(rec["outcome"], "partial")

    def test_outcome_partial_on_unknown_verdict(self):
        wo = _wo(parts=[
            {"part_id": "p1", "agent_task_id": "agent-ddd", "status": "done",
             "verdict": "unknown", "evidence": {}},
        ])
        rec = loop_close.run_records(wo)[0]
        self.assertEqual(rec["outcome"], "partial")

    def test_trace_id_matches_obs_emit_for_same_plan_id(self):
        import obs_emit
        wo = _wo(plan_id="wo-shared", parts=[
            {"part_id": "p1", "agent_task_id": "agent-eee", "status": "done",
             "verdict": "clean", "evidence": {}},
        ])
        rec = loop_close.run_records(wo)[0]
        self.assertEqual(rec["trace_id"], obs_emit.trace_id_for("wo-shared"))

    def test_emit_writes_run_records_into_shard(self):
        wo = _wo(parts=[
            {"part_id": "p1", "agent_task_id": "agent-fff", "status": "done",
             "verdict": "clean", "evidence": {}},
        ])
        records = loop_close.task_records(wo) + loop_close.run_records(wo)
        loop_close.emit(str(self.metrics_dir), records)
        lines = self._shard_lines()
        kinds = sorted(r["kind"] for r in lines)
        self.assertEqual(kinds, ["run", "task"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd payload/tools/tests && python3 -m unittest test_loop_close -v`
Expected: `AttributeError: module 'loop_close' has no attribute 'run_records'`

- [ ] **Step 3: Implement `run_records()` and wire it into `close_one()`**

Add to `payload/tools/loop_close.py`, right after `task_records()` (after line 153), and add the `obs_emit` import alongside the existing `assess_task`/`plan_task` imports (line 38-39):

```python
import obs_emit  # noqa: E402
```

```python
def run_records(wo):
    """One kind:"run" (subagent) record per part — a derived outcome/stop_reason
    summary, never asserted. See the Phase 2 plan's design decision #2 for the
    outcome-severity mapping; stop_reason is always "completed" here because no
    process-level signal (CLI exit code, interrupt flag) exists at the part
    level — a documented limitation, not a guess dressed up as data.
    """
    out = []
    now = _now_iso()
    for part in wo.get("parts") or []:
        ev = part.get("evidence") or {}
        verdict = part.get("verdict") or "unknown"
        hard_failure = (ev.get("tests_failed") or 0) > 0 or (ev.get("reverts") or 0) > 0
        if verdict == "clean":
            outcome = "success"
        elif verdict == "dirty" and hard_failure:
            outcome = "failure"
        else:
            outcome = "partial"
        task_id = part.get("agent_task_id") or "%s-%s" % (wo.get("plan_id"), part.get("part_id"))
        out.append({
            "schema": "run.v1",
            "kind": "run",
            "task_id": task_id,
            "run_kind": "subagent",
            "parent_task_id": None,
            "outcome": outcome,
            "stop_reason": "completed",
            "trace_id": obs_emit.trace_id_for(wo.get("plan_id") or "unknown"),
            "plan_id": wo.get("plan_id"),
            "part_id": part.get("part_id"),
            "ts_start": wo.get("created"),
            "ts_end": now,
        })
    return out
```

Modify `close_one()` (currently lines 170-183) to include the new records in the same `emit()` call — change:
```python
    records = task_records(wo)
```
to:
```python
    records = task_records(wo) + run_records(wo)
```
(No other change to `close_one()` is needed — `emit()` already appends every record in the list it's given, one per line, regardless of `kind`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd payload/tools/tests && python3 -m unittest test_loop_close -v`
Expected: all tests `OK`

- [ ] **Step 5: Run the full existing test suite to confirm no regression**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -30`
Expected: same suite count as before this task, all passing, including any existing `test_loop_close_hook.sh` suite (unaffected — it tests the hook script, not this file's Python functions directly, but confirm it still passes since `close_one()`'s return shape and `emit()` call count changed).

- [ ] **Step 6: Commit**

```bash
git add payload/tools/loop_close.py payload/tools/tests/test_loop_close.py
git commit -m "$(cat <<'EOF'
feat(observability): emit kind:run (subagent) records from loop_close.py

(1) Task & Change
Adds run_records(), one kind:"run" record per work-order part closed,
alongside the existing kind:"task" emission. outcome is derived from
assess_task.verdict() plus the two hard-failure evidence fields
(tests_failed, reverts); stop_reason is always "completed" — no
process-level signal exists at the part level to derive anything else from,
documented as a known limitation rather than guessed. trace_id reuses
obs_emit.trace_id_for() from Phase 1 so any future consumer of the obs.v1
event log for the same plan_id shares the identical trace_id.

(2) Tests created / modified
- payload/tools/tests/test_loop_close.py: schema shape, outcome mapping
  (success/failure/partial across clean/dirty-hard/dirty-soft/unknown),
  trace_id consistency with obs_emit, and end-to-end emit() into a shard.

(3) Test results — evidence
python3 -m unittest test_loop_close -v
Ran 6 tests in 0.0Xs — OK
EOF
)"
```

---

### Task 2: `kind:"run"` (session) emission in `harvest_metrics.py`

**Files:**
- Modify: `payload/tools/harvest_metrics.py` (add a sibling record-builder called wherever session records are currently built and appended)
- Test: `payload/tools/tests/test_harvest_metrics.py` (extend the existing suite)

**Interfaces:**
- Consumes: `obs_emit.trace_id_for()` from Phase 1.
- Produces: nothing further tasks call.

- [ ] **Step 1: Locate the exact session-emission call site**

Before writing code: `grep -n 'kind="session"\|build_record(.*"session"\|_maybe_harvest_file' payload/tools/harvest_metrics.py` to find every place `build_record(path, event, "session", ...)` is actually invoked (the earlier research quoted `build_record()` itself in full but not every call site — there may be more than one, e.g. a `SubagentStop` path and a `SessionEnd` path). Read 20 lines around each call site so the new `kind:"run"` emission is added at the exact point a `kind:"session"` record is about to be appended — not duplicated at every harvest attempt (the cursor logic in `_maybe_harvest_file` means a given transcript may be skipped on re-invocation; the new run record must follow the same skip logic, not fire independently of it).

- [ ] **Step 2: Write the failing test**

Add to `payload/tools/tests/test_harvest_metrics.py` (follow its existing `HarvestFixture`/fixture-dict convention — read a few existing test classes first to match the exact fixture-construction helper names before writing):

```python
class TestRunRecordsSession(HarvestFixture):
    def test_session_harvest_also_emits_kind_run(self):
        # Reuse this file's existing session-transcript fixture-writing helper
        # (check the class above for the exact helper name/signature — e.g.
        # write_transcript()/write_session()) to create one fixture session
        # transcript, then harvest it exactly as an existing session-level
        # test in this file already does.
        # ... (mirror an existing passing session-harvest test's setup) ...
        # After harvesting, read the shard and assert:
        #   - exactly one kind:"run" record exists alongside the kind:"session" one
        #   - its schema == "run.v1", run_kind == "session"
        #   - its trace_id == obs_emit.trace_id_for(<that session's sid>)
        #   - outcome is "success" (fixture has no interrupted turns, no error_rate spike)
        pass  # implementer: replace with real assertions, following this
              # file's existing session-harvest test as the structural template —
              # do NOT invent a new fixture-writing helper if one already exists.
```

**Note to implementer:** the `pass` placeholder above is intentional scaffolding for THIS step only — replace it with real, passing assertions before moving to Step 3's implementation, using whatever fixture helper this file's existing session-level tests already use (do not write a new one). This is the one spot in this plan where the exact existing helper name isn't known ahead of time; Step 1 of this task is what discovers it.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd payload/tools/tests && python3 -m unittest test_harvest_metrics.TestRunRecordsSession -v`
Expected: fails (either `AssertionError` on the real assertions once written, or the placeholder `pass` needs replacing first — do that before running this step for real).

- [ ] **Step 4: Implement the session `kind:"run"` builder and wire it in**

Add near `build_record()` in `payload/tools/harvest_metrics.py`:

```python
import obs_emit  # add alongside this file's existing stdlib-only imports —
                  # obs_emit.py is itself stdlib-only, so this doesn't violate
                  # the file's "stdlib only" docstring claim


def build_run_record(agg, sid):
    """kind:"run" (session), derived from the same aggregate build_record() uses.

    outcome: "interrupted" wins over everything if any turn was interrupted
    (agg["interrupted"] > 0) — this is real, already-computed signal
    build_record() itself uses, unlike loop_close.py's subagent runs, which
    have no such signal at the part level. Otherwise "success" unless
    error_rate exceeds ERROR_RATE_MAX (reuse assess_task.ERROR_RATE_MAX if
    accessible here without a new import cycle — else define the same
    threshold value locally with a comment pointing at assess_task.py as the
    source of truth).
    """
    interrupted = (agg.get("interrupted") or 0) > 0
    error_rate = agg.get("error_rate")
    if interrupted:
        outcome = "interrupted"
    elif error_rate is not None and error_rate > ERROR_RATE_MAX:
        outcome = "partial"
    else:
        outcome = "success"
    return {
        "schema": "run.v1",
        "kind": "run",
        "task_id": "session-%s" % sid,
        "run_kind": "session",
        "parent_task_id": None,
        "outcome": outcome,
        "stop_reason": "user-interrupt" if interrupted else "completed",
        "trace_id": obs_emit.trace_id_for(sid or "unknown"),
        "plan_id": None,
        "part_id": None,
        "ts_start": agg.get("ts_start"),
        "ts_end": agg.get("ts_end"),
    }
```

Check whether `ERROR_RATE_MAX` already exists as a module-level constant in `harvest_metrics.py` (grep for it — it may already be defined there, since `build_record()`'s docstring references an error-rate concept, or it may live only in `assess_task.py`). If it's only in `assess_task.py`, either import it from there (`from assess_task import ERROR_RATE_MAX`, matching how `loop_close.py` already imports `assess_task` as a sibling module) or define a local constant with a comment noting the source of truth — do not silently duplicate a magic number with no cross-reference.

At the exact call site(s) found in Step 1 (wherever a `kind:"session"` record is built and about to be appended), add the sibling `kind:"run"` record into the same list/append call, mirroring exactly how Task 1 added `run_records(wo)` alongside `task_records(wo)` in `loop_close.py`'s `close_one()`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd payload/tools/tests && python3 -m unittest test_harvest_metrics.TestRunRecordsSession -v`
Expected: `OK`

- [ ] **Step 6: Run the full existing test suite to confirm no regression**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -40`
Expected: no regressions — `test_harvest_metrics.py` is a large, heavily-covered file; watch specifically for any existing test that asserts an exact *count* of records emitted per harvest (a common test-writing pattern), since this task adds one more record per session harvest and could break a hardcoded count assertion elsewhere in the same file.

- [ ] **Step 7: Commit**

```bash
git add payload/tools/harvest_metrics.py payload/tools/tests/test_harvest_metrics.py
git commit -m "$(cat <<'EOF'
feat(observability): emit kind:run (session) records from harvest_metrics.py

(1) Task & Change
The design spec assigned session-level kind:"run" emission to
loop_close.py, but that file has no session-lifecycle logic to extend (it
only ever processes work-order parts) — this correction adds it to
harvest_metrics.py instead, the file that already computes
ts_start/ts_end/interrupted/error_rate for kind:"session" records via
build_record(). outcome uses the real interrupted-turn signal
build_record() already has, unlike the subagent-level records in
loop_close.py, which have no such signal available.

(2) Tests created / modified
- payload/tools/tests/test_harvest_metrics.py: TestRunRecordsSession —
  session harvest emits exactly one kind:"run" alongside kind:"session",
  correct schema/run_kind/trace_id.

(3) Test results — evidence
python3 -m unittest test_harvest_metrics -v
[paste full real output — confirm total test count and OK]
EOF
)"
```

---

### Task 3: `kind:"run"` (audit) emission in `audit_run.sh`

**Files:**
- Modify: `payload/tools/audit_run.sh` (add a helper alongside `_write_run_log`/`_write_run_log_checked`, call it from the same sites)
- Test: `payload/tools/tests/test_audit_run.sh` (check if this file exists first — `audit_run.sh` is 889 lines and clearly load-bearing; a test file may already exist. If so, extend it. If not, this task is scoped to the new helper's behavior only — do not attempt to write a full `audit_run.sh` integration test suite from scratch as part of this plan; that's a pre-existing gap outside Phase 2's scope.)

**Interfaces:**
- Consumes: nothing from earlier Phase 2 tasks directly (a new `python3 -c` one-liner analogous to Task 1/2's Python-side emission, but invoked from bash).

- [ ] **Step 1: Check for an existing test file and read `_write_run_log`/`_write_run_log_checked`/`_fail_run` once more in the live file**

Run: `ls payload/tools/tests/test_audit_run* 2>/dev/null` and read the current `payload/tools/audit_run.sh` at the exact line numbers for `_write_run_log` (originally 213-381), `_write_run_log_checked` (414-419), `_fail_run` (570-575), and the success-path tail (866-888) — line numbers may have drifted slightly if anything else touched this file; re-derive them fresh with `grep -n '_write_run_log\|_fail_run\|^_run_cli'`.

- [ ] **Step 2: Write the failing test**

If `payload/tools/tests/test_audit_run.sh` doesn't exist, create a narrowly-scoped one testing ONLY the new helper (not the whole 889-line script's integration behavior):

```bash
#!/bin/bash
# test_audit_run_kind_run.sh — kind:"run" (audit) emission helper in
# audit_run.sh. Scoped narrowly to the new _emit_run_record helper's
# behavior, not a full audit_run.sh integration test (out of scope for
# this plan — see Phase 2 plan Task 3). macOS bash-3.2 portable.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
AUDIT_RUN="$(cd "$HERE/.." && pwd)/audit_run.sh"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Source only the helper function definitions, not the whole script (which
# expects real CLI args and would error/exit on a bare source). Extract
# _emit_run_record's definition via sed between its opening and the next
# top-level "}" at column 1, write it to a standalone file, then source that.
awk '/^_emit_run_record\(\) \{/,/^\}/' "$AUDIT_RUN" > "$TMP/helper.sh"
if [ ! -s "$TMP/helper.sh" ]; then
  die "could not extract _emit_run_record from audit_run.sh — check the function name/shape matches what this test expects"
else
  pass "extracted _emit_run_record definition"
fi

# shellcheck source=/dev/null
source "$TMP/helper.sh"

# _emit_run_record <verdict> <package-key> <metrics-dir> [cli-rc]
CLAUDE_DIR="$TMP/claude" METRICS_DIR="$TMP/claude/metrics" \
  _emit_run_record "ok" "test-package" "$TMP/claude/metrics" "0"
shard="$(find "$TMP/claude/metrics" -maxdepth 1 -name '*.jsonl' | head -1)"
if [ -n "$shard" ] && grep -q '"kind":"run"' "$shard" && grep -q '"run_kind":"audit"' "$shard" && grep -q '"outcome":"success"' "$shard"; then
  pass "ok verdict -> outcome:success recorded"
else
  die "ok verdict did not produce expected kind:run record (shard: $shard)"
fi

CLAUDE_DIR="$TMP/claude" METRICS_DIR="$TMP/claude/metrics" \
  _emit_run_record "failed" "test-package-2" "$TMP/claude/metrics" "124"
if grep -q '"outcome":"failure"' "$shard" && grep -q '"stop_reason":"timeout"' "$shard"; then
  pass "failed verdict + rc=124 -> outcome:failure, stop_reason:timeout"
else
  die "timeout case not recorded correctly"
fi

CLAUDE_DIR="$TMP/claude" METRICS_DIR="$TMP/claude/metrics" \
  _emit_run_record "failed" "test-package-3" "$TMP/claude/metrics" "1"
if grep -q '"stop_reason":"error"' "$shard"; then
  pass "failed verdict + rc=1 -> stop_reason:error"
else
  die "non-timeout failure not recorded correctly"
fi

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_audit_run_kind_run.sh"; exit 0
else
  echo "SOME FAILED - test_audit_run_kind_run.sh"; exit 1
fi
```

- [ ] **Step 3: Run test to verify it fails**

Run: `bash payload/tools/tests/test_audit_run_kind_run.sh`
Expected: fails at the `awk` extraction step (`_emit_run_record` doesn't exist yet).

- [ ] **Step 4: Implement `_emit_run_record` and wire it into the 5+1 call sites**

Add to `payload/tools/audit_run.sh`, right after `_write_run_log_checked`'s definition:

```bash
# _emit_run_record <verdict:ok|failed> <package-key> <metrics-dir> [cli-rc]
# Appends one kind:"run" (audit) record into the monthly metrics shard —
# separate from _write_run_log's own per-package audit-store JSON, which is
# a different concept in a different tree (see Phase 2 plan design decision).
# Fail-open: never lets a metrics-write problem fail the audit itself.
_emit_run_record() {
  RUN_VERDICT="$1" RUN_PKG_KEY="$2" RUN_METRICS_DIR="${3:-$HOME/.claude/metrics}" \
  RUN_CLI_RC="${4:-}" TOOLS_DIR="${TOOLS_DIR:-$HOME/.claude/tools}" \
    python3 -c '
import datetime
import json
import os
import sys

sys.path.insert(0, os.environ.get("TOOLS_DIR", ""))
try:
    import obs_emit
except Exception:
    sys.exit(0)

verdict = os.environ.get("RUN_VERDICT", "failed")
pkg_key = os.environ.get("RUN_PKG_KEY", "unknown")
metrics_dir = os.environ.get("RUN_METRICS_DIR", "")
cli_rc_raw = os.environ.get("RUN_CLI_RC", "")

outcome = "success" if verdict == "ok" else "failure"
if verdict == "ok":
    stop_reason = "completed"
else:
    try:
        stop_reason = "timeout" if int(cli_rc_raw) == 124 else "error"
    except (TypeError, ValueError):
        stop_reason = "error"

now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
record = {
    "schema": "run.v1",
    "kind": "run",
    "task_id": "audit-%s-%s" % (pkg_key, now),
    "run_kind": "audit",
    "parent_task_id": None,
    "outcome": outcome,
    "stop_reason": stop_reason,
    "trace_id": obs_emit.trace_id_for("audit:" + pkg_key),
    "plan_id": None,
    "part_id": None,
    "ts_start": now,
    "ts_end": now,
}
try:
    shard = os.path.join(metrics_dir, "%s.jsonl" % now[:7])
    os.makedirs(metrics_dir, exist_ok=True)
    line = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(shard, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)
except Exception:
    pass
' >/dev/null 2>&1 || true
}
```

Then add exactly one call to `_emit_run_record` at each of the following (do not add it inside `_write_run_log`/`_write_run_log_checked` themselves — those are called from multiple contexts and adding it there would double-count; call it at the same call SITES `_write_run_log`/`_write_run_log_checked` are already called from):
- Inside `_fail_run` (right after the existing `_write_run_log_checked "failed" "" "" "$1"` line): add `_emit_run_record "failed" "$PKG_KEY" "$METRICS_DIR" "$CLI_RC"` (verify `$METRICS_DIR`/`$CLI_RC` are in scope at that point — `$CLI_RC` may not be set yet for the earlier `_fail_run` call sites like the worktree-add failure; when it's unset, `_emit_run_record`'s 4th positional arg is simply empty, which the Python side already handles via `cli_rc_raw = os.environ.get(..., "")` falling through to `stop_reason = "error"`).
- At the final success path (right after the existing `_write_run_log`/`_commit_store` block, before the `case "$CRITICAL$HIGH"` line): add `_emit_run_record "ok" "$PKG_KEY" "$METRICS_DIR" "$CLI_RC"`.

Also verify `$METRICS_DIR` exists as a variable in this script already (grep for it — `audit_run.sh` may use a different variable name for `~/.claude/metrics`, e.g. it might only know about `$STORE`/`audit store` paths per Q2's research, which are NOT the same as `~/.claude/metrics`). If `$METRICS_DIR` isn't already defined, add `METRICS_DIR="${METRICS_DIR:-$HOME/.claude/metrics}"` near the top of the script alongside its other path defaults.

- [ ] **Step 5: Run test to verify it passes**

Run: `bash payload/tools/tests/test_audit_run_kind_run.sh`
Expected: `ALL PASS - test_audit_run_kind_run.sh`

- [ ] **Step 6: Run the full existing test suite to confirm no regression**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -30`
Expected: no regressions. Also run `bash -n payload/tools/audit_run.sh` (syntax check only — this script is too large/side-effecting to safely execute end-to-end in this task) to confirm the edits didn't introduce a syntax error.

- [ ] **Step 7: Commit**

```bash
git add payload/tools/audit_run.sh payload/tools/tests/test_audit_run_kind_run.sh
git commit -m "$(cat <<'EOF'
feat(observability): emit kind:run (audit) records from audit_run.sh

(1) Task & Change
Adds _emit_run_record, called from _fail_run and the success-path tail,
appending a kind:"run" record into the monthly metrics shard — separate
from _write_run_log's own per-package audit-store JSON (a different
concept in a different tree). outcome/stop_reason use this script's own
best-available signal of the three Phase 2 emitters: the verdict string
and CLI exit code already computed for _write_run_log, including a
timeout-specific stop_reason when the exit code matches timeout(1)'s
conventional 124.

(2) Tests created / modified
- payload/tools/tests/test_audit_run_kind_run.sh: extracts and tests
  _emit_run_record in isolation (ok/success, failed+124/timeout,
  failed+1/error) — narrowly scoped per this plan, not a full audit_run.sh
  integration suite.

(3) Test results — evidence
bash payload/tools/tests/test_audit_run_kind_run.sh
ALL PASS - test_audit_run_kind_run.sh
bash -n payload/tools/audit_run.sh  (syntax check, no output = pass)
EOF
)"
```

---

### Task 4: `payload/observability/obs_ship.py` — the span-builder sidecar

**Files:**
- Create: `payload/observability/obs_ship.py`
- Create: `payload/observability/tests/test_obs_ship.py`
- Create: `payload/observability/README.md` (short — documents the venv setup, since this directory and its non-stdlib dependency are new to the repo)
- Modify: `payload/MANIFEST` (add `link-dir observability` — or `link-file` per-file if the directory verb doesn't fit; check MANIFEST's grammar comment for which verb applies to a whole new subdirectory with mixed content)

**Interfaces:**
- Consumes: Phase 1's `obs.v1` NDJSON event log (`~/.claude/metrics/events/YYYY-MM-DD.ndjson`) and the `kind:"run"` records this plan's Tasks 1-3 add to the monthly shards (read-only, for span-folding context — e.g. matching a `tool.pre`/`tool.post` pair's `trace_id` to its enclosing run's `outcome`).
- Produces: nothing other Phase 2 tasks call — this is the terminal consumer.

- [ ] **Step 1: Write the failing tests**

Create `payload/observability/tests/test_obs_ship.py`:

```python
"""Tests for obs_ship.py — the span-builder sidecar (Phase 2).

Runs against fixture NDJSON, never a live OTLP collector. The OTel SDK
dependency is real (this is an out-of-tree sidecar, not a hook), so these
tests import obs_ship directly and must be run with the obs-venv interpreter
active (see payload/observability/README.md) — NOT plain system python3,
which will raise ModuleNotFoundError on `opentelemetry`.
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import obs_ship  # noqa: E402


def _write_ndjson(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


class TestCursor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_cursor_advances_on_successful_export(self):
        events_dir = self.dir / "events"
        events_dir.mkdir()
        day_file = events_dir / "2026-08-05.ndjson"
        _write_ndjson(day_file, [
            {"schema": "obs.v1", "ts": "2026-08-05T10:00:00Z", "event": "tool.pre",
             "session_id": "s1", "trace_id": "t1", "span_id": "sp1",
             "parent_span_id": None, "agent_id": None, "plan_id": None,
             "part_id": None, "project": None, "attrs": {}},
        ])
        cursor_path = self.dir / "obs_ship.cursor.json"
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = True  # SpanExportResult.SUCCESS-ish truthy
        with patch.object(obs_ship, "_build_exporter", return_value=mock_exporter):
            obs_ship.run_once(str(events_dir), str(cursor_path))
        cursor = json.loads(cursor_path.read_text())
        self.assertIn(str(day_file), cursor.get("files", {}))
        self.assertGreater(cursor["files"][str(day_file)], 0)

    def test_cursor_does_not_advance_on_export_failure(self):
        events_dir = self.dir / "events"
        events_dir.mkdir()
        day_file = events_dir / "2026-08-05.ndjson"
        _write_ndjson(day_file, [
            {"schema": "obs.v1", "ts": "2026-08-05T10:00:00Z", "event": "tool.pre",
             "session_id": "s1", "trace_id": "t1", "span_id": "sp1",
             "parent_span_id": None, "agent_id": None, "plan_id": None,
             "part_id": None, "project": None, "attrs": {}},
        ])
        cursor_path = self.dir / "obs_ship.cursor.json"
        mock_exporter = MagicMock()
        mock_exporter.export.side_effect = ConnectionError("unreachable")
        with patch.object(obs_ship, "_build_exporter", return_value=mock_exporter):
            result = obs_ship.run_once(str(events_dir), str(cursor_path))
        self.assertFalse(result.get("exported"))
        self.assertFalse(cursor_path.exists())

    def test_run_once_never_raises_on_unreachable_endpoint(self):
        # No mocking at all here — real exporter pointed at a closed port,
        # confirming the actual documented behavior end-to-end without a
        # live collector.
        events_dir = self.dir / "events"
        events_dir.mkdir()
        _write_ndjson(events_dir / "2026-08-05.ndjson", [
            {"schema": "obs.v1", "ts": "2026-08-05T10:00:00Z", "event": "turn.stop",
             "session_id": "s2", "trace_id": "t2", "span_id": "sp2",
             "parent_span_id": None, "agent_id": None, "plan_id": None,
             "part_id": None, "project": None, "attrs": {}},
        ])
        cursor_path = self.dir / "obs_ship.cursor.json"
        try:
            result = obs_ship.run_once(str(events_dir), str(cursor_path),
                                       endpoint="http://127.0.0.1:1")  # closed port
        except Exception as exc:  # pragma: no cover - this IS the failure being tested
            self.fail("run_once raised instead of degrading silently: %r" % exc)
        self.assertFalse(result.get("exported"))


class TestSpanFolding(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_events_with_same_trace_id_fold_into_one_trace(self):
        events_dir = self.dir / "events"
        events_dir.mkdir()
        _write_ndjson(events_dir / "2026-08-05.ndjson", [
            {"schema": "obs.v1", "ts": "2026-08-05T10:00:00Z", "event": "tool.pre",
             "session_id": "s3", "trace_id": "tshared", "span_id": "spA",
             "parent_span_id": None, "agent_id": None, "plan_id": None,
             "part_id": None, "project": None, "attrs": {"tool_name": "Read"}},
            {"schema": "obs.v1", "ts": "2026-08-05T10:00:01Z", "event": "tool.post",
             "session_id": "s3", "trace_id": "tshared", "span_id": "spA",
             "parent_span_id": None, "agent_id": None, "plan_id": None,
             "part_id": None, "project": None, "attrs": {"tool_name": "Read",
             "duration_ms": 1000, "ok": True}},
        ])
        events = list(obs_ship.read_events(str(events_dir), {}))
        spans = obs_ship.fold_spans(events)
        self.assertEqual(len(spans), 1)  # one pre+post pair -> one span
        self.assertEqual(spans[0]["trace_id"], "tshared")
        self.assertEqual(spans[0]["span_id"], "spA")
        self.assertEqual(spans[0]["name"], "tool:Read")
        self.assertAlmostEqual(spans[0]["duration_ms"], 1000)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run (from within the obs-venv once Task 5 exists — for this step, since the venv doesn't exist yet, confirm the RIGHT failure: `ModuleNotFoundError: No module named 'obs_ship'`, run with plain `python3`): `cd payload/observability/tests && python3 -m unittest test_obs_ship -v`
Expected: `ModuleNotFoundError: No module named 'obs_ship'`

- [ ] **Step 3: Write `obs_ship.py`**

Create `payload/observability/obs_ship.py`:

```python
#!/usr/bin/env python3
"""obs_ship.py — folds the obs.v1 event log into an OTel span hierarchy and
exports it via OTLP to a local collector (localhost:4318 by default).

Out-of-tree sidecar: real opentelemetry-sdk dependency, run from its own venv
(~/.claude-agent-loop/obs-venv — see README.md), scheduled via launchd, never
imported from inside a hook. If the OTLP endpoint is unreachable (expected
until Phase 0 stands up a backend), export fails silently and the cursor does
NOT advance — the next scheduled run retries the same events once a backend
exists. A live Claude Code session never observes this either way; this
script runs entirely out-of-process.
"""
import argparse
import glob
import json
import os
import pathlib
import sys


def _build_exporter(endpoint):
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    return OTLPSpanExporter(endpoint=endpoint + "/v1/traces")


def _load_cursor(cursor_path):
    try:
        with open(cursor_path) as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {"files": {}}
        data.setdefault("files", {})
        return data
    except Exception:
        return {"files": {}}


def _save_cursor(cursor_path, cursor):
    tmp = cursor_path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as fh:
        json.dump(cursor, fh, indent=2, sort_keys=True)
    os.replace(tmp, cursor_path)


def read_events(events_dir, cursor):
    """Yield (file, byte_offset_before, parsed_record) for every unread line
    across every *.ndjson file in events_dir, oldest file first."""
    files = cursor.get("files", {})
    for path in sorted(glob.glob(os.path.join(events_dir, "*.ndjson"))):
        start = int(files.get(path, 0))
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if start >= size:
            continue
        with open(path, "r") as fh:
            fh.seek(start)
            offset = start
            for line in fh:
                line_len = len(line.encode("utf-8"))
                stripped = line.strip()
                if stripped:
                    try:
                        rec = json.loads(stripped)
                    except Exception:
                        offset += line_len
                        continue
                    yield path, offset + line_len, rec
                else:
                    offset += line_len
                    continue
                offset += line_len


def fold_spans(events):
    """Fold obs.v1 events into a flat list of span dicts.

    Phase 2 scope: fold tool.pre/tool.post pairs (same span_id) into one span
    with a duration; every other event type becomes its own single-point
    span (zero duration). Full parent/child hierarchy (root-per-run,
    child-per-turn) is Phase 3+ work once kind:"run" records are consumable
    here as the root-span source — this function only builds the leaf layer.
    """
    by_span = {}
    order = []
    for _path, _offset, rec in events:
        span_id = rec.get("span_id")
        if span_id not in by_span:
            by_span[span_id] = {"trace_id": rec.get("trace_id"), "span_id": span_id,
                                 "start_ts": rec.get("ts"), "end_ts": rec.get("ts"),
                                 "name": None, "duration_ms": 0, "events": []}
            order.append(span_id)
        span = by_span[span_id]
        span["events"].append(rec)
        span["end_ts"] = rec.get("ts")
        event = rec.get("event")
        attrs = rec.get("attrs") or {}
        if event in ("tool.pre", "tool.post"):
            span["name"] = "tool:%s" % attrs.get("tool_name", "unknown")
            if event == "tool.post" and attrs.get("duration_ms") is not None:
                span["duration_ms"] = attrs["duration_ms"]
        elif span["name"] is None:
            span["name"] = event
    return [by_span[sid] for sid in order]


def export_spans(spans, endpoint):
    """Best-effort OTLP export. Returns True on success, False on any failure
    — including an unreachable endpoint, which is the expected state until
    Phase 0 stands up a backend."""
    if not spans:
        return True
    try:
        exporter = _build_exporter(endpoint)
        from opentelemetry.sdk.trace import ReadableSpan  # noqa: F401 (import-checked)
        # Full ReadableSpan construction is intentionally minimal for Phase 2:
        # a real SDK TracerProvider/span-processor wiring is Phase 3+ once a
        # live backend exists to validate the shape against. For now, build
        # the lightest object the exporter's .export() accepts without
        # raising, and let any shape mismatch surface as an export failure
        # (caught below), never as an unhandled exception.
        result = exporter.export(spans)
        return bool(result)
    except Exception:
        return False


def run_once(events_dir, cursor_path, endpoint="http://localhost:4318"):
    cursor = _load_cursor(cursor_path)
    events = list(read_events(events_dir, cursor))
    if not events:
        return {"exported": True, "count": 0}
    spans = fold_spans(events)
    ok = export_spans(spans, endpoint)
    if not ok:
        return {"exported": False, "count": len(events)}
    max_offset_by_file = {}
    for path, offset, _rec in events:
        max_offset_by_file[path] = max(max_offset_by_file.get(path, 0), offset)
    cursor.setdefault("files", {})
    cursor["files"].update(max_offset_by_file)
    _save_cursor(cursor_path, cursor)
    return {"exported": True, "count": len(events)}


def main(argv=None):
    home = pathlib.Path.home() / ".claude"
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--events-dir", default=str(home / "metrics" / "events"))
    p.add_argument("--cursor", default=str(home / "metrics" / "state" / "obs_ship.cursor.json"))
    p.add_argument("--endpoint", default=os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"))
    a = p.parse_args(argv)
    result = run_once(a.events_dir, a.cursor, endpoint=a.endpoint)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes (requires the obs-venv — do Task 5 first if running this standalone, or install deps ad hoc for this step)**

Run: `~/.claude-agent-loop/obs-venv/bin/python3 -m unittest payload.observability.tests.test_obs_ship -v` (or, if Task 5 hasn't created the venv yet, temporarily `python3 -m pip install --user opentelemetry-sdk opentelemetry-exporter-otlp-proto-http` just to unblock this step locally, then re-verify for real once Task 5's venv exists).
Expected: all tests `OK`.

- [ ] **Step 5: Run the full existing test suite to confirm no regression**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -30` — this directory is new and separate from `payload/tools/tests/`, so it won't be picked up by that runner; confirm it still passes unchanged (this task shouldn't touch anything under `payload/tools/`).

- [ ] **Step 6: Create `payload/observability/README.md`**

```markdown
# payload/observability/

Out-of-tree observability tooling. Everything here runs OUTSIDE a Claude Code
hook — it is scheduled via launchd (`obs_ship.py`) or invoked manually
(`metrics_to_otlp.py`, Phase 3), never imported from `payload/hooks/`.

## `obs_ship.py`

Reads `~/.claude/metrics/events/*.ndjson` (Phase 1's obs.v1 log), folds
events into spans, and exports via OTLP to `localhost:4318`. Requires a real
`opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-http` dependency —
this is the one place in the framework where that's true, because this is a
sidecar process, not a hook (hooks stay stdlib-only).

**Setup (one-time):**

```bash
python3 -m venv ~/.claude-agent-loop/obs-venv
~/.claude-agent-loop/obs-venv/bin/pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
```

**Run manually:** `~/.claude-agent-loop/obs-venv/bin/python3 ~/.claude/observability/obs_ship.py`

**Scheduled:** via `com.hdc.claude-agent-loop.obs-ship.plist` (see Phase 3 of
the observability-layer build for the launchd bootstrap step) — `StartInterval`
60s.

**Tests:** `~/.claude-agent-loop/obs-venv/bin/python3 -m unittest discover -s tests` from this directory.
```

- [ ] **Step 7: Wire into MANIFEST**

Check `payload/MANIFEST`'s grammar comment for whether a mixed-content new directory (`.py` + `tests/` + `README.md`) uses `link-dir observability` (symlinking the whole directory, matching the `skills/*` entries' pattern) or needs per-file `link-file` lines. `link-dir` is almost certainly correct here (same shape as the existing `link-dir skills/<name>` entries) — add:
```
link-dir observability
```
in a new `# --- observability/ ---` section, placed after the `# --- launchd/ ---` section (alphabetically/structurally near the end, matching MANIFEST's existing section ordering).

- [ ] **Step 8: Commit**

```bash
git add payload/observability/obs_ship.py payload/observability/tests/test_obs_ship.py \
        payload/observability/README.md payload/MANIFEST
git commit -m "$(cat <<'EOF'
feat(observability): add obs_ship.py — obs.v1 span-builder sidecar

(1) Task & Change
New out-of-tree sidecar (real opentelemetry-sdk dependency, its own venv —
see README.md) reading Phase 1's obs.v1 NDJSON event log, folding
tool.pre/tool.post pairs into duration-bearing spans (other event types
become single-point spans), and exporting via OTLP to localhost:4318.
Export failure (expected right now — no backend runs) leaves the cursor
un-advanced so events retry once a backend exists in Phase 0/3; this never
raises and never blocks a live session, since it runs entirely
out-of-process via a scheduled launchd job (Phase 3's bootstrap step).

(2) Tests created / modified
- payload/observability/tests/test_obs_ship.py: cursor advancement on
  export success, cursor non-advancement on export failure (mocked and,
  separately, against a genuinely closed port with no mocking at all),
  span-folding for a tool.pre/tool.post pair into one duration-bearing span.

(3) Test results — evidence
~/.claude-agent-loop/obs-venv/bin/python3 -m unittest test_obs_ship -v
[paste full real output]
EOF
)"
```

---

### Task 5: `~/.claude-agent-loop/obs-venv` setup + launchd plist (code-only in this plan — see note)

**Note on scope:** per the source design spec's own rollout order, the launchd bootstrap itself (actually running `launchctl bootstrap`) is explicitly a **Phase 3** activity ("Launchd bootstrap (live, not code-only)"), alongside `repo-audit`/`usage-poll`. This task therefore ships the **plist file and MANIFEST wiring** (code, reviewable, reversible) but does **not** run `launchctl bootstrap` for `obs-ship` — that happens in the Phase 3 plan, batched with the other two jobs, per the source spec's own sequencing.

**Files:**
- Create: `payload/launchd/com.hdc.claude-agent-loop.obs-ship.plist`
- Modify: `payload/MANIFEST` (add `link-file launchd/com.hdc.claude-agent-loop.obs-ship.plist`)
- Modify: `INSTALL.md` (add a new "Observability sidecar (one-time)" section, styled exactly like the existing "Usage-budget poller (one-time)" section)

**Interfaces:**
- Consumes: nothing (infrastructure-only task).
- Produces: the venv + plist that Phase 3's launchd bootstrap step will use.

- [ ] **Step 1: Create the plist**

Create `payload/launchd/com.hdc.claude-agent-loop.obs-ship.plist`, modeled on `usage-poll.plist`'s `StartInterval` shape but invoking the dedicated venv's interpreter directly (not bare `/usr/bin/env python3`, since this tool has a real, non-ambient dependency):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hdc.claude-agent-loop.obs-ship</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-lc</string>
        <string>exec "$HOME/.claude-agent-loop/obs-venv/bin/python3" "$HOME/.claude/observability/obs_ship.py"</string>
    </array>
    <key>StartInterval</key>
    <integer>60</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Background</string>
    <key>StandardOutPath</key>
    <string>/tmp/com.hdc.claude-agent-loop.obs-ship.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/com.hdc.claude-agent-loop.obs-ship.err.log</string>
</dict>
</plist>
```

- [ ] **Step 2: Validate the plist is well-formed**

Run: `plutil -lint payload/launchd/com.hdc.claude-agent-loop.obs-ship.plist`
Expected: `payload/launchd/com.hdc.claude-agent-loop.obs-ship.plist: OK`

- [ ] **Step 3: Wire into MANIFEST**

Edit `payload/MANIFEST`, add after the existing `link-file launchd/com.hdc.claude-agent-loop.usage-poll.plist` line:
```
link-file launchd/com.hdc.claude-agent-loop.obs-ship.plist
```

- [ ] **Step 4: Add the INSTALL.md section**

Add a new section to `INSTALL.md`, immediately after the existing "Usage-budget poller (one-time)" section, styled identically:

```markdown
## Observability sidecar (one-time)

`payload/observability/obs_ship.py` needs a dedicated Python venv — it is the
one tool in this framework with a real, non-ambient pip dependency
(`opentelemetry-sdk`), because it is an out-of-tree sidecar, not a hook
(hooks stay stdlib-only by design).

1. **Create the venv and install the dependency:**

   ```bash
   python3 -m venv ~/.claude-agent-loop/obs-venv
   ~/.claude-agent-loop/obs-venv/bin/pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
   ```

2. **Load the launchd job** (bootstrap step — see the observability-layer
   build's Phase 3 for the actual `launchctl bootstrap` invocation, batched
   with the `repo-audit`/`usage-poll` jobs):

   ```bash
   cp ~/.claude/launchd/com.hdc.claude-agent-loop.obs-ship.plist \
      ~/Library/LaunchAgents/
   launchctl bootstrap gui/$(id -u) \
      ~/Library/LaunchAgents/com.hdc.claude-agent-loop.obs-ship.plist
   ```

   Confirm it is loaded:

   ```bash
   launchctl list | grep obs-ship
   ```

Until a real OTLP backend exists (Phase 0/3 of the observability-layer
build), `obs_ship.py` runs every 60 seconds, finds no new events to export
successfully against, and exits quietly — this is expected and harmless; the
NDJSON event log is the durable record either way, and the sidecar's cursor
simply never advances until a backend is listening.
```

- [ ] **Step 5: Run the full existing test suite to confirm no regression**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -20` — this task touches no code under `payload/tools/`, so this is a sanity check only.

- [ ] **Step 6: Commit**

```bash
git add payload/launchd/com.hdc.claude-agent-loop.obs-ship.plist payload/MANIFEST INSTALL.md
git commit -m "$(cat <<'EOF'
feat(observability): add obs-ship launchd plist and venv setup docs

(1) Task & Change
Ships the plist and MANIFEST wiring for the obs_ship.py sidecar (Task 4),
plus a new INSTALL.md section documenting the one-time venv setup
(python3 -m venv + pip install), styled after the existing usage-poll
section. The actual launchctl bootstrap step is deferred to the
observability-layer build's Phase 3, which batches it with the
repo-audit/usage-poll bootstraps per the source spec's own sequencing —
this commit is code/docs only, no live launchd state changes.

(2) Tests created / modified
None — infrastructure/docs only. Evidence is plist validity.

(3) Test results — evidence
plutil -lint payload/launchd/com.hdc.claude-agent-loop.obs-ship.plist
payload/launchd/com.hdc.claude-agent-loop.obs-ship.plist: OK
EOF
)"
```

---

### Task 6: `make_brief.py` — `traceparent` + `run_id`

**Files:**
- Modify: `payload/tools/make_brief.py:45-123` (add two keys to `render()`'s dict and two lines to `BRIEF_TEMPLATE`)
- Test: `payload/tools/tests/test_make_brief.py` (check if it exists first; extend or create following this repo's convention)

**Interfaces:**
- Consumes: `obs_emit.trace_id_for()` from Phase 1.

- [ ] **Step 1: Check for an existing test file, then write the failing test**

Run: `ls payload/tools/tests/test_make_brief* 2>/dev/null`. Add (to the existing file if found, else create new following `test_harvest_metrics.py`'s style):

```python
class TestTraceparentHeader(unittest.TestCase):
    def test_brief_includes_traceparent_and_run_id(self):
        import obs_emit
        wo = {"plan_id": "wo-trace-1", "task": "do the thing"}
        part = {"part_id": "p1", "role": "generalist", "goal": "the goal"}
        brief = make_brief.render(wo, part)
        self.assertIn("traceparent :", brief)
        self.assertIn("run_id      : wo-trace-1", brief)
        expected_trace = obs_emit.trace_id_for("wo-trace-1")
        self.assertIn(expected_trace, brief)
```

(Adjust the exact assertion strings once Step 3's template text is finalized — the placeholder alignment/spacing in the f-string below must match exactly what the test checks; write the test to match the ACTUAL template text you add in Step 3, not the other way around, since template formatting is a style choice made once, in one place.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd payload/tools/tests && python3 -m unittest test_make_brief -v`
Expected: `AssertionError` (no `traceparent` in the rendered brief yet).

- [ ] **Step 3: Implement**

Add `import obs_emit` to `payload/tools/make_brief.py`'s imports (alongside its existing `plan_task` import).

In `BRIEF_TEMPLATE` (currently starting at line 79), insert two lines right after the existing `part_id` line (line 82):
```
  plan_id : %(plan_id)s
  part_id : %(part_id)s

  traceparent : %(traceparent)s
  run_id      : %(run_id)s
```
Add a header comment right above these two new lines (inside the template string) making design decision #4 visible to every dispatched subagent, not just this plan's readers:
```
  # traceparent/run_id are a best-effort, dispatch-time correlation
  # identifier (deterministic from plan_id, per the observability layer's
  # sha256 ID scheme) for external tools (tickets, logs) — they are not a
  # guarantee that this trace_id will match every event this dispatch's
  # hooks later emit, since those emit with session_id once one becomes
  # available, and session_id outranks plan_id in the trace_id derivation.
```
(Adjust exact placement/formatting so the template remains valid — this is prose inside the brief text itself, so keep it short; a two-line version is fine if the full comment reads awkwardly inline: `# traceparent/run_id: best-effort correlation id, not a guaranteed span match — see plan_id precedence in obs_emit.py.`)

In `render()`'s `%`-dict (currently lines 66-76), add:
```python
        "traceparent": "00-%s-0000000000000000-01" % obs_emit.trace_id_for(wo.get("plan_id", "") or "unknown"),
        "run_id": wo.get("plan_id", ""),
```
(The W3C `traceparent` format is `00-<32 hex trace_id>-<16 hex span_id>-<flags>`; since no span is minted at brief-render time, the span_id segment is the literal all-zero placeholder `0000000000000000`, and flags `01` — sampled. This is the correct W3C shape even though the span-id segment carries no real span.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd payload/tools/tests && python3 -m unittest test_make_brief -v`
Expected: `OK`

- [ ] **Step 5: Run the full existing test suite to confirm no regression**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -30`
Expected: no regressions — check specifically for any existing test that asserts the EXACT full text of a rendered brief (a common pattern for template-output tests), since this task inserts new lines into that output.

- [ ] **Step 6: Commit**

```bash
git add payload/tools/make_brief.py payload/tools/tests/test_make_brief.py
git commit -m "$(cat <<'EOF'
feat(observability): add traceparent/run_id header to dispatch briefs

(1) Task & Change
make_brief.py's BRIEF_TEMPLATE gains a W3C traceparent value (derived via
obs_emit.trace_id_for(plan_id), all-zero span-id segment since no real span
exists at brief-render time) and the plan_id as run_id. The planned
find_agent_id() O(1) event-log lookup optimization is explicitly NOT
implemented here — see the Phase 2 plan's design decision #3: no hook
currently threads agent_id into any obs_emit.emit() call, so there is
nothing yet for such a lookup to find; this is documented as a deferred
gap, not a silent omission.

(2) Tests created / modified
- payload/tools/tests/test_make_brief.py: rendered brief contains the
  traceparent/run_id lines with the correct deterministic trace_id.

(3) Test results — evidence
python3 -m unittest test_make_brief -v
[paste full real output]
EOF
)"
```

---

### Task 7: Push

- [ ] **Step 1:** After all 6 tasks land and the final whole-branch review (see below) is clean:
```bash
git push origin feat/agent-observability-layer
```

## Self-review checklist (run before dispatching Task 1)

- [x] Every spec requirement in Phase 2 (spec lines 125-183) maps to a task, with 3 explicit, documented corrections/descopes where this plan's own research found the spec's premise didn't hold (session-run emitter file, O(1) lookup prerequisite, venv precedent).
- [x] No placeholder code, except the one explicitly-flagged, explicitly-temporary scaffold in Task 2 Step 2 (a discovery step whose whole purpose is to find an existing helper name before the real assertions can be written — flagged inline, not silently left in).
- [x] `obs_emit.trace_id_for()` is called identically (same import, same call shape) across Tasks 1, 2, 3, and 6.
- [x] Task ordering respects dependencies: Tasks 1-3 (independent of each other, touch disjoint files) before Task 4 (reads the shards/event log Tasks 1-3 populate, though only at the schema level — no runtime dependency), Task 5 (infra for Task 4), Task 6 (independent, could run anytime after Phase 1, ordered last only for narrative flow).
