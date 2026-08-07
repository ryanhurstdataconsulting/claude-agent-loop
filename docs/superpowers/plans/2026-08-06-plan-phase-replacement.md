# PLAN-Phase Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the DECOMPOSE/ASSIGN/BRIEF/LOG/ASSESS work-order pipeline with a single PLAN artifact and CLI, folding BRIEF into decomposition and ASSESS into SCORE, with the creativity gate removed entirely.

**Architecture:** One JSON **plan** per task at `~/.claude/plans/<YYYY-MM-DD>/<task_id>.json`, date-partitioned by parsing the date out of `task_id` itself (no directory scan needed to find a plan by id). `plan_task.py` owns creation, assignment, and brief rendering in one pass (folding in what `make_brief.py` used to do), plus recording each step's structured return. `score_task.py` gains the objective evidence/verdict computation `assess_task.py` used to own, exposed both as a reusable function (for `loop_close.py`'s unattended SessionEnd path) and a `--auto` CLI mode. `make_brief.py` and `assess_task.py` are deleted. `workorder-gate.sh` (the creativity-gate hook) is deleted outright — PLAN becomes agent-judgment-driven, documented in the resource-loop skill, with no keyword-scored backstop.

**Tech Stack:** Python 3 stdlib only. `unittest` via `cd payload/tools/tests && python3 -m unittest <module> -v` (or `./run_all.sh` for the full suite). macOS bash 3.2 portable for hook scripts.

## Global Constraints

- Python 3 stdlib only — no third-party imports in any tool or test.
- Every tool exits 0 on success and non-zero with a stated reason on failure. These tools are invoked deliberately, never from a hook, so they do **not** fail open.
- Plan schema version is `2`. A file with any other `schema` value is rejected, not migrated (the migration script in Task 9 is the one place schema-1 input is read).
- Hook and `settings.json` changes (Tasks 6, 8) go through a normal `git commit`, never `loop_autocommit.sh` — that tool's Gate 0 restriction on `settings*.json`/`hooks/` exists to stop the autonomous LEARN loop from self-editing those paths, not to bar this user-directed engineering work.
- Every new or removed tool gets its `link-file tools/<name>` line added to or removed from `payload/MANIFEST`.
- Grammar gate (`python3 ~/.claude/tools/prose_grammar_gate.py`) must pass on every markdown file touched.
- Commit bodies use the three-section (1) Task & Change / (2) Tests created or modified / (3) Test results — evidence format.
- Reference spec: `docs/superpowers/specs/2026-08-06-agent-loop-v2-design.md`, Phase 1.

---

### Task 1: `plan_task.py` — new schema, decompose+assign+brief in one pass, no creativity gate

**Files:**
- Modify: `payload/tools/plan_task.py`
- Modify: `payload/tools/tests/test_plan_task.py`

**Interfaces:**
- Consumes: `route_role.load_roles(roles_dir)` → `dict`, `route_role.route(task, roles)` → `{"role": str, "score": int, "skills": list}` (unchanged, from `route_role.py`).
- Produces: `plan_id(task, created)` → `str` (unchanged logic); `create(task, source, plan_doc, project, branch, roles_dir, goals=None, created=None)` → `dict` (a full plan, already assigned and briefed); `load(base_dir, task_id)` → `dict`; `save(base_dir, plan)` → `None`; `render_brief(plan, step)` → `str`.

**Schema change (schema 1 → 2), field-by-field:**

| Old (`parts[]`, schema 1) | New (`steps[]`, schema 2) | Note |
|---|---|---|
| `plan_id` (top-level) | `task_id` | same generator, same format `wo-<YYYYMMDD>-<slug>-<hash6>` |
| `task` (top-level) | `task` | unchanged |
| — | `supervisor_reasoning` (top-level) | new, optional, plain string from `--reasoning`, defaults to `""` — no model call happens inside this tool |
| `part_id` | `id` | unchanged values (`p1`, `p2`, …) |
| `role` | `agent` | same values (`generalist`, `dba`, …) |
| `role_score` | `agent_score` | unchanged |
| `skills`, `model`, `agent_task_id` | same names | unchanged |
| — | `depends_on` | new, `[]` for every step in this task (no DAG construction yet — `--from-plan` still creates one step per heading, in document order, with no dependency inference) |
| — | `budget_tokens` | new, `None` unless `--budget-tokens N` passed at the CLI (applies to every step in the call) |
| — | `worktree` | new, `False` unless `--worktree` passed at the CLI |
| — | `brief` | new — the full dispatch prompt, rendered at creation/assignment time (Step 3 below) |
| `status` | `status` | values become `pending` / `done` / `failed` — the old `assigned` value is dropped, since assignment and brief rendering now happen synchronously inside `create()`, not as a separate stage a caller waits on |
| `log` | `return` | unchanged shape (the subagent's structured JSON) |
| `evidence` + `verdict` | `assessment` | now one object: `{"evidence": {...}, "verdict": "..."}` or `None`, written by `score_task.py` (Task 3) |
| `score` | *(removed)* | was always `null` in every real plan file inspected; the subjective self-score already lives in the metrics `kind:"score"` record keyed by `task_id`, which is where `score_task.py` has always written it — this field was dead weight |

`--force` and `--classify` are removed. `MIN_CREATIVE`, `CREATIVE_STRONG`, `CREATIVE_WEAK`, `creative_score()`, `is_creative()`, `CreativeTaskRefused`, `_refusal_message()` are all deleted — `create()` never refuses a task.

- [ ] **Step 1: Write the failing tests**

```python
# In test_plan_task.py, replace the TestPlanId / TestCreativeGate classes and
# update TestCreate (existing fixtures for role dirs are reused unchanged —
# see the file's existing ROLE_DATA_ENGINEER fixture and _tmp_roles() helper).

class TestPlanId(unittest.TestCase):
    def test_deterministic_for_same_inputs(self):
        a = pt.plan_id("rebuild the dashboard", "2026-08-06T00:00:00Z")
        b = pt.plan_id("rebuild the dashboard", "2026-08-06T00:00:00Z")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("wo-20260806-rebuild-the-dashboard-"))

    def test_differs_when_task_differs(self):
        a = pt.plan_id("task one", "2026-08-06T00:00:00Z")
        b = pt.plan_id("task two", "2026-08-06T00:00:00Z")
        self.assertNotEqual(a, b)


class TestCreateNoGate(unittest.TestCase):
    def test_creative_task_no_longer_refused(self):
        # what used to raise CreativeTaskRefused now just succeeds
        plan = pt.create("build a brand new dashboard component", source="direct",
                          plan_doc=None, project="p", branch="b",
                          roles_dir=self.roles_dir)
        self.assertEqual(plan["schema"], 2)
        self.assertEqual(len(plan["steps"]), 1)

    def test_no_force_kwarg_exists(self):
        import inspect
        self.assertNotIn("force", inspect.signature(pt.create).parameters)

    def test_creative_score_removed(self):
        self.assertFalse(hasattr(pt, "creative_score"))
        self.assertFalse(hasattr(pt, "CreativeTaskRefused"))


class TestCreateAssignsAndBriefs(unittest.TestCase):
    # setUp() builds self.roles_dir exactly as the existing
    # TestAssign.setUp() does today — reuse that fixture, do not duplicate it.
    def test_new_step_arrives_already_assigned_and_briefed(self):
        plan = pt.create("write the quarterly data pipeline", source="direct",
                          plan_doc=None, project="p", branch="b",
                          roles_dir=self.roles_dir)
        step = plan["steps"][0]
        self.assertIsNotNone(step["agent"])
        self.assertIsInstance(step["brief"], str)
        self.assertIn(plan["task_id"], step["brief"])
        self.assertIn(step["id"], step["brief"])
        self.assertEqual(step["status"], "pending")

    def test_from_plan_creates_one_step_per_heading_all_briefed(self):
        doc = "### Task 1: First thing\n### Task 2: Second thing\n"
        plan = pt.create("parent task", source="plan", plan_doc="doc.md",
                          project="p", branch="b", roles_dir=self.roles_dir,
                          goals=pt.parse_plan_doc(doc))
        self.assertEqual(len(plan["steps"]), 2)
        for step in plan["steps"]:
            self.assertTrue(step["brief"])
            self.assertEqual(step["depends_on"], [])
            self.assertIsNone(step["budget_tokens"])
            self.assertFalse(step["worktree"])

    def test_reasoning_defaults_empty_and_is_settable(self):
        plan = pt.create("a task", source="direct", plan_doc=None, project="p",
                          branch="b", roles_dir=self.roles_dir)
        self.assertEqual(plan["supervisor_reasoning"], "")
        plan2 = pt.create("a task", source="direct", plan_doc=None, project="p",
                          branch="b", roles_dir=self.roles_dir,
                          reasoning="routed to generalist, low ambiguity")
        self.assertEqual(plan2["supervisor_reasoning"],
                         "routed to generalist, low ambiguity")


class TestDatePartitionedPersistence(unittest.TestCase):
    def test_round_trip_uses_date_from_task_id(self):
        with tempfile.TemporaryDirectory() as base:
            plan = pt.create("x", source="direct", plan_doc=None, project="p",
                             branch="b", roles_dir=self.roles_dir,
                             created="2026-08-06T12:00:00Z")
            pt.save(base, plan)
            expected = pathlib.Path(base) / "2026-08-06" / (plan["task_id"] + ".json")
            self.assertTrue(expected.is_file())
            loaded = pt.load(base, plan["task_id"])
            self.assertEqual(loaded, plan)

    def test_unknown_schema_rejected(self):
        with tempfile.TemporaryDirectory() as base:
            d = pathlib.Path(base) / "2026-08-06"
            d.mkdir(parents=True)
            (d / "wo-20260806-x-abc123.json").write_text('{"schema": 1, "task_id": "wo-20260806-x-abc123"}')
            with self.assertRaises(pt.WorkOrderError):
                pt.load(base, "wo-20260806-x-abc123")
```

(Keep every existing `TestPlanDocParse`, `TestPersistence` malformed-JSON/missing-file case, and `TestAssign` idempotency case from the current file — they test behavior that is unchanged by this task, just update field names `parts`→`steps`, `part_id`→`id`, `role`→`agent` wherever those tests touch a plan dict directly.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd payload/tools/tests && python3 -m unittest test_plan_task -v`
Expected: FAIL — `AttributeError` / `TypeError` on the new signatures and removed gate.

- [ ] **Step 3: Implement the new `plan_task.py`**

Delete `MIN_CREATIVE`, `CREATIVE_STRONG`, `CREATIVE_WEAK`, `creative_score()`, `is_creative()`, `_refusal_message()`, `CreativeTaskRefused`. Bump `SCHEMA = 2`.

Port `render()` and `BRIEF_TEMPLATE`/`RETURN_SCHEMA` from `make_brief.py` into this file verbatim, renaming `_part(wo, part_id)`→internal step lookup by `id`, `wo.get("plan_id")`→`plan.get("task_id")`; keep `obs_emit.trace_id_for`/`span_id_for` calls as-is (`obs_emit` becomes a new top-of-file import here). Rename the function to `render_brief(plan, step)`.

`create(task, source, plan_doc, project, branch, roles_dir, goals=None, created=None, reasoning="", budget_tokens=None, worktree=False)`: builds the step list exactly as the old `create()`+`assign()` did (call `route_role.load_roles(roles_dir)` once, `route_role.route()` per goal), sets `agent`/`agent_score`/`skills`/`model`/`depends_on: []`/`budget_tokens`/`worktree`, then calls `render_brief(plan, step)` for every step before returning — so a freshly created plan is always fully assigned and briefed. No `is_creative` branch anywhere in this function.

`_path(base_dir, task_id)`: extract the 8-digit date from `task_id` via regex `wo-(\d{8})-`, reformat `YYYYMMDD`→`YYYY-MM-DD`, return `pathlib.Path(base_dir) / that / (task_id + ".json")`. `save()`/`load()` use this; `load()` still checks `schema == SCHEMA` and raises `WorkOrderError` otherwise (rename the message from "work order" to "plan" throughout, but the exception class name `WorkOrderError` stays — renaming it would touch every importer in Tasks 3, 5, and is not worth the churn for a name that reads fine either way).

Keep `assign(plan, roles_dir)` as a standalone re-routing function for the `--assign` CLI action (Task 2 wires it in): re-runs `route_role.route()` and `render_brief()` for every step not in `("done", "failed")`, leaving closed steps untouched — this is the same idempotency contract the old `assign()` had.

CLI: `--new`, `--from-plan` + `--task`, `--assign`, `--show` stay; add `--reasoning`, `--budget-tokens` (int), `--worktree` (store_true) as optional flags on the create path; remove `--force`, `--classify`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd payload/tools/tests && python3 -m unittest test_plan_task -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add payload/tools/plan_task.py payload/tools/tests/test_plan_task.py
git commit -m "$(cat <<'EOF'
feat(plan): plan_task.py schema 2 — steps replace parts, gate removed

(1) Task & Change
Phase 1 of docs/superpowers/specs/2026-08-06-agent-loop-v2-design.md. Folds
BRIEF (formerly make_brief.py) into DECOMPOSE/ASSIGN so plan_task.py --new /
--from-plan returns a fully assigned, fully briefed plan in one call. Removes
the creativity gate (creative_score/MIN_CREATIVE/CreativeTaskRefused/--force)
from the tool itself, not just the hook that calls it. Plans persist at
~/.claude/plans/<YYYY-MM-DD>/<task_id>.json, date-partitioned by parsing the
date out of task_id so lookup by id needs no directory scan.

(2) Tests created / modified
- payload/tools/tests/test_plan_task.py — new schema-2 field names, no-gate
  behavior, date-partitioned persistence round trip.

(3) Test results — evidence
$ cd payload/tools/tests && python3 -m unittest test_plan_task -v
<paste real output>
EOF
)"
```

---

### Task 2: `plan_task.py` — `--record` replaces `--log`

**Files:**
- Modify: `payload/tools/plan_task.py`
- Modify: `payload/tools/tests/test_plan_task.py`

**Interfaces:**
- Consumes: `load()`/`save()` from Task 1.
- Produces: `record_return(plan, step_id, payload)` → the mutated step dict.

- [ ] **Step 1: Write the failing tests**

```python
class TestRecordReturn(unittest.TestCase):
    def test_record_sets_done_on_ok_true(self):
        plan = self._plan_with_one_step()
        pt.record_return(plan, "S1", {"ok": True, "summary": "did it"})
        self.assertEqual(plan["steps"][0]["status"], "done")
        self.assertEqual(plan["steps"][0]["return"]["summary"], "did it")

    def test_missing_ok_is_failed_not_done(self):
        plan = self._plan_with_one_step()
        pt.record_return(plan, "S1", {"summary": "ambiguous"})
        self.assertEqual(plan["steps"][0]["status"], "failed")

    def test_ok_false_sets_failed(self):
        plan = self._plan_with_one_step()
        pt.record_return(plan, "S1", {"ok": False, "summary": "nope"})
        self.assertEqual(plan["steps"][0]["status"], "failed")

    def test_agent_task_id_captured(self):
        plan = self._plan_with_one_step()
        pt.record_return(plan, "S1", {"ok": True, "agent_task_id": "agent-abc"})
        self.assertEqual(plan["steps"][0]["agent_task_id"], "agent-abc")

    def test_unknown_step_raises(self):
        plan = self._plan_with_one_step()
        with self.assertRaises(KeyError):
            pt.record_return(plan, "S99", {"ok": True})

    def test_cli_record_requires_step_and_json(self):
        # subprocess CLI test, mirrors the file's existing TestCLI pattern:
        # `plan_task.py --record <id>` with neither --step nor --json exits 2
        ...
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd payload/tools/tests && python3 -m unittest test_plan_task -v`
Expected: FAIL — `AttributeError: module 'plan_task' has no attribute 'record_return'`

- [ ] **Step 3: Implement**

Rename `log_part(wo, part_id, payload)` to `record_return(plan, step_id, payload)`: same body, `wo.get("parts")`→`plan.get("steps")`, `part.get("part_id")`→`step.get("id")`, `part["log"]`→`step["return"]`. CLI: rename `--log` to `--record` (keep `--part`→rename to `--step` for consistency with the new field name, `--json` unchanged).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd payload/tools/tests && python3 -m unittest test_plan_task -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add payload/tools/plan_task.py payload/tools/tests/test_plan_task.py
git commit -m "$(cat <<'EOF'
feat(plan): plan_task.py --record replaces --log

(1) Task & Change
Continues Phase 1. --log/--part renamed to --record/--step to match the new
steps[] schema; log_part() renamed to record_return(), writing into
step["return"] instead of part["log"].

(2) Tests created / modified
- payload/tools/tests/test_plan_task.py — record_return unit tests + CLI arg
  validation.

(3) Test results — evidence
$ cd payload/tools/tests && python3 -m unittest test_plan_task -v
<paste real output>
EOF
)"
```

---

### Task 3: `score_task.py` — `auto_assess()` and `--auto`

**Files:**
- Modify: `payload/tools/score_task.py`
- Modify: `payload/tools/tests/test_score_task.py`

**Interfaces:**
- Consumes: `plan_task.load(base_dir, task_id)` / `plan_task.save(base_dir, plan)` (Task 1).
- Produces: `verdict(evidence)` → `str` (ported unchanged); `metrics_for(metrics_dir, agent_task_id)` → `dict|None` (ported unchanged); `git_evidence(repo, since, until, files)` → `dict` (ported unchanged); `auto_assess(plan, metrics_dir, repo=None, followup_hours=24)` → mutates `plan["steps"][i]["assessment"]` in place and returns `plan`; `evidence_scale_for(verdict)` → one of `"proven"`/`"partial"`/`"asserted"`.

- [ ] **Step 1: Write the failing tests**

```python
class TestAutoAssess(unittest.TestCase):
    # port every case from the old test_assess_task.py's TestVerdict,
    # TestMetricsFor, and TestGitEvidence classes verbatim — same inputs,
    # same expected verdict strings ("clean"/"dirty"/"unknown"), just import
    # them as score_task.verdict / score_task.metrics_for / score_task.git_evidence
    # instead of assess_task.*.

    def test_assess_fills_assessment_on_every_step(self):
        plan = self._plan_with_one_done_step()  # agent_task_id set, status done
        st.auto_assess(plan, self.metrics_dir, repo=None)
        step = plan["steps"][0]
        self.assertIn("evidence", step["assessment"])
        self.assertIn(step["assessment"]["verdict"], ("clean", "dirty", "unknown"))

    def test_failed_step_cannot_assess_clean(self):
        plan = self._plan_with_one_failed_step()
        st.auto_assess(plan, self.metrics_dir, repo=None)
        self.assertEqual(plan["steps"][0]["assessment"]["verdict"], "dirty")


class TestEvidenceScaleMapping(unittest.TestCase):
    def test_clean_maps_to_proven(self):
        self.assertEqual(st.evidence_scale_for("clean"), "proven")

    def test_dirty_maps_to_asserted_not_partial(self):
        # dirty means a real problem was found, not merely "no strong signal" —
        # asserted ("no verifiable evidence backs the outcome claim") is closer
        # in spirit than partial, and a caller who wants a rework=minor|major
        # flag reads that from the per-step assessment, not this scale alone.
        self.assertEqual(st.evidence_scale_for("dirty"), "asserted")

    def test_unknown_maps_to_asserted(self):
        self.assertEqual(st.evidence_scale_for("unknown"), "asserted")


class TestAutoCLI(unittest.TestCase):
    def test_auto_writes_assessment_and_appends_score_record(self):
        # subprocess CLI test: score_task.py --auto <task_id> --state-dir ...
        #   --metrics-dir ... ; then read back the plan file and confirm
        # assessment is populated, and grep the metrics shard for a new
        # kind:"score" record with scales.evidence set.
        ...

    def test_auto_flags_rework_on_followup_fix(self):
        # a step whose evidence shows followup_fixes > 0 causes the emitted
        # score record to also include scales.rework = "minor"
        ...
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd payload/tools/tests && python3 -m unittest test_score_task -v`
Expected: FAIL — `AttributeError: module 'score_task' has no attribute 'auto_assess'`

- [ ] **Step 3: Implement**

Port `verdict()`, `metrics_for()`, `git_evidence()` from `assess_task.py` into `score_task.py` unchanged (they take plain dicts/strings, no schema dependency). Port `assess()`, renamed `auto_assess(plan, metrics_dir, repo=None, followup_hours=FOLLOWUP_HOURS)`: same body, `wo.get("parts")`→`plan.get("steps")`, `part.get("agent_task_id")` unchanged field name, `part.get("log")`→`step.get("return")`, and instead of setting `part["evidence"]`/`part["verdict"]` separately, set `step["assessment"] = {"evidence": evidence, "verdict": v}`.

`evidence_scale_for(v)`: `{"clean": "proven", "dirty": "asserted", "unknown": "asserted"}[v]` — a `"partial"` value is never emitted by the mapping itself (a signal either fully backs the claim or doesn't), but the scale's third level exists for a human's own subjective score, so `--scale evidence=partial` remains valid when someone scores by hand.

`--auto <task_id>` CLI action (new, alongside the existing `--task-id --scale` mode which stays untouched): load the plan via `plan_task.load()`, call `auto_assess()`, save it back via `plan_task.save()`, then append one `kind:"score"` record **per step**, each keyed by `score_task.step_task_id(plan, step)` — the same key `loop_close.task_records()` gives that step's `kind:"task"` record — with `scales={"evidence": evidence_scale_for(that step's verdict)}`, plus `scales["rework"] = "minor"` when that step's assessment shows `followup_fixes > 0` (or `"major"` when it shows a `revert`), and `resources_deployed` looked up exactly as `_lookup_resources()` already does. The worst verdict across all steps (`dirty` > `unknown` > `clean` — dirty wins so a bad step is never masked by good ones) is printed as an operator summary.

> **Corrected 2026-08-07, final whole-branch review.** As originally written, this task specified ONE rolled-up record keyed on the plan id run through `_normalize_task_id()`. That produced a `session-wo-*` key matching no `kind:"task"` record anywhere, so `_lookup_resources()` always returned `[]` and no heuristic rule could reach the score — the SCORE→LEARN wiring was inert. `_normalize_task_id()` was built for genuinely bare human/session ids, not plan ids, and is no longer applied on the `--auto` path at all.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd payload/tools/tests && python3 -m unittest test_score_task -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add payload/tools/score_task.py payload/tools/tests/test_score_task.py
git commit -m "$(cat <<'EOF'
feat(score): score_task.py auto_assess() absorbs assess_task's verdict logic

(1) Task & Change
Continues Phase 1. Ports assess_task.py's objective clean/dirty/unknown
verdict algorithm (tests/tool-errors/commits/reverts from the metrics shard
and git log) into score_task.py as auto_assess(), targeting the new steps[]
schema. Maps the verdict onto the existing SCALES.md evidence scale
(proven/asserted) instead of a bespoke field, and flags rework on a detected
follow-up-fix or revert commit. auto_assess() is a plain function so
loop_close.py (Task 5) can call it directly, same as it called
assess_task.assess() before.

(2) Tests created / modified
- payload/tools/tests/test_score_task.py — ported verdict/metrics_for/
  git_evidence cases from test_assess_task.py, plus new evidence-scale
  mapping and --auto CLI tests.

(3) Test results — evidence
$ cd payload/tools/tests && python3 -m unittest test_score_task -v
<paste real output>
EOF
)"
```

---

### Task 4: Delete `make_brief.py` and `assess_task.py`

**Files:**
- Delete: `payload/tools/make_brief.py`, `payload/tools/tests/test_make_brief.py`
- Delete: `payload/tools/assess_task.py`, `payload/tools/tests/test_assess_task.py`
- Modify: `payload/MANIFEST`

**Interfaces:**
- Consumes: nothing new — this task only removes code whose behavior Tasks 1 and 3 have already absorbed and tested.

- [ ] **Step 1: Confirm no remaining importers**

Run: `grep -rn "import make_brief\|import assess_task\|from make_brief\|from assess_task" ~/dev/claude-agent-loop/payload/`
Expected: matches only in `loop_close.py` (fixed in Task 5) — if anything else matches, stop and handle it before deleting.

- [ ] **Step 2: Delete the files**

```bash
git rm payload/tools/make_brief.py payload/tools/tests/test_make_brief.py
git rm payload/tools/assess_task.py payload/tools/tests/test_assess_task.py
```

- [ ] **Step 3: Update `payload/MANIFEST`**

Remove the `link-file tools/make_brief.py` (line 237) and `link-file tools/assess_task.py` (line 217) lines.

- [ ] **Step 4: Run the full suite to confirm nothing else broke**

Run: `cd payload/tools/tests && ./run_all.sh`
Expected: `test_loop_close` FAILS (expected — Task 5 fixes it next), everything else PASSES.

- [ ] **Step 5: Commit**

```bash
git add -u payload/MANIFEST
git commit -m "$(cat <<'EOF'
refactor(plan): delete make_brief.py and assess_task.py

(1) Task & Change
Continues Phase 1. Both tools' logic now lives in plan_task.py (brief
rendering, Task 1) and score_task.py (auto_assess, Task 3). loop_close.py
still imports assess_task at this commit — fixed in the next task, so
test_loop_close is expected to fail here and only here.

(2) Tests created / modified
- Deleted payload/tools/tests/test_make_brief.py and test_assess_task.py —
  their coverage moved into test_plan_task.py (Task 1) and test_score_task.py
  (Task 3).

(3) Test results — evidence
$ cd payload/tools/tests && ./run_all.sh
<paste output showing only test_loop_close failing, with the ImportError>
EOF
)"
```

---

### Task 5: `loop_close.py` — rewire onto `score_task.auto_assess`, `steps[]`, date-partitioned plans

**Files:**
- Modify: `payload/tools/loop_close.py`
- Modify: `payload/tools/tests/test_loop_close.py`

**Interfaces:**
- Consumes: `plan_task.load()`/`save()` (Task 1), `score_task.auto_assess()` (Task 3).
- Produces: same public surface as before, renamed where the schema renamed: `is_ready(plan)`, `is_closed(plan)`, `find_agent_id(projects_dir, step_id, task_id=None)`, `link(plan, projects_dir)`, `task_records(plan)`, `run_records(plan)`, `emit(metrics_dir, records)`, `close_one(plan, metrics_dir, projects_dir, repo=None, dry_run=False)`, `ready_plans(base_dir)` (renamed from `ready_work_orders`).

- [ ] **Step 1: Write the failing tests**

```python
# Port every existing test in test_loop_close.py, renaming:
#   wo["parts"] -> plan["steps"], part_id -> id, part["log"] -> step["return"],
#   part["evidence"]/part["verdict"] -> step["assessment"]["evidence"/"verdict"],
#   assess_task.assess -> score_task.auto_assess (mock/patch target),
#   ready_work_orders -> ready_plans.
# Two behaviors are genuinely new and need new cases:

class TestReadyPlansScansDatePartitions(unittest.TestCase):
    def test_scans_every_date_subdirectory(self):
        with tempfile.TemporaryDirectory() as base:
            self._write_ready_plan(base, "2026-08-05", "wo-20260805-a-111111")
            self._write_ready_plan(base, "2026-08-06", "wo-20260806-b-222222")
            found = lc.ready_plans(base)
            self.assertEqual({p["task_id"] for p in found},
                             {"wo-20260805-a-111111", "wo-20260806-b-222222"})

    def test_missing_base_dir_is_empty_not_an_error(self):
        self.assertEqual(lc.ready_plans("/no/such/dir"), [])


class TestCloseOneUsesAutoAssess(unittest.TestCase):
    def test_close_one_populates_assessment_via_score_task(self):
        plan = self._ready_plan_one_step()
        lc.close_one(plan, self.metrics_dir, self.projects_dir)
        self.assertIsNotNone(plan["steps"][0]["assessment"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd payload/tools/tests && python3 -m unittest test_loop_close -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'assess_task'` and `AttributeError` on renamed functions.

- [ ] **Step 3: Implement**

Replace `import assess_task` with `import score_task`. Replace every `assess_task.assess(wo, ...)` call with `score_task.auto_assess(plan, ...)`. Rename `wo`→`plan`, `part`→`step`, `part_id`→`id`, `part.get("log")`→`step.get("return")`, `part.get("evidence")`/`part.get("verdict")`→`(step.get("assessment") or {}).get("evidence")`/`.get("verdict")` in `task_records()` and `run_records()`. Rename `ready_work_orders(state_dir)`→`ready_plans(base_dir)`: replace `d.glob("*.json")` with `d.glob("*/*.json")` (one level of date-partition directories) and pass `f.stem` (still the bare `task_id`, since the filename is unchanged) to `plan_task.load(base_dir, f.stem)` — `load()`'s own `_path()` re-derives the date from the id, so this works unchanged even though the glob found the file one directory deeper. `find_agent_id()`: rename its `part_id` parameter to `step_id`, `plan_id` parameter to `task_id` — body unchanged (`make_brief.py`'s old brief template already wrote both identifiers into the dispatch prompt; Task 1's `render_brief()` still does, via the same `BRIEF_TEMPLATE`).

CLI default: `--state-dir` becomes `--base-dir`, default `str(home / "plans")`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd payload/tools/tests && python3 -m unittest test_loop_close -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add payload/tools/loop_close.py payload/tools/tests/test_loop_close.py
git commit -m "$(cat <<'EOF'
refactor(plan): loop_close.py onto score_task.auto_assess and steps[]

(1) Task & Change
Continues Phase 1. The SessionEnd unattended-close path now imports
score_task instead of the deleted assess_task, and reads/writes the new
steps[]/assessment schema. ready_work_orders() becomes ready_plans(),
scanning one level of YYYY-MM-DD date-partition directories under
~/.claude/plans/ instead of a flat workorders/ directory.

(2) Tests created / modified
- payload/tools/tests/test_loop_close.py — renamed fixtures throughout;
  new coverage for date-partition scanning and the score_task handoff.

(3) Test results — evidence
$ cd payload/tools/tests && ./run_all.sh
<paste output — full suite green>
EOF
)"
```

---

### Task 6: `loop-close.sh` — point at `~/.claude/plans`

**Files:**
- Modify: `payload/hooks/loop-close.sh`
- Modify: `payload/tools/tests/test_hooks_harvest.sh` (its `STATE_DIR` assertions, if any reference the old path — check first)

**Interfaces:**
- Consumes: `loop_close.py --all` (Task 5's new `--base-dir` flag).

- [ ] **Step 1: Check the current test for a path assumption**

Run: `grep -n "STATE_DIR\|workorders" ~/dev/claude-agent-loop/payload/tools/tests/test_hooks_harvest.sh`
If it asserts on the literal `metrics/state/workorders` path, that assertion needs updating in Step 3 below; if it only asserts on behavior (records emitted), no test change is needed.

- [ ] **Step 2: Implement**

In `loop-close.sh`, change:
```bash
STATE_DIR="${STATE_DIR:-$METRICS_DIR/state/workorders}"
```
to:
```bash
BASE_DIR="${BASE_DIR:-$CLAUDE_DIR/plans}"
```
and update the two references (`STATE_DIR` env-var passthrough into the heredoc, and the `import loop_close` call in Step 1 of the heredoc which calls `loop_close.ready_work_orders(state)`) to `loop_close.ready_plans(base)` using `BASE_DIR`. `plan_task.save(state, wo)` inside the heredoc becomes `plan_task.save(base, wo)`.

- [ ] **Step 3: Update the test if Step 1 found a path assertion**

Change the literal path string to match `plans/<date>/`.

- [ ] **Step 4: Run the test**

Run: `cd payload/tools/tests && bash test_hooks_harvest.sh`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add payload/hooks/loop-close.sh payload/tools/tests/test_hooks_harvest.sh
git commit -m "$(cat <<'EOF'
refactor(plan): loop-close.sh reads ~/.claude/plans, not metrics/state/workorders

(1) Task & Change
Continues Phase 1. Repoints the SessionEnd hook's default base directory at
the new date-partitioned plans/ layout Task 5's ready_plans() expects.

(2) Tests created / modified
- payload/tools/tests/test_hooks_harvest.sh — path assertion updated if one
  existed (see step 1's grep).

(3) Test results — evidence
$ cd payload/tools/tests && bash test_hooks_harvest.sh
<paste output>
EOF
)"
```

---

### Task 7: `pipeline-relay.sh` — update the directive text

**Files:**
- Modify: `payload/hooks/pipeline-relay.sh`
- Modify: `payload/tools/tests/test_pipeline_relay.sh`

**Interfaces:**
- Consumes: nothing code-level — this is a text-content change to the `RELAYS` dict's two strings.

- [ ] **Step 1: Write the failing test assertions**

The existing `test_pipeline_relay.sh` (per its structure) asserts `sys.argv[1] in h['additionalContext']` for a substring passed on the command line. Add/change its invocations to assert the NEW substrings are present and the OLD ones are gone:

```bash
# writing-plans link must mention --from-plan but NOT make_brief.py/--log/assess_task.py
run_case "writing-plans" "plan_task.py --from-plan"
run_case_absent "writing-plans" "make_brief.py"
run_case_absent "writing-plans" "assess_task.py"
```

(Follow the file's existing helper-function shape for `run_case`; add a `run_case_absent` helper alongside it if the file doesn't already have a negative-assertion helper — same pattern, inverted `assert`.)

- [ ] **Step 2: Run to verify failure**

Run: `bash payload/tools/tests/test_pipeline_relay.sh`
Expected: FAIL on the new assertions (old text still present).

- [ ] **Step 3: Implement**

Update the `RELAYS` dict in `pipeline-relay.sh`:

```python
RELAYS = {
    "brainstorming": (
        "PIPELINE RELAY: brainstorming settles the DESIGN. Its output is a spec, "
        "and a spec is not a decomposition — do not start implementing from it.\n"
        "The chain continues:\n"
        "  next  Skill(superpowers:writing-plans) — break the design into tasks\n"
        "  then  python3 ~/.claude/tools/plan_task.py --from-plan <plan-doc> "
        "--task \"<the request>\"\n"
        "The plan is what makes the work measurable. Without it, nothing "
        "downstream can attribute or score this task."
    ),
    "writing-plans": (
        "PIPELINE RELAY: once this plan document is written, create the plan "
        "artifact BEFORE implementing:\n"
        "  python3 ~/.claude/tools/plan_task.py --from-plan <plan-doc> "
        "--task \"<the request>\"\n"
        "Every step returned is already assigned and briefed — dispatch it "
        "directly. Then per step: plan_task.py --record <task_id> --step <id> "
        "--json <file-or-json> to record each return (write the return to a "
        "file and pass the path — a real return's prose carries quotes and "
        "newlines that shell quoting mangles), and score_task.py --auto "
        "<task_id> at the end."
    ),
}
```

- [ ] **Step 4: Run the test**

Run: `bash payload/tools/tests/test_pipeline_relay.sh`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add payload/hooks/pipeline-relay.sh payload/tools/tests/test_pipeline_relay.sh
git commit -m "$(cat <<'EOF'
refactor(plan): pipeline-relay.sh directive text for the collapsed pipeline

(1) Task & Change
Continues Phase 1. Drops make_brief.py/--log/assess_task.py mentions from
the two relay messages, replacing them with plan_task.py --record and
score_task.py --auto.

(2) Tests created / modified
- payload/tools/tests/test_pipeline_relay.sh — asserts new substrings
  present, old tool names absent.

(3) Test results — evidence
$ bash payload/tools/tests/test_pipeline_relay.sh
<paste output>
EOF
)"
```

---

### Task 8: Remove `workorder-gate.sh`

**Files:**
- Delete: `payload/hooks/workorder-gate.sh`, `payload/tools/tests/test_workorder_gate.sh`
- Modify: `~/.claude/settings.json` (the live, non-symlinked settings file — not under `payload/`)
- Modify: `payload/MANIFEST`

**Interfaces:** none — pure removal.

- [ ] **Step 1: Remove the files**

```bash
git rm payload/hooks/workorder-gate.sh payload/tools/tests/test_workorder_gate.sh
```

- [ ] **Step 2: Remove its `link-file` line from `payload/MANIFEST`**

- [ ] **Step 3: Remove its entry from `~/.claude/settings.json`**

Edit the `hooks.UserPromptSubmit` array (currently 3 entries: `auto-update.sh`, `workorder-gate.sh`, `prompt-clarity-gate.sh`) to remove the middle entry, leaving:
```json
"UserPromptSubmit": [
  {"hooks": [{"type": "command", "command": "/Users/ryanhurst/.claude/hooks/auto-update.sh"}]},
  {"hooks": [{"type": "command", "command": "/Users/ryanhurst/.claude/hooks/prompt-clarity-gate.sh"}]}
]
```
This is a direct edit to the live file, not routed through `loop_autocommit.sh` (see Global Constraints).

- [ ] **Step 4: Verify no other hook fires on the removed file**

Run: `grep -rln "workorder-gate" ~/dev/claude-agent-loop/payload/ ~/.claude/settings.json`
Expected: no matches remain.

- [ ] **Step 5: Manually exercise a creative prompt to confirm silence**

Run: `echo '{"prompt": "build a brand new dashboard", "session_id": "test"}' | CLAUDE_DIR=~/.claude python3 -c "import sys; sys.exit(0)"` is not a real hook test (no hook left to run) — instead confirm by inspection that `settings.json`'s `UserPromptSubmit` array no longer references the deleted path, which Step 4's grep already established.

- [ ] **Step 6: Commit (framework repo)**

```bash
git add -u payload/MANIFEST
git commit -m "$(cat <<'EOF'
feat(plan): remove workorder-gate.sh — no keyword-scored PLAN backstop

(1) Task & Change
Phase 1 of the v2 spec, decided collaboratively: the creativity gate that
auto-intercepted every prompt is dropped. PLAN becomes a directive step in
the resource-loop skill (Task 10), exercised by agent judgment, same trust
level as MATCH/ANNOUNCE/ROUTE/SCORE. Confirmed zero other hooks depend on
plan_task.creative_score before removing it in Task 1.

(2) Tests created / modified
- Deleted payload/tools/tests/test_workorder_gate.sh — nothing replaces it,
  there is no gate left to test.

(3) Test results — evidence
$ grep -rln "workorder-gate" payload/ — no matches.
EOF
)"
```

- [ ] **Step 7: Commit (settings.json, separately — different repo/tree)**

```bash
cd ~/.claude && git add settings.json
git commit -m "$(cat <<'EOF'
feat(hooks): drop workorder-gate.sh from UserPromptSubmit

(1) Task & Change
Companion to the claude-agent-loop framework-repo commit removing
workorder-gate.sh's source. This machine's live settings.json must stop
referencing the deleted hook path or every prompt would hit a missing file.

(2) Tests created / modified
N/A — settings.json edit; verified by grep in the framework-repo commit that
no remaining reference to workorder-gate.sh exists anywhere.

(3) Test results — evidence
$ python3 -c "import json; json.load(open('settings.json'))"  # valid JSON
<paste output — no exception>
EOF
)"
```

---

### Task 9: Migration script — `workorders/*.json` → `plans/<YYYY-MM-DD>/<task_id>.json`

**Files:**
- Create: `payload/tools/migrate_workorders_to_plans.py`
- Create: `payload/tools/tests/test_migrate_workorders_to_plans.py`

**Interfaces:**
- Consumes: nothing from earlier tasks except the target schema shape (Task 1).
- Produces: `migrate_one(old_wo)` → `dict` (a schema-2 plan); `migrate_all(state_dir, base_dir, archive_dir, dry_run=False)` → `list[dict]` (summary per file: old id, new path, step count).

**Field mapping (schema 1 → 2), applied per part→step:**

| Old | New |
|---|---|
| `plan_id` | `task_id` |
| `task` | `task` |
| *(nothing)* | `supervisor_reasoning: ""` |
| `part_id` | `id` |
| `role` | `agent` |
| `role_score` | `agent_score` |
| `skills`, `model`, `agent_task_id`, `status` | unchanged |
| *(nothing)* | `depends_on: []`, `budget_tokens: None`, `worktree: False` |
| *(nothing — brief was rendered on demand, never persisted)* | `brief: ""` for any step not already `done`/`failed` (a genuinely stale, never-briefed step can't have its historical brief reconstructed; if it's re-dispatched, re-run `plan_task.py --assign` first, which will render one) |
| `log` | `return` |
| `evidence` + `verdict` (when both present) | `assessment: {"evidence": evidence, "verdict": verdict}`; when either is `None`, `assessment: None` |
| `score` | dropped (see Task 1's table) |
| `status: "assigned"` | becomes `status: "pending"` (the intermediate `assigned` value no longer exists — Task 1) |

Top-level: `schema: 1`→`2`, everything else (`created`, `project`, `git_branch`, `source`, `plan_doc`, `closed_at` if present) carries over unchanged. `forced` is dropped (the field it recorded — a creativity-gate override — no longer exists as a concept).

- [ ] **Step 1: Write the failing tests**

```python
class TestMigrateOne(unittest.TestCase):
    def test_maps_every_field(self):
        old = {
            "schema": 1, "plan_id": "wo-20260805-x-111111", "task": "do a thing",
            "source": "plan", "plan_doc": "doc.md", "forced": False,
            "created": "2026-08-05T10:00:00Z", "project": "p", "git_branch": "main",
            "parts": [{
                "part_id": "p1", "goal": "the goal", "status": "done",
                "role": "generalist", "role_score": 0, "skills": [], "model": "opus",
                "agent_task_id": "agent-abc", "log": {"ok": True, "summary": "did it"},
                "evidence": {"tests_detected": False}, "verdict": "clean", "score": None,
            }],
        }
        new = mig.migrate_one(old)
        self.assertEqual(new["schema"], 2)
        self.assertEqual(new["task_id"], "wo-20260805-x-111111")
        self.assertEqual(new["supervisor_reasoning"], "")
        step = new["steps"][0]
        self.assertEqual(step["id"], "p1")
        self.assertEqual(step["agent"], "generalist")
        self.assertEqual(step["return"], {"ok": True, "summary": "did it"})
        self.assertEqual(step["assessment"], {"evidence": {"tests_detected": False}, "verdict": "clean"})
        self.assertEqual(step["depends_on"], [])
        self.assertNotIn("score", step)
        self.assertNotIn("forced", new)

    def test_assigned_status_becomes_pending(self):
        old = self._minimal_old_wo(part_status="assigned")
        new = mig.migrate_one(old)
        self.assertEqual(new["steps"][0]["status"], "pending")

    def test_pending_step_gets_empty_brief(self):
        old = self._minimal_old_wo(part_status="assigned")
        new = mig.migrate_one(old)
        self.assertEqual(new["steps"][0]["brief"], "")

    def test_missing_evidence_or_verdict_yields_none_assessment(self):
        old = self._minimal_old_wo(part_status="pending")
        new = mig.migrate_one(old)
        self.assertIsNone(new["steps"][0]["assessment"])


class TestMigrateAll(unittest.TestCase):
    def test_writes_date_partitioned_files_and_archives_source(self):
        with tempfile.TemporaryDirectory() as root:
            state_dir = pathlib.Path(root) / "workorders"
            state_dir.mkdir()
            (state_dir / "wo-20260805-x-111111.json").write_text(
                json.dumps(self._minimal_old_wo_dict()))
            base_dir = pathlib.Path(root) / "plans"
            archive_dir = pathlib.Path(root) / "workorders_archive"
            summaries = mig.migrate_all(str(state_dir), str(base_dir), str(archive_dir))
            self.assertEqual(len(summaries), 1)
            self.assertTrue((base_dir / "2026-08-05" / "wo-20260805-x-111111.json").is_file())
            self.assertTrue((archive_dir / "wo-20260805-x-111111.json").is_file())
            self.assertFalse((state_dir / "wo-20260805-x-111111.json").is_file())

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            state_dir = pathlib.Path(root) / "workorders"
            state_dir.mkdir()
            (state_dir / "wo-20260805-x-111111.json").write_text(
                json.dumps(self._minimal_old_wo_dict()))
            base_dir = pathlib.Path(root) / "plans"
            mig.migrate_all(str(state_dir), str(base_dir),
                            str(pathlib.Path(root) / "archive"), dry_run=True)
            self.assertFalse(base_dir.exists())
            self.assertTrue((state_dir / "wo-20260805-x-111111.json").is_file())

    def test_no_dependency_fabricated_for_multi_part_orders(self):
        old = self._minimal_old_wo_dict()
        old["parts"] = old["parts"] * 2
        old["parts"][0]["part_id"], old["parts"][1]["part_id"] = "p1", "p2"
        new = mig.migrate_one(old)
        for step in new["steps"]:
            self.assertEqual(step["depends_on"], [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd payload/tools/tests && python3 -m unittest test_migrate_workorders_to_plans -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`migrate_one(old)` applies the field mapping table above using `plan_task._path()`-compatible output (import `plan_task` for the date-parsing regex, don't duplicate it — factor the `wo-(\d{8})-` extraction the same way `plan_task._path()` does, or call a small shared helper `plan_task.date_partition_for(task_id)` added in this task as a one-line addition to `plan_task.py`, used by both `_path()` and this migration script).

`migrate_all(state_dir, base_dir, archive_dir, dry_run=False)`: iterate `pathlib.Path(state_dir).glob("*.json")`, `json.loads` each, `migrate_one()`, and unless `dry_run`, write via `plan_task.save(base_dir, new)` and move the original file into `archive_dir` (create it if absent) via `shutil.move`. Returns one summary dict per file: `{"task_id": ..., "new_path": ..., "step_count": ...}`.

CLI: `migrate_workorders_to_plans.py [--state-dir DIR] [--base-dir DIR] [--archive-dir DIR] [--dry-run]`, defaults `~/.claude/metrics/state/workorders`, `~/.claude/plans`, `~/.claude/metrics/state/workorders_archive`. Prints one line per migrated file.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd payload/tools/tests && python3 -m unittest test_migrate_workorders_to_plans -v`
Expected: PASS

- [ ] **Step 5: Dry-run against the real 18 files, inspect the output**

Run: `python3 payload/tools/migrate_workorders_to_plans.py --dry-run`
Expected: 18 lines printed, one per file in `~/.claude/metrics/state/workorders/`, no files written (confirm with `ls ~/.claude/plans` → not found).

- [ ] **Step 6: Run for real**

Run: `python3 payload/tools/migrate_workorders_to_plans.py`
Expected: 18 lines printed; `~/.claude/plans/<date>/<id>.json` exists for each; `~/.claude/metrics/state/workorders/` is now empty; `~/.claude/metrics/state/workorders_archive/` holds all 18 original files unchanged.

- [ ] **Step 7: Spot-check one migrated file against its archived original**

Run: `python3 -c "import json; a=json.load(open('<archived original path>')); b=json.load(open('<migrated new path>')); print(len(a['parts']) == len(b['steps']))"`
Expected: `True`, and manually eyeball that a `done` step's `return`/`assessment` match the original `log`/`evidence`+`verdict`.

- [ ] **Step 8: Commit**

```bash
git add payload/tools/migrate_workorders_to_plans.py payload/tools/tests/test_migrate_workorders_to_plans.py payload/tools/plan_task.py payload/MANIFEST
git commit -m "$(cat <<'EOF'
feat(plan): migrate the 18 live work orders to the schema-2 plans layout

(1) Task & Change
Phase 1 of the v2 spec. One-time migration: parts[]->steps[], field renames
per the design doc's table, no dependency graph fabricated (depends_on stays
[] for every migrated step — order is preserved by array position only, same
as before). Originals moved to metrics/state/workorders_archive/, read-only
historical record, not deleted.

(2) Tests created / modified
- payload/tools/tests/test_migrate_workorders_to_plans.py — field-mapping
  unit tests plus a migrate_all() integration test against a fixture
  work order.

(3) Test results — evidence
$ cd payload/tools/tests && python3 -m unittest test_migrate_workorders_to_plans -v
<paste output>
$ python3 payload/tools/migrate_workorders_to_plans.py --dry-run
<paste 18-line output>
$ python3 payload/tools/migrate_workorders_to_plans.py
<paste 18-line output>
$ ls ~/.claude/metrics/state/workorders/ | wc -l   # expect 0
$ ls ~/.claude/metrics/state/workorders_archive/ | wc -l   # expect 18
EOF
)"
```

---

### Task 10: Documentation & registry sweep

**Files:**
- Modify: `payload/skills/resource-loop/SKILL.md`
- Modify: `payload/registry/REGISTRY.md`
- Delete: `payload/registry/guides/make-brief.md`, `payload/registry/guides/assess-task.md` (if the latter exists — check; the earlier survey found `plan-task.md` and `make-brief.md`, confirm `assess-task.md`'s presence before assuming)
- Modify: `payload/registry/guides/plan-task.md`
- Modify: `payload/observability/dashboards/shard-kpis.json`
- Modify: `payload/tools/obs_emit.py` (comment only)
- Modify: `payload/tools/heuristics_eval.py` (comment only)

**Interfaces:** none — text/doc changes only, no importable surface.

- [ ] **Step 1: Check for `assess-task.md`**

Run: `ls ~/dev/claude-agent-loop/payload/registry/guides/assess-task.md`
If present, fold its content into `plan-task.md` per Step 4 below and delete it; if absent, skip.

- [ ] **Step 2: Rewrite the SKILL.md pipeline section**

Replace the fenced pipeline diagram (currently lines 22–31) with:

```
DECOMPOSE  plan_task.py --new "<task>"                     one step, assigned + briefed
+ASSIGN    plan_task.py --from-plan <doc> --task "<task>"  one step per plan task,
+BRIEF                                                       assigned + briefed
EXECUTE    dispatch the step's brief; agent returns JSON, not prose
RECORD     plan_task.py --record <task_id> --step <id> --json <file-or-json>
                                            (a file path is safer than inline
                                             JSON — return prose has quotes)
SCORE      score_task.py --auto <task_id>   (objective verdict, folds in what
                                              assess_task.py used to do)
LEARN      heuristics_eval.py, reading that objective evidence
```

Remove the paragraph starting "**You do not have to remember this.** `workorder-gate.sh` runs on `UserPromptSubmit`…" entirely — replace with:

> **PLAN is judgment, not a gate.** Decide for yourself whether a task is big enough for a plan artifact — multi-step, multi-agent, or ambiguous work is; a one-line fix or a question is not. There is no keyword-scored backstop forcing this anymore. `pipeline-relay.sh` still nudges the next link once you've launched `superpowers:brainstorming` or `superpowers:writing-plans`, so a session that settles a design doesn't stop at the spec.

Update "**The superpowers gate.**" paragraph — delete it; decomposing a creative task through brainstorming/writing-plans first is still the right move, but it is no longer enforced by a tool-level refusal. Fold its one durable point into the PLAN-is-judgment paragraph above: creative work is still worth designing before it's decomposed — say so as guidance, not as a rule `plan_task.py` enforces.

Update "**What ASSESS decides…**" paragraph → retitle "**What SCORE's `--auto` mode decides…**", same content, `assess_task.py`→`score_task.py --auto`, and note the evidence-scale mapping (proven/asserted) replacing the old bespoke verdict field.

Update the SCORE numbered step (step 5 in "## The six steps") to mention `--auto` as the objective half, preceding the existing subjective `--scale` invocation.

- [ ] **Step 3: Update REGISTRY.md**

Replace the three rows (lines 38–40) with one:
```
| plan-task | tool | DECOMPOSE/ASSIGN/BRIEF/RECORD — build a plan, route and brief each step, record each subagent's structured return |
```
Add `score_task`'s row a note if it doesn't already mention `--auto` (check its current row text first; extend it to mention the auto-verdict mode if the existing row is silent on it).

- [ ] **Step 4: Merge guide docs**

Rewrite `payload/registry/guides/plan-task.md`: fold in `make-brief.md`'s "Why this exists" and "Composition" content (briefing is now part of this tool, not a handoff to a separate one), update the "Interface" block to the new CLI (`--new`, `--from-plan`, `--assign`, `--record`, `--show`), update "Composition" to say `score_task.py --auto` is the next stage instead of `assess-task`, update "Build & maintenance notes" test count (Task 1+2's combined test count, real number after those tasks land — count with `grep -c "def test_" payload/tools/tests/test_plan_task.py`). Delete `make-brief.md` (and `assess-task.md` if Step 1 found it — fold its content the same way).

- [ ] **Step 5: Update the dashboard panel**

In `shard-kpis.json`, the `resources_source` panel and its description already use the literal string `"workorder"` as an attribution-source value — leave that value unchanged (Task 5's `task_records()` still emits `resources_source: "workorder"`; renaming it would require a parallel `heuristics_eval.py` `PRECISE_SOURCES` change and would break continuity with 18 files' worth of historical metrics for no behavioral gain). Only update the top-level `"description"` field's prose where it names `assess_task.py`/`make_brief.py`/`plan_task.py` DECOMPOSE-stage-only framing, to instead say the verdict comes from `score_task.py --auto`.

- [ ] **Step 6: Update `obs_emit.py` and `heuristics_eval.py` comments**

`obs_emit.py` line 11: change "existing plan_id() convention in plan_task.py" — this is already accurate (Task 1 kept `plan_id()`'s name and behavior), so only reword if it references "work order" by name; if it does, change to "plan".

`heuristics_eval.py` line 251-254 comment (`PRECISE_SOURCES = ("task", "workorder")`): update the prose comment above it if it says "workorder is written by plan_task.py at assignment time" — Task 1 changed WHEN plan_task.py writes (now at creation, not a separate assign step for the common path), so correct that detail. The `PRECISE_SOURCES` tuple's values stay unchanged per Step 5's decision.

- [ ] **Step 7: Lint and grammar-gate everything touched**

Run: `python3 ~/.claude/tools/lint_registry.py`
Run: `python3 ~/.claude/tools/prose_grammar_gate.py payload/skills/resource-loop/SKILL.md payload/registry/REGISTRY.md payload/registry/guides/plan-task.md`
Expected: both exit 0.

- [ ] **Step 8: Commit**

```bash
git add payload/skills/resource-loop/SKILL.md payload/registry/REGISTRY.md \
        payload/registry/guides/plan-task.md payload/observability/dashboards/shard-kpis.json \
        payload/tools/obs_emit.py payload/tools/heuristics_eval.py
git rm payload/registry/guides/make-brief.md
git commit -m "$(cat <<'EOF'
docs(plan): sweep SKILL.md, REGISTRY.md, guides, dashboard for Phase 1

(1) Task & Change
Documents the collapsed pipeline: DECOMPOSE+ASSIGN+BRIEF as one step,
RECORD replacing LOG, SCORE --auto replacing ASSESS, and PLAN as agent
judgment rather than a gated hook. Collapses the plan-task/make-brief/
assess-task REGISTRY rows into one. resources_source value "workorder"
is kept unchanged in the dashboard/heuristics_eval.py to preserve
continuity with existing metrics history.

(2) Tests created / modified
None — documentation only. Verified with lint_registry.py and
prose_grammar_gate.py (see evidence).

(3) Test results — evidence
$ python3 ~/.claude/tools/lint_registry.py
<paste output>
$ python3 ~/.claude/tools/prose_grammar_gate.py payload/skills/resource-loop/SKILL.md payload/registry/REGISTRY.md payload/registry/guides/plan-task.md
<paste output>
EOF
)"
```

---

### Task 11: Full-suite verification and Phase 1 close-out

**Files:** none created — verification only.

- [ ] **Step 1: Run the full test suite**

Run: `cd payload/tools/tests && ./run_all.sh`
Expected: every test passes, including `test_plan_task`, `test_score_task`, `test_loop_close`, `test_hooks_harvest`, `test_pipeline_relay`, `test_migrate_workorders_to_plans`.

- [ ] **Step 2: Confirm no dangling references anywhere in the framework repo**

Run: `grep -rln "make_brief\|assess_task\|workorder-gate\|metrics/state/workorders[^_]" ~/dev/claude-agent-loop/payload/ | grep -v workorders_archive`
Expected: no matches (the `workorders_archive` exclusion allows Task 9's archive path to still exist).

- [ ] **Step 3: Confirm `~/.claude/settings.json` is valid and gate-free**

Run: `python3 -c "import json; d=json.load(open('/Users/ryanhurst/.claude/settings.json')); ups=[h['hooks'][0]['command'] for h in d['hooks']['UserPromptSubmit']]; print(ups); assert 'workorder-gate.sh' not in ' '.join(ups)"`
Expected: prints the 2-entry list, no assertion error.

- [ ] **Step 4: Confirm the live migration result one more time**

Run: `find ~/.claude/plans -name '*.json' | wc -l` (expect 18) and `find ~/.claude/metrics/state/workorders -maxdepth 1 -name '*.json' | wc -l` (expect 0).

- [ ] **Step 5: Update the spec doc's status**

Edit `docs/superpowers/specs/2026-08-06-agent-loop-v2-design.md`'s header: add a line under `**Status:** Approved` noting `**Phase 1 landed:** <date>, see docs/superpowers/plans/2026-08-06-plan-phase-replacement.md`.

- [ ] **Step 6: Final commit**

```bash
git add docs/superpowers/specs/2026-08-06-agent-loop-v2-design.md
git commit -m "$(cat <<'EOF'
docs(spec): mark Phase 1 (PLAN-phase replacement) landed

(1) Task & Change
Closes out Phase 1 of the v2 spec. All 11 tasks in
docs/superpowers/plans/2026-08-06-plan-phase-replacement.md are complete:
plan_task.py folds DECOMPOSE/ASSIGN/BRIEF, score_task.py --auto folds
ASSESS, make_brief.py/assess_task.py/workorder-gate.sh are deleted, the 18
live work orders are migrated to ~/.claude/plans/. Phases 2 (REGISTRY
domain taxonomy), 3 (blackboard), 5 (dispatcher generalization), and 7
(GNAP reserved filenames) are independent and each get their own plan next;
Phases 4 (worktree EXECUTE) and 6 (consensus gate) wait on 1 and 3
respectively per the spec's dependency ordering.

(2) Tests created / modified
None in this commit — status update only. Full-suite evidence below.

(3) Test results — evidence
$ cd payload/tools/tests && ./run_all.sh
<paste full green output>
$ grep -rln "make_brief\|assess_task\|workorder-gate\|metrics/state/workorders[^_]" payload/ | grep -v workorders_archive
<paste: no output>
EOF
)"
```

---

## Self-Review Notes

**Spec coverage:** Every Phase 1 bullet from the design spec is covered — new artifact/schema (Task 1), BRIEF folded in (Task 1), RECORD renamed (Task 2), SCORE absorbs ASSESS via the evidence scale (Task 3), tools deleted (Task 4), gate removed (Task 8), 9+ callers rewritten (Tasks 5–8, 10), migration of the 18 files (Task 9), REGISTRY collapse and doc updates (Task 10).

**Deferred by design, not by omission:** `depends_on`, `budget_tokens`, `worktree` (per step) and `termination` (per plan, `{"success_when", "max_steps"}`, settable via `--success-when` / `--max-steps`) are schema fields as of Task 1, but nothing in Phase 1 *acts* on them yet (no dependency-ordered dispatch, no budget enforcement, no worktree creation, no termination check) — that behavior is Phase 4 (worktree EXECUTE support) and lands once this phase is stable, per the spec's ordering. Phase 1 only needs the fields to exist so Phase 4 doesn't have to touch this schema again. `termination` was added late, during the final whole-branch review, which caught that the spec's schema example carried it while the implementation did not.

**Type/name consistency check:** `task_id` (not `plan_id`) is used consistently from Task 1 onward in every task's interface section. `step["id"]` (not `part_id`) likewise. `plan_task.WorkOrderError` keeps its old class name deliberately (noted in Task 1) — every task that raises or catches it uses that same name, no drift.
