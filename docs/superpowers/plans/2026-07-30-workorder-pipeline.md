# Work-Order Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace prose-scraped resource attribution with a per-task JSON work order that every loop stage reads and writes, so LEARN runs on precise, objective evidence.

**Architecture:** Three stdlib-only Python tools under `payload/tools/`, sharing one JSON artifact at `~/.claude/metrics/state/workorders/<plan-id>.json`. `plan_task.py` owns the artifact's whole lifecycle (create, assign, log). `make_brief.py` renders a dispatchable subagent prompt from one part. `assess_task.py` joins the artifact to the metrics shard and to `git log` to produce an objective verdict with no model involvement. Existing tools are reused, not replaced: `route_role.route()` is imported directly for per-part assignment.

**Tech Stack:** Python 3 stdlib only. `unittest` via the existing `payload/tools/tests/run_all.sh`. macOS bash 3.2 portable for any shell surface.

## Global Constraints

- Python 3 stdlib only — no third-party imports in any tool or test.
- Every tool exits 0 on success and non-zero with a stated reason on failure. These are invoked deliberately, never from a hook, so they do **not** fail open.
- No `hooks/` or `settings*.json` changes in this slice. `loop_autocommit.sh` refuses that lane by design.
- Work-order schema version is `1`. A file with any other `schema` value is rejected, not migrated.
- Every new tool gets a `link-file tools/<name>` line in `payload/MANIFEST`.
- Grammar gate (`python3 ~/.claude/tools/prose_grammar_gate.py`) must pass on every markdown file touched.
- Commit bodies use the three-section (1) Task & Change / (2) Tests created or modified / (3) Test results — evidence format.

---

### Task 1: `plan_task.py` — work-order creation and the superpowers gate

**Files:**
- Create: `payload/tools/plan_task.py`
- Test: `payload/tools/tests/test_plan_task.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `plan_id(task, created)` → `str`; `is_creative(task)` → `bool`; `create(task, source, plan_doc, force, state_dir, project, branch)` → `dict`; `parse_plan_doc(text)` → `list[str]`; `load(state_dir, plan_id)` → `dict`; `save(state_dir, wo)` → `None`. Exit code `3` means "creative task refused".

- [ ] **Step 1: Write the failing tests**

```python
import json, pathlib, tempfile, unittest
import plan_task as pt

class TestPlanId(unittest.TestCase):
    def test_deterministic_for_same_inputs(self):
        a = pt.plan_id("rebuild the dashboard", "2026-07-30T00:00:00Z")
        b = pt.plan_id("rebuild the dashboard", "2026-07-30T00:00:00Z")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("wo-20260730-rebuild-the-dashboard-"))

    def test_differs_when_task_differs(self):
        a = pt.plan_id("task one", "2026-07-30T00:00:00Z")
        b = pt.plan_id("task two", "2026-07-30T00:00:00Z")
        self.assertNotEqual(a, b)

class TestCreativeGate(unittest.TestCase):
    def test_creative_task_detected(self):
        self.assertTrue(pt.is_creative("build a new dashboard component"))
        self.assertTrue(pt.is_creative("redesign the report layout"))

    def test_mechanical_task_not_creative(self):
        self.assertFalse(pt.is_creative("count the rows in the export"))
        self.assertFalse(pt.is_creative("rename the fixture files"))

    def test_creative_direct_source_refused(self):
        with self.assertRaises(pt.CreativeTaskRefused):
            pt.create("build a new skill", source="direct", plan_doc=None,
                      force=False, state_dir="/tmp", project="p", branch="b")

    def test_force_records_the_override(self):
        wo = pt.create("build a new skill", source="direct", plan_doc=None,
                       force=True, state_dir="/tmp", project="p", branch="b")
        self.assertTrue(wo["forced"])

class TestPlanDocParse(unittest.TestCase):
    def test_extracts_task_headings(self):
        text = "# Plan\n## Group\n### Task 1: First thing\nbody\n### Task 2: Second thing\n"
        self.assertEqual(pt.parse_plan_doc(text), ["First thing", "Second thing"])

    def test_no_headings_is_an_error(self):
        with self.assertRaises(pt.PlanParseError):
            pt.parse_plan_doc("# Plan\nno task headings here\n")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd payload/tools/tests && python3 -m unittest test_plan_task -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'plan_task'`

- [ ] **Step 3: Implement `plan_task.py`**

Module-level constants and functions: `SCHEMA = 1`; `CREATIVE_PHRASES` as a tuple of route-style phrases; `CreativeTaskRefused` and `PlanParseError` exception classes. `plan_id()` slugifies the first six words of the task, prefixes `wo-<YYYYMMDD>-`, and suffixes a 6-hex SHA-256 prefix of `task + "\n" + created`. `is_creative()` reuses the scoring shape from `route_role.phrase_hits` — multi-word phrase scores 2, single word scores 1, creative at total ≥ 2. `create()` raises `CreativeTaskRefused` when `is_creative(task) and source == "direct" and not force`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd payload/tools/tests && python3 -m unittest test_plan_task -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add payload/tools/plan_task.py payload/tools/tests/test_plan_task.py
git commit -F <commit body in the three-section format>
```

---

### Task 2: `plan_task.py` — `--assign` and `--log`

**Files:**
- Modify: `payload/tools/plan_task.py`
- Modify: `payload/tools/tests/test_plan_task.py`

**Interfaces:**
- Consumes: `create()`, `load()`, `save()` from Task 1.
- Produces: `assign(wo, roles_dir)` → mutates each part with `role`, `role_score`, `skills`, `model`; `model_for(goal)` → `"session" | "opus" | "sonnet"`; `log_part(wo, part_id, payload)` → mutates `part.log` and `part.status`.

- [ ] **Step 1: Write the failing tests**

```python
class TestAssign(unittest.TestCase):
    def test_each_part_routed_independently(self):
        wo = {"schema": 1, "parts": [
            {"part_id": "p1", "goal": "author an Airflow DAG with a backfill", "status": "pending"},
            {"part_id": "p2", "goal": "run EXPLAIN ANALYZE on the slow query", "status": "pending"}]}
        pt.assign(wo, roles_dir=str(pathlib.Path.home() / ".claude" / "agents" / "roles"))
        self.assertNotEqual(wo["parts"][0]["role"], wo["parts"][1]["role"])
        self.assertEqual(wo["parts"][0]["status"], "assigned")

    def test_unroutable_part_is_generalist_with_no_skills(self):
        wo = {"schema": 1, "parts": [{"part_id": "p1", "goal": "zzz", "status": "pending"}]}
        pt.assign(wo, roles_dir=str(pathlib.Path.home() / ".claude" / "agents" / "roles"))
        self.assertEqual(wo["parts"][0]["role"], "generalist")
        self.assertEqual(wo["parts"][0]["skills"], [])

class TestModelTier(unittest.TestCase):
    def test_creation_routes_to_opus(self):
        self.assertEqual(pt.model_for("write the report narrative"), "opus")

    def test_mechanical_routes_to_sonnet(self):
        self.assertEqual(pt.model_for("extract the ids and count them"), "sonnet")

    def test_no_match_defaults_to_session(self):
        self.assertEqual(pt.model_for("zzz"), "session")

class TestLog(unittest.TestCase):
    def test_log_sets_done(self):
        wo = {"schema": 1, "parts": [{"part_id": "p1", "goal": "g", "status": "assigned"}]}
        pt.log_part(wo, "p1", {"ok": True, "summary": "did it"})
        self.assertEqual(wo["parts"][0]["status"], "done")

    def test_log_ok_false_sets_failed(self):
        wo = {"schema": 1, "parts": [{"part_id": "p1", "goal": "g", "status": "assigned"}]}
        pt.log_part(wo, "p1", {"ok": False, "summary": "blocked"})
        self.assertEqual(wo["parts"][0]["status"], "failed")

    def test_unknown_part_id_raises(self):
        wo = {"schema": 1, "parts": []}
        with self.assertRaises(KeyError):
            pt.log_part(wo, "nope", {"ok": True})
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL, `module 'plan_task' has no attribute 'assign'`
- [ ] **Step 3: Implement** — import `route_role` from the same directory (mirroring how `score_task.py` imports `lint_scales`), call `route_role.route(part["goal"], roles)` per part.
- [ ] **Step 4: Run to verify pass**
- [ ] **Step 5: Commit**

---

### Task 3: `make_brief.py` — the dispatchable brief

**Files:**
- Create: `payload/tools/make_brief.py`
- Test: `payload/tools/tests/test_make_brief.py`

**Interfaces:**
- Consumes: a work-order dict as produced by Tasks 1–2.
- Produces: `render(wo, part_id)` → `str`.

- [ ] **Step 1: Write the failing tests**

```python
import unittest
import make_brief as mb

WO = {"schema": 1, "plan_id": "wo-20260730-x-abc123", "task": "the whole task",
      "parts": [{"part_id": "p1", "goal": "author the DAG", "role": "data-engineer",
                 "skills": ["airflow-dag-authoring"], "model": "opus", "status": "assigned"}]}

class TestRender(unittest.TestCase):
    def test_identifiers_present(self):
        out = mb.render(WO, "p1")
        self.assertIn("wo-20260730-x-abc123", out)
        self.assertIn("p1", out)

    def test_skills_rendered(self):
        self.assertIn("airflow-dag-authoring", mb.render(WO, "p1"))

    def test_return_schema_demanded(self):
        out = mb.render(WO, "p1")
        self.assertIn("plan_id", out)
        self.assertIn("part_id", out)
        self.assertIn("ok", out)

    def test_grammar_rule_carried(self):
        self.assertIn("grammar", mb.render(WO, "p1").lower())

    def test_unknown_part_raises(self):
        with self.assertRaises(KeyError):
            mb.render(WO, "p9")

    def test_generalist_renders_without_skill_list(self):
        wo = {"schema": 1, "plan_id": "wo-x", "task": "t",
              "parts": [{"part_id": "p1", "goal": "g", "role": "generalist",
                         "skills": [], "model": "session", "status": "assigned"}]}
        out = mb.render(wo, "p1")
        self.assertIn("generalist", out)
```

- [ ] **Step 2: Run to verify failure**
- [ ] **Step 3: Implement `render()`** as a single f-string template.
- [ ] **Step 4: Run to verify pass**
- [ ] **Step 5: Commit**

---

### Task 4: `assess_task.py` — the objective channel

**Files:**
- Create: `payload/tools/assess_task.py`
- Test: `payload/tools/tests/test_assess_task.py`

**Interfaces:**
- Consumes: a work-order dict; the metrics shards at `<metrics_dir>/YYYY-MM.jsonl`.
- Produces: `verdict(evidence)` → `"clean" | "dirty" | "unknown"`; `metrics_for(metrics_dir, agent_task_id)` → `dict | None`; `assess(wo, metrics_dir, repo)` → mutates `part.evidence` and `part.verdict`; `subagents_row(wo, part)` → `str`.

- [ ] **Step 1: Write the failing tests**

```python
import unittest
import assess_task as at

class TestVerdict(unittest.TestCase):
    def test_clean_requires_no_failures_no_reverts_low_errors(self):
        self.assertEqual(at.verdict({"tests_detected": True, "tests_failed": 0,
                                     "reverts": 0, "error_rate": 0.0}), "clean")

    def test_failed_test_forces_dirty(self):
        self.assertEqual(at.verdict({"tests_detected": True, "tests_failed": 3,
                                     "reverts": 0, "error_rate": 0.0}), "dirty")

    def test_revert_forces_dirty(self):
        self.assertEqual(at.verdict({"tests_detected": True, "tests_failed": 0,
                                     "reverts": 1, "error_rate": 0.0}), "dirty")

    def test_high_error_rate_is_dirty(self):
        self.assertEqual(at.verdict({"tests_detected": True, "tests_failed": 0,
                                     "reverts": 0, "error_rate": 0.5}), "dirty")

    def test_no_signal_is_unknown_never_clean(self):
        self.assertEqual(at.verdict({"tests_detected": False, "tests_failed": 0,
                                     "reverts": 0, "error_rate": None}), "unknown")

class TestSubagentsRow(unittest.TestCase):
    def test_row_cites_plan_id_and_verdict(self):
        wo = {"plan_id": "wo-x", "task": "t"}
        part = {"part_id": "p1", "goal": "g", "role": "dba", "verdict": "dirty",
                "evidence": {"tests_failed": 2}}
        row = at.subagents_row(wo, part)
        self.assertIn("wo-x", row)
        self.assertIn("dba", row)
        self.assertTrue(row.startswith("|"))
```

- [ ] **Step 2: Run to verify failure**
- [ ] **Step 3: Implement.** `verdict()` returns `unknown` first when there is no objective signal at all, so a silent task is never scored `clean`. `subagents_row()` returns the markdown row only — it never writes to a client project.
- [ ] **Step 4: Run to verify pass**
- [ ] **Step 5: Commit**

---

### Task 5: Wiring — MANIFEST, registry, resource-loop skill, CHANGELOG

**Files:**
- Modify: `payload/MANIFEST` (three `link-file tools/` lines, alphabetical)
- Modify: `payload/registry/REGISTRY.md` (three tool rows)
- Modify: `payload/skills/resource-loop/SKILL.md` (the new stage sequence)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add the MANIFEST lines** in alphabetical position among the existing `tools/` entries.
- [ ] **Step 2: Add the registry rows** under a `## Tools` heading, then run `python3 ~/.claude/tools/lint_registry.py`. Expected: clean.
- [ ] **Step 3: Update the resource-loop skill** so MATCH → ANNOUNCE → ROUTE becomes DECOMPOSE → ASSIGN → BRIEF → EXECUTE → ASSESS → LEARN, naming the three tools and the brainstorming/writing-plans gate.
- [ ] **Step 4: Run the grammar gate** on every markdown file touched. Expected: `OK (0 issues)` each.
- [ ] **Step 5: Run the full suite** — `bash payload/tools/tests/run_all.sh`. Expected: no FAIL lines.
- [ ] **Step 6: Commit and push.**

---

## Self-Review

**Spec coverage:** Storage and schema → Task 1. Stage 1 DECOMPOSE and the superpowers gate → Task 1. Stage 2 ASSIGN and the model tier table → Task 2. Stage 4 EXECUTE logging → Task 2. Stage 3 BRIEF → Task 3. Stage 5 ASSESS and the `SUBAGENTS.md` proposal row → Task 4. MANIFEST/registry/skill wiring → Task 5.

**Known gap, deliberately deferred:** the spec's Stage 6 `heuristics_eval.py --from-workorder` mode is **not** in this plan. It depends on work orders existing in the store to test against, and adding a `resources_source: "workorder"` branch to the heuristics engine without real rows would be untestable speculation. It lands in a follow-up once the first work orders have accumulated. Every other spec section has a task.

**Type consistency:** `plan_id`, `part_id`, `role`, `skills`, `model`, `status`, `log`, `evidence`, `verdict` are used with the same names and types in Tasks 1–4.
