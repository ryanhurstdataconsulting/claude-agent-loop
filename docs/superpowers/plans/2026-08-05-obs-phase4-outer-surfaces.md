# Agent Observability Layer — Phase 4: Outer Surfaces and Guardrails — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the observability layer past `claude-agent-loop` itself into three outer surfaces the source spec names: `audit_run.sh`'s own OTel/retry semantics, `HDC_Assistant`'s application-level span instrumentation, and a new SQL-preflight guardrail hook for `68_Challenge_Report`'s production-database access — plus file the one deliberately-not-implemented heuristic stub.

**Architecture:** Three separate repositories (`claude-agent-loop`, `HDC_Assistant`, `HDCx68Sports/68_Challenge_Report`), each getting one independent, self-contained change, plus one global registry-candidate file. No shared code between them — each task stands alone.

## Global Constraints

- **`audit_run.sh` currently carries ZERO live production risk right now.** Confirmed via this plan's own research: `~/.claude/metrics/audit/config.json` doesn't exist on this machine, so `audit_dispatch.py`'s nightly 03:17 fire raises an uncaught `ConfigError` before ever reaching `audit_run.sh` at all (a documented, deliberate state from Phase 3). Any change to `audit_run.sh` in this plan is therefore safe to make with normal engineering care — there is no live audit run today that could be disrupted mid-flight.
- **`HDC_Assistant` has an unrelated dirty working tree** (`src/hdc_assistant/memory/index.py`, `tests/test_index.py` modified, per this plan's own research) — pre-existing work-in-progress, not caused by this plan. Stage and commit ONLY the files this plan's task touches; never touch, stash, or commit the pre-existing dirty files.
- **`68_Challenge_Report`'s SQL-preflight hook warns, never blocks** — matching every other hook's fail-open, additive-only posture in this framework (an explicit source-spec requirement, not a design choice this plan is free to revisit).
- **The heuristic stub is filed, never auto-implemented.** Heuristic rule ids are owner-gated per this machine's own `HEURISTICS.md` convention — this plan files a candidate describing a future `H9`, and stops there.

## Design decisions locked in for this plan

1. **The source spec's "existing lost-run detector" doesn't map onto real code the way the spec implies.** This plan's research found TWO existing "lost run" concepts in `audit_run.sh`/`audit_dispatch.py`, and neither is "alert when the model produces bad findings": `_run_log_lost()` (audit_run.sh) fires only when the run-log JSON *file itself* can't be written to disk (a filesystem failure, unrelated to model output quality); `audit_dispatch.py`'s `collect_alerts()` "lost run" concept means "no run-log entry at all for tonight's sweep" (a scheduler-level gap, not a per-run model-quality signal). **Correction**: a model-produced failure (CLI exits 0, but no/bad findings) continues to go through the EXISTING `_fail_run()` path, which already calls `_notify()` — this plan does NOT invoke `_run_log_lost()` for that case, since doing so would be semantically wrong (that function's real meaning is "the log write failed," not "the model failed"). `_fail_run()`'s existing notification IS the "alert" the spec means; no new alerting is needed.
2. **No existing retry-supporting code structure exists in `audit_run.sh`.** The script's worktree lifecycle (setup → CLI run → gate/commit) is inline, straight-line script body under a single `trap _cleanup EXIT/INT/TERM`, not a callable function. This plan wraps that body into a single `_run_one_attempt()` function (returning a status the caller branches on), called up to twice from `main`-level script flow, with the EXIT trap tracking "the current worktree path" via a variable the function updates — rather than either a recursive self-invocation (which would need careful de-dup of side effects) or a larger rewrite.
3. **The "infrastructural failure" vs. "model-produced failure" distinction requires reordering the existing linear exit-code/findings checks.** Today, `_fail_run` on a non-zero CLI exit code short-circuits via `exit 1` before the `SECURITY_AUDIT.md` existence check ever runs — so the two failure classes can't currently be told apart. This plan's `_run_one_attempt()` checks for the findings file's existence *regardless* of `$CLI_RC` first, then classifies: **infrastructural** = non-zero exit code AND no findings file (the CLI itself broke — retry once) vs. **model-produced** = the findings file is genuinely missing/empty despite a zero exit code, OR a non-zero exit code that nonetheless left findings behind (rare, but real findings written is real findings written — never discard them by retrying over them) — never retried, alerts via `_fail_run`.
4. **`OTEL_RESOURCE_ATTRIBUTES`'s `parent.run=<dispatch-run-id>` is entirely new plumbing** — no run-id concept exists anywhere in `audit_run.sh`/`audit_dispatch.py` today. This plan adds a `--dispatch-run-id` optional CLI flag to `audit_run.sh` (defaulting to a value computed from the invocation's own PID+timestamp when absent, so a direct/manual invocation — not through `audit_dispatch.py` — still gets *some* stable-for-this-process value rather than an empty attribute) and threads it through both to the `OTEL_RESOURCE_ATTRIBUTES` env var and into `_emit_run_record`'s existing `trace_id_for("audit:%s:%s" % (pkg_key, now))` call unchanged (the run-id is for OTel linkage only — it does NOT change the Phase 3 `trace_id` formula, which already gets its own per-run uniqueness from the `now` timestamp).
5. **`HDC_Assistant`'s "the existing silent branch" framing doesn't match the code's current, already-fixed state.** This plan's research found `_single_agent_turn()` already raises a visible `RuntimeError` (not silence) on the `subtype=="success" and is_error=True` case, with a code comment explaining exactly why. The OTel work here is a genuine addition (mapping that already-raised exception onto a span's ERROR status, so it's visible in traces too, not just in Python-level exception handling/logs) — not a "fix" for a silence that no longer exists in the current codebase.

---

### Task 1: `payload/tools/audit_run.sh` — OTel passthrough + retry-once-on-infrastructural-failure

**Files:**
- Modify: `payload/tools/audit_run.sh`
- Modify: `payload/tools/audit_dispatch.py` (thread a dispatch-run-id into the subprocess call — see Step 4)
- Test: `payload/tools/tests/test_audit_run_retry.sh` (new — narrowly scoped, matching this repo's established convention of NOT writing a full 959-line-script integration suite from scratch)

**Interfaces:** None — self-contained shell + one small Python-side threading change.

- [ ] **Step 1: Re-derive exact current line numbers**

Run: `grep -n '_run_cli\|_fail_run\|_emit_run_record\|_run_log_lost\|_write_run_log_checked\|CLI_RC=\|SECURITY_AUDIT.md\|trap _cleanup' payload/tools/audit_run.sh` and read the surrounding context at each hit — this plan's own research quoted the key functions but line numbers may drift further by the time this task runs.

- [ ] **Step 2: Write the failing test**

Create `payload/tools/tests/test_audit_run_retry.sh`, narrowly scoped to the NEW classification/retry logic (not a full script integration test):

```bash
#!/bin/bash
# test_audit_run_retry.sh — the infrastructural-vs-model-produced failure
# classification helper in audit_run.sh. Scoped narrowly, matching this
# repo's established convention for this large script (see
# test_audit_run_kind_run.sh's own header note). macOS bash-3.2 portable.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
AUDIT_RUN="$(cd "$HERE/.." && pwd)/audit_run.sh"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Extract just the _classify_attempt function (a small, pure, side-effect-free
# helper this task adds) rather than sourcing the whole script.
awk '/^_classify_attempt\(\) \{/,/^\}/' "$AUDIT_RUN" > "$TMP/helper.sh"
if [ ! -s "$TMP/helper.sh" ]; then
  die "could not extract _classify_attempt — check the function exists with this exact name/shape"
else
  pass "extracted _classify_attempt"
fi
source "$TMP/helper.sh"

# _classify_attempt <cli_rc> <findings_file_exists: 0|1> -> prints classification, one of:
#   infrastructural | model-produced | ok

out="$(_classify_attempt 1 0)"
[ "$out" = "infrastructural" ] && pass "nonzero exit + no findings -> infrastructural" \
  || die "expected infrastructural, got: $out"

out="$(_classify_attempt 0 0)"
[ "$out" = "model-produced" ] && pass "zero exit + no findings -> model-produced" \
  || die "expected model-produced, got: $out"

out="$(_classify_attempt 1 1)"
[ "$out" = "model-produced" ] && pass "nonzero exit + findings DID land -> model-produced (never discard real findings)" \
  || die "expected model-produced, got: $out"

out="$(_classify_attempt 0 1)"
[ "$out" = "ok" ] && pass "zero exit + findings present -> ok" \
  || die "expected ok, got: $out"

if [ "$fail" -eq 0 ]; then
  echo "ALL PASS - test_audit_run_retry.sh"; exit 0
else
  echo "SOME FAILED - test_audit_run_retry.sh"; exit 1
fi
```

- [ ] **Step 3: Run test to verify it fails**

Run: `bash payload/tools/tests/test_audit_run_retry.sh`
Expected: fails at the `awk` extraction (`_classify_attempt` doesn't exist yet).

- [ ] **Step 4: Implement**

Add `_classify_attempt` to `audit_run.sh` (a small, pure function — no side effects, testable in isolation):

```bash
# _classify_attempt <cli_rc> <findings_file_exists: 0|1>
# Prints exactly one of: infrastructural | model-produced | ok
_classify_attempt() {
  local rc="$1" findings_exist="$2"
  if [ "$findings_exist" = "1" ]; then
    if [ "$rc" = "0" ]; then
      echo "ok"
    else
      echo "model-produced"   # findings landed despite a nonzero exit — never discard them
    fi
    return 0
  fi
  if [ "$rc" != "0" ]; then
    echo "infrastructural"    # the CLI itself broke, nothing was produced
  else
    echo "model-produced"     # CLI reported success but wrote nothing
  fi
}
```

Add a `--dispatch-run-id` CLI flag (defaulting to `"$(date +%s)-$$"` when not passed) parsed alongside this script's existing argument parsing (find the existing `getopts`/positional-arg parsing block and add this flag there, following its existing style).

Restructure the worktree-setup → CLI-run → gate/commit body into `_run_one_attempt()`, called from the main flow up to twice:
- First call: normal flow, exactly as today, but ending in a call to `_classify_attempt "$CLI_RC" "$([ -f "$AUDIT_FILE" ] && echo 1 || echo 0)"` instead of the current linear `if [ "$CLI_RC" -ne 0 ]; then _fail_run ...; fi` / `[ -f "$AUDIT_FILE" ] || _fail_run ...` pair.
- If the classification is `infrastructural` AND this is the first attempt: clean up the current worktree, log a retry notice, call `_run_one_attempt()` a second time in a fresh worktree.
- If the classification is `infrastructural` on the SECOND attempt, or `model-produced` on any attempt: call `_fail_run` with a message identifying which classification triggered it (e.g. `_fail_run "infrastructural failure, retried once, still failing: $(tail -1 "$CLI_ERR")"` or `_fail_run "model produced no usable findings: $AUDIT_FILE missing or empty"`).
- If `ok`: proceed to the existing success path unchanged.
- Every `_emit_run_record` call site gets a `stop_reason` reflecting which path was taken: the existing `"error"`/`"timeout"`/`"completed"` logic from Phase 2 stays, but ensure a retried-then-succeeded run's `stop_reason` is `"completed"` (the retry is invisible in the final `outcome`, only visible via the log's retry-notice line) and a retried-then-still-failed run's `stop_reason` reflects the SECOND attempt's own CLI_RC (matching the existing `== 124` → `"timeout"` else `"error"` logic already in `_emit_run_record`).

Thread the OTel env vars onto `_run_cli`'s invocation (the exact call site found in Step 1):
```bash
OTEL_RESOURCE_ATTRIBUTES="service.name=claude-code,deployment.environment=hdc-local,audit.package=${PKG_KEY},parent.run=${DISPATCH_RUN_ID}" \
  _run_cli "$@" >"$CLI_OUT" 2>"$CLI_ERR" &
```
(Reuse the OTHER OTel env vars — `CLAUDE_CODE_ENABLE_TELEMETRY`, `OTEL_METRICS_EXPORTER`, etc. — from the calling environment; Phase 0 already set these globally in `~/.claude/settings.json`, so the subprocess inherits them automatically without needing to be re-set here. Only `OTEL_RESOURCE_ATTRIBUTES` needs a per-invocation override, since the global one lacks `audit.package`/`parent.run`.)

Thread `--dispatch-run-id` from `payload/tools/audit_dispatch.py`'s `run_package()` (the call site found in Step 1's research, currently `["bash", runner, path, root, "--key", package]`) by adding a computed run-id (e.g. `"night-%s-%s" % (today_date_string, package)`) to that argument list.

- [ ] **Step 5: Run test to verify it passes**

Run: `bash payload/tools/tests/test_audit_run_retry.sh`
Expected: `ALL PASS - test_audit_run_retry.sh`

- [ ] **Step 6: Run the full existing test suite AND a syntax check**

Run: `bash payload/tools/tests/run_all.sh 2>&1 | tail -30` and `bash -n payload/tools/audit_run.sh` (syntax check — per this repo's established convention, this script is too large/side-effecting to execute end-to-end in a task; confirm the existing `test_audit_run_kind_run.sh` suite, which extracts and tests `_emit_run_record` in isolation, still passes unmodified since this task doesn't touch that function's own body).

- [ ] **Step 7: Commit**

```bash
git add payload/tools/audit_run.sh payload/tools/audit_dispatch.py payload/tools/tests/test_audit_run_retry.sh
git commit -m "$(cat <<'EOF'
feat(observability): OTel passthrough + retry-once for audit_run.sh

(1) Task & Change
Adds OTEL_RESOURCE_ATTRIBUTES (audit.package/parent.run) to the claude CLI
subprocess invocation, native OTel export happens inside that subprocess
using the globally-configured env vars from Phase 0. Adds
_classify_attempt(), a pure function distinguishing infrastructural
failure (CLI broke, nothing produced — retry once in a fresh worktree)
from model-produced failure (findings missing/empty despite a clean exit,
or present despite a dirty one — never discard real findings by
retrying over them — alert via the existing _fail_run/_notify path, not
_run_log_lost, which is a different, narrower concept: see this plan's
design decision 1). A --dispatch-run-id flag threads parent/child linkage
from audit_dispatch.py's nightly sweep.

(2) Tests created / modified
- payload/tools/tests/test_audit_run_retry.sh: all 4 classification
  branches of _classify_attempt, extracted and tested in isolation.

(3) Test results — evidence
bash payload/tools/tests/test_audit_run_retry.sh
ALL PASS - test_audit_run_retry.sh
bash -n payload/tools/audit_run.sh (syntax check, no output = pass)
Full suite: bash payload/tools/tests/run_all.sh — no regressions.
EOF
)"
```

- [ ] **Step 8: Push**

```bash
git push origin feat/agent-observability-layer
```

---

### Task 2: `HDC_Assistant` — span instrumentation for `run_agent_turn_async()`

**Repo:** `/Users/ryanhurst/dev/HurstDataConsultingLLC/HDC_Assistant` (separate repo, separate commit, own remote if any — check before pushing).

**Files:**
- Modify: `pyproject.toml` (add `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http`, matching claude-agent-loop's Phase 2 dependency choice, since this is real application code — not a hook — so a real dependency is fine here, per the source spec's own explicit carve-out)
- Modify: `src/hdc_assistant/agent/core.py`
- Modify: `tests/test_agent_core.py`

**Interfaces:** None — self-contained within this repo.

**Prerequisite check**: confirm this repo's git working tree's pre-existing dirty files (`src/hdc_assistant/memory/index.py`, `tests/test_index.py`) are STILL the only dirty files before starting (`git status --short`) — if something else has changed since this plan's research, stop and report NEEDS_CONTEXT rather than committing over unrelated work-in-progress.

- [ ] **Step 1: Add the dependency**

Add to `pyproject.toml`'s `dependencies` list: `"opentelemetry-sdk"`, `"opentelemetry-exporter-otlp-proto-http"`. Install: `pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http` (or via whatever this project's own dependency-install convention is — check for a Makefile/README install step first).

- [ ] **Step 2: Write the failing test**

Add to `tests/test_agent_core.py`, following the file's existing `pytest` + `AsyncMock`/`patch.object` convention exactly (read the two existing retry tests quoted in this plan's research first, match their exact idiom):

```python
@pytest.mark.asyncio
async def test_run_agent_turn_async_creates_one_span_per_turn():
    from hdc_assistant.agent import core
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    with (
        patch.object(core, "_tracer_provider", provider),
        patch.object(core, "_single_agent_turn", AsyncMock(return_value="ok")),
    ):
        result = await core.run_agent_turn_async("hello")

    assert result == "ok"
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "agent_turn"
    assert spans[0].status.status_code.name == "OK"


@pytest.mark.asyncio
async def test_run_agent_turn_async_creates_child_span_per_retry_attempt():
    from hdc_assistant.agent import core
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    with (
        patch.object(core, "_tracer_provider", provider),
        patch.object(
            core, "_single_agent_turn", AsyncMock(side_effect=[RuntimeError("boom"), "ok"])
        ),
        patch.object(core.asyncio, "sleep", AsyncMock()),
    ):
        result = await core.run_agent_turn_async("hello")

    assert result == "ok"
    spans = exporter.get_finished_spans()
    # one root "agent_turn" span + one child "attempt" span per attempt (2 attempts: fail, succeed)
    names = sorted(s.name for s in spans)
    assert names.count("attempt") == 2
    assert "agent_turn" in names
    attempt_spans = [s for s in spans if s.name == "attempt"]
    error_span = next(s for s in attempt_spans if s.status.status_code.name == "ERROR")
    ok_span = next(s for s in attempt_spans if s.status.status_code.name == "OK")
    assert error_span is not None and ok_span is not None


@pytest.mark.asyncio
async def test_success_with_is_error_true_sets_error_span_status_not_just_a_raise():
    from hdc_assistant.agent import core
    from claude_agent_sdk import ResultMessage
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    async def fake_query(prompt, options):
        yield ResultMessage(subtype="success", is_error=True, result=None,
                             errors=["boom"], api_error_status=500)

    with (
        patch.object(core, "_tracer_provider", provider),
        patch.object(core, "query", fake_query),
        patch.object(core.asyncio, "sleep", AsyncMock()),
        pytest.raises(RuntimeError),
    ):
        await core.run_agent_turn_async("hello", retries=0)

    spans = exporter.get_finished_spans()
    attempt_span = next(s for s in spans if s.name == "attempt")
    assert attempt_span.status.status_code.name == "ERROR"
```

**Note to implementer**: the exact `ResultMessage` constructor signature/fields in the third test are illustrative — check `claude_agent_sdk`'s actual `ResultMessage` definition first (it may not accept all these kwargs, or may need different ones) and adjust the fixture to construct a real, valid instance rather than guessing. If `ResultMessage` is hard to construct directly, mock `_single_agent_turn` itself to raise the exact `RuntimeError` `_single_agent_turn` already raises in that case (matching the OTHER two tests' `AsyncMock(side_effect=...)` pattern) rather than needing a real `ResultMessage` — that tests the same span-status behavior with less fixture fragility.

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_agent_core.py -v` (or however this project runs its test suite — check for a Makefile/README command first)
Expected: fails — `core` has no `_tracer_provider` attribute yet, spans aren't created.

- [ ] **Step 4: Implement**

Add near the top of `src/hdc_assistant/agent/core.py` (after the existing imports):
```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_tracer_provider = TracerProvider(
    resource=Resource.create({"service.name": "hdc-assistant"})
)
_tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces"))
)
_tracer = _tracer_provider.get_tracer("hdc_assistant.agent.core")
```
(Module-level `_tracer_provider`/`_tracer` matches this file's existing module-level `logger` pattern; tests patch `_tracer_provider` directly, per Step 2's tests, to swap in an in-memory exporter — verify this patching approach actually works given how `_tracer` is derived from `_tracer_provider` at import time; if patching `_tracer_provider` after import doesn't retroactively affect an already-created `_tracer`, the tests/implementation need to call `trace.get_tracer(...)` fresh inside `run_agent_turn_async`/`_single_agent_turn` each time rather than caching `_tracer` at module level — verify this empirically rather than assuming either shape works.)

Wrap `run_agent_turn_async()` in a root span, and each attempt in a child span:
```python
async def run_agent_turn_async(prompt: str, retries: int = 1, backoff_seconds: float = 2.0) -> str:
    """Run one agent turn, retrying once with backoff on any exception.

    Call this from async code (e.g. a python-telegram-bot handler) — it runs
    inside the caller's existing event loop rather than starting a new one.
    """
    with _tracer.start_as_current_span("agent_turn") as turn_span:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            with _tracer.start_as_current_span("attempt") as attempt_span:
                attempt_span.set_attribute("attempt_number", attempt + 1)
                try:
                    result = await _single_agent_turn(prompt)
                    attempt_span.set_status(trace.StatusCode.OK)
                    turn_span.set_status(trace.StatusCode.OK)
                    return result
                except Exception as e:
                    attempt_span.set_status(trace.StatusCode.ERROR, str(e))
                    attempt_span.record_exception(e)
                    last_error = e
                    logger.warning("Agent turn failed (attempt %d/%d): %s", attempt + 1, retries + 1, e)
                    if attempt < retries:
                        await asyncio.sleep(backoff_seconds)
        turn_span.set_status(trace.StatusCode.ERROR, str(last_error))
        raise last_error
```
(Confirm the exact `set_status` call signature against the installed SDK version — some versions want `Status(StatusCode.ERROR, description)` as an object rather than positional args; verify empirically per this plan's established pattern for any OTel SDK usage, don't assume.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_agent_core.py -v`
Expected: all pass, including the pre-existing 2 retry tests (confirm no regression — the span wrapping must not change `run_agent_turn_async`'s return value or exception-raising behavior on any path, only add spans around it).

- [ ] **Step 6: Run the FULL existing test suite for this repo**

Run whatever this repo's full test command is (check README/Makefile — likely `pytest` from the repo root) — confirm no regressions anywhere else, and confirm the pre-existing dirty files (`memory/index.py`, `test_index.py`) are unaffected by anything in this task.

- [ ] **Step 7: Commit — ONLY the files this task touched**

```bash
cd /Users/ryanhurst/dev/HurstDataConsultingLLC/HDC_Assistant
git add pyproject.toml src/hdc_assistant/agent/core.py tests/test_agent_core.py
git commit -m "$(cat <<'EOF'
feat(observability): instrument run_agent_turn_async with OTel spans

(1) Task & Change
Part of the claude-agent-loop agent-observability-layer build's Phase 4
(see docs/superpowers/specs/2026-08-05-agent-observability-layer-design.md
in that repo). Wraps run_agent_turn_async in a root "agent_turn" span with
one child "attempt" span per retry attempt, exporting to the same
localhost:4318 OTLP endpoint every phase of that build standardizes on.
The "success but is_error=True" edge case already raises a visible
RuntimeError (not silent, contrary to the source spec's framing of a
"silent branch" — that's stale relative to this file's current state);
this change adds the corresponding ERROR span status so it's visible in
traces too, not just in Python-level exception handling.

(2) Tests created / modified
- tests/test_agent_core.py: one span per successful turn, one child span
  per retry attempt with correct OK/ERROR status each, the is_error=True
  case setting an ERROR span status.

(3) Test results — evidence
pytest tests/test_agent_core.py -v
[paste full real output]
EOF
)"
```

- [ ] **Step 8: Push** (only if this repo has a configured remote — check `git remote -v` first; if none, state that in the report and skip)

---

### Task 3: `68_Challenge_Report` — SQL-preflight guardrail hook

**Repo:** `/Users/ryanhurst/dev/HurstDataConsultingLLC/HDCx68Sports/68_Challenge_Report`

**Files:**
- Modify: `.claude/settings.local.json` (add the first `hooks` key this file has ever had)
- Create: `.claude/hooks/sql-preflight.sh` (or wherever this project's convention puts a project-local hook script — check if `.claude/hooks/` already exists as a directory pattern anywhere in this workspace before inventing a new location)
- Create: `docs/sql_examples/readonly_query_example.sql` (or an equivalent tracked location — the "one tracked example query file" the source spec requires)

**Interfaces:** None.

- [ ] **Step 1: Confirm the hook-script location convention**

Check whether any OTHER project under `HDCx68Sports/` already has a `.claude/hooks/` directory with a project-local hook script (as opposed to referencing a global `~/.claude/hooks/` script) — this determines whether to create a new directory pattern or follow an existing one. If none exists anywhere in this workspace, `.claude/hooks/sql-preflight.sh` (relative to the `68_Challenge_Report` project root) is a reasonable, discoverable default.

- [ ] **Step 2: Write the hook script**

Create `68_Challenge_Report/.claude/hooks/sql-preflight.sh`, mirroring this framework's own hook conventions (bash wrapper → python heredoc, defensive JSON parsing, always exits 0, warns via `additionalContext` never blocks):

```bash
#!/bin/bash
# sql-preflight.sh — PreToolUse(Bash) guardrail for queries touching
# sports68db. Mirrors the sql-safety-reviewer agent's static checks
# (read-only transaction wrapper, statement timeout, no DDL/DML) but
# WARNS via additionalContext — never blocks — matching this framework's
# fail-open, additive-only posture for every other hook. Only fires when
# the Bash command looks like it touches psql/sports68db/the bastion
# tunnel; every other Bash command is untouched.
set -u

INPUT="$(cat 2>/dev/null || true)"

SQL_PREFLIGHT_INPUT="$INPUT" python3 <<'PY' || true
import json
import os
import re
import sys

try:
    raw = os.environ.get("SQL_PREFLIGHT_INPUT", "")
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}

tool_input = data.get("tool_input")
if not isinstance(tool_input, dict):
    tool_input = {}
command = str(tool_input.get("command") or "")

TRIGGER_RE = re.compile(r"psql|sports68db|bastion\.newprod\.6-8sports\.com", re.IGNORECASE)
if not TRIGGER_RE.search(command):
    sys.stdout.flush()
    os._exit(0)

DDL_DML_RE = re.compile(
    r"\b(CREATE|ALTER|DROP|TRUNCATE|RENAME|COMMENT|GRANT|REVOKE|"
    r"INSERT|UPDATE|DELETE|MERGE|COPY\s+\w+\s+FROM)\b",
    re.IGNORECASE,
)
has_readonly = re.search(r"SET\s+TRANSACTION\s+READ\s+ONLY", command, re.IGNORECASE)
has_timeout = re.search(r"SET\s+statement_timeout\s*=\s*\d+", command, re.IGNORECASE)
has_ddl_dml = DDL_DML_RE.search(command)

warnings = []
if not has_readonly:
    warnings.append("no 'SET TRANSACTION READ ONLY' found")
if not has_timeout:
    warnings.append("no 'SET statement_timeout = ...' found")
if has_ddl_dml:
    warnings.append("possible DDL/DML keyword detected: %s" % has_ddl_dml.group(0))

if warnings:
    context = (
        "sql-preflight: this command touches sports68db and is missing safety "
        "guards the sql-safety-reviewer agent checks for: %s. See "
        "docs/sql_examples/readonly_query_example.sql for the expected pattern. "
        "This is a warning only — it does not block the command."
        % "; ".join(warnings)
    )
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": context,
        }
    }))

sys.stdout.flush()
os._exit(0)
PY

exit 0
```

- [ ] **Step 3: Write the tracked example query file**

Create `68_Challenge_Report/docs/sql_examples/readonly_query_example.sql`, reusing the REAL, already-in-use pattern from `src/ct_report/db/connection.py`'s `readonly_connection()` (found in this plan's own research — don't invent new syntax):

```sql
-- readonly_query_example.sql — the expected read-only-transaction + timeout
-- pattern for any manual query against sports68db, matching what
-- src/ct_report/db/connection.py's readonly_connection() already applies
-- automatically for every connection made through this project's own
-- Python helpers. Copy this preamble verbatim for any ad-hoc psql session.

SET TRANSACTION READ ONLY;
SET statement_timeout = 30000;  -- 30s, matches connection.py's STATEMENT_TIMEOUT_MS default

-- Example: count athletes by country (adjust WHERE/columns as needed).
SELECT country, count(*) AS athlete_count
FROM athlete_athlete
GROUP BY country
ORDER BY athlete_count DESC
LIMIT 20;
```

- [ ] **Step 4: Wire the hook into `.claude/settings.local.json`**

Add the FIRST `hooks` key this file has ever had (confirm via Step 1's research that it's genuinely absent before adding, don't overwrite an unexpected existing key):
```json
"hooks": {
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/sql-preflight.sh"
        }
      ]
    }
  ]
}
```
(Verify `$CLAUDE_PROJECT_DIR` is the correct variable for a project-relative hook path in this framework's hook-binding convention — check an existing project-local hook binding elsewhere in this workspace for the exact variable name Claude Code substitutes, if one exists; if none exists as precedent, use whatever mechanism Claude Code's own hook documentation specifies for a project-relative path.)

- [ ] **Step 5: Manually test the hook**

```bash
chmod +x .claude/hooks/sql-preflight.sh
echo '{"tool_input":{"command":"psql -h bastion.newprod.6-8sports.com -c \"SELECT * FROM athlete_athlete\""}}' | bash .claude/hooks/sql-preflight.sh
```
Expected: a JSON output with `additionalContext` warning about missing read-only/timeout guards (this example query has neither).

```bash
echo '{"tool_input":{"command":"psql -c \"SET TRANSACTION READ ONLY; SET statement_timeout = 30000; SELECT 1\""}}' | bash .claude/hooks/sql-preflight.sh
```
Expected: empty output (no warnings — this one has both guards).

```bash
echo '{"tool_input":{"command":"ls -la"}}' | bash .claude/hooks/sql-preflight.sh
```
Expected: empty output (doesn't match the trigger pattern at all).

- [ ] **Step 6: Commit**

```bash
cd /Users/ryanhurst/dev/HurstDataConsultingLLC/HDCx68Sports/68_Challenge_Report
git add .claude/hooks/sql-preflight.sh .claude/settings.local.json docs/sql_examples/readonly_query_example.sql
git commit -m "$(cat <<'EOF'
feat(observability): add SQL-preflight guardrail hook

(1) Task & Change
Part of the claude-agent-loop agent-observability-layer build's Phase 4.
New PreToolUse(Bash) hook warning (never blocking, matching every other
hook's fail-open posture) when a command touching psql/sports68db/the
bastion tunnel is missing the read-only-transaction + statement-timeout
guards the sql-safety-reviewer agent checks for, or contains a DDL/DML
keyword. Ships one tracked example query file reusing the exact pattern
already validated in src/ct_report/db/connection.py's
readonly_connection().

(2) Tests created / modified
Manual verification (3 cases: missing-guards warns, guards-present is
silent, non-matching command is silent) — see report for exact commands
and output; no automated test harness exists in this project yet for
hook scripts.

(3) Test results — evidence
[paste the 3 manual test commands and their real output]
EOF
)"
```

- [ ] **Step 7: Push** (only if this repo has a configured remote — check first)

---

### Task 4: File the hook-health heuristic candidate stub

**Files:**
- Create: `~/.claude/registry/candidates/2026-08-05-hook-health-heuristic.md`

**Interfaces:** None — this is a proposal document, never auto-implemented. Heuristic rule ids are owner-gated.

- [ ] **Step 1: Confirm `H9` is genuinely unused**

Run: `grep -n '^## H' ~/.claude/learning/HEURISTICS.md` — confirm the highest existing id (this plan's own research found H8 as the highest; re-confirm at implementation time in case something changed).

- [ ] **Step 2: Write the candidate**

Create `~/.claude/registry/candidates/2026-08-05-hook-health-heuristic.md`, following the candidates README's prescribed template (Status: candidate + `## Evidence` section) rather than the one example this plan's research found that predates/doesn't-follow that template exactly:

```markdown
# Candidate: H9 — hook-health heuristic

**Status:** candidate
**Filed:** 2026-08-05, as part of the agent-observability-layer build's
Phase 4 (see the design spec and Phase 4 plan in `claude-agent-loop`'s
`docs/superpowers/specs/` and `docs/superpowers/plans/`).

## What H9 would flag

A rule watching `hook.error` event counts (from the obs.v1 structured
event log Phase 1 of the observability-layer build added — see
`payload/tools/obs_emit.py` in `claude-agent-loop`) plus per-hook
heartbeat age, to detect a wired hook that has gone silent — no
`tool.pre`/`tool.post`/`gate.decision`/`skill.invoked` events from a
specific hook script for N sessions, or a `hook.error` count above a
threshold for one specific hook — as a signal distinct from the hook
simply never having a reason to fire (e.g. `read-guard.sh` only fires on
`Read` tool calls; silence there could be innocent).

## Why this is filed as a candidate, not implemented

Heuristic rule ids in this framework are owner-gated
(`~/.claude/learning/HEURISTICS.md`'s own convention, enforced by
`lint_heuristics.py`) — a new rule id is an owner code change, never an
autocommit. This build's Phase 1 shipped the event log H9 would consume;
Phase 4 explicitly stops short of writing the evaluator itself.

## Evidence

The observability-layer design spec (source doc §2 architecture review)
named "invisible hook health" as one of the gaps motivating this entire
build — no dashboards/alerts exist today for a hook that silently stops
firing. Phase 1's `hook.error` trap (added to all 13 hook scripts across
`claude-agent-loop` and the local-only `~/.claude/hooks/` files) and
Phase 3's alerts-as-code (`payload/observability/alerts/hook-silent.yaml`
in `claude-agent-loop`, covering the 4 hooks with a genuine positive
per-invocation signal) already give this rule real data to evaluate
against — H9 would be the metrics-engine-side counterpart to that
alerts-as-code file, running inside `heuristics_eval.py` against the same
signal an eventual Grafana alert would also read, so a violation surfaces
in-session (via the loop) even before any backend/dashboard exists to
show it visually.

## What's needed to act on this

An owner decision on: the exact threshold (how many sessions of silence,
or what `hook.error` count, trips the rule), which of the 13 hooks get a
DEFAULT threshold vs. an override (mirroring `hook-silent.yaml`'s own
4-of-11 scoping decision — most hooks don't have a reliable positive
signal to measure "silence" against), and whether this becomes its own
new rule id (H9) or folds into an existing rule's threshold tuning.
```

- [ ] **Step 3: Lint the registry**

Run: `python3 ~/.claude/tools/lint_registry.py`
Expected: `lint_registry: OK (0 error(s))` — confirm adding this candidate file doesn't trip any registry-wide lint (candidates are typically outside the lint's scope, but confirm rather than assume).

- [ ] **Step 4: Surface it to the user**

This file is not committed through `loop_autocommit.sh` (candidates are filed directly, not auto-committed) and there's no repo to `git add` it into — `~/.claude/registry/candidates/` is part of the `~/.claude` local git repo (the same one Phase 1's Task 6 committed into). Commit it there:
```bash
cd ~/.claude
git add registry/candidates/2026-08-05-hook-health-heuristic.md
git commit -m "$(cat <<'EOF'
docs(registry): file H9 hook-health heuristic candidate

(1) Task & Change
Part of the claude-agent-loop agent-observability-layer build's Phase 4.
Proposes a future heuristic rule watching hook.error counts and
per-hook heartbeat age from Phase 1's obs.v1 event log, to detect a
wired hook that's gone silent. Filed as a candidate per this framework's
own owner-gating convention for new heuristic rule ids — not
implemented.

(2) Tests created / modified
None — a proposal document.

(3) Test results — evidence
python3 ~/.claude/tools/lint_registry.py
lint_registry: OK (0 error(s))
EOF
)"
```
(No push — this repo has no remote, per Phase 1's own established finding.)

## Self-review checklist

- [x] Every spec requirement in Phase 4 (source spec lines 241-276) maps to a task, with 2 documented corrections where this plan's own research found the spec's framing didn't match real code (design decision 1's lost-run-detector mismatch, design decision 5's already-fixed "silent branch").
- [x] No fabricated retry/OTel behavior — `audit_run.sh`'s new retry structure is built as a genuinely new, pure, independently-testable function rather than a hand-waved "add a retry loop somewhere."
- [x] Cross-repo commit boundaries are explicit: Task 1 in `claude-agent-loop`, Task 2 in `HDC_Assistant`, Task 3 in `HDCx68Sports/68_Challenge_Report`, Task 4 in `~/.claude`.
- [x] `HDC_Assistant`'s pre-existing dirty working tree is explicitly called out as untouchable scope.
