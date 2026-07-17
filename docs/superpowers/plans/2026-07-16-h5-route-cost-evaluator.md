# H5 route-cost-outlier Evaluator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make H5 (route-cost-outlier) the eighth evaluable rule: derive each task's route tier from its recorded `models` token usage, label task shape at scoring time via a new `score_task.py --task-shape` flag, and fire a theme-note when 2+ mechanical tasks in the last 10 labeled tasks ran on Opus.

**Architecture:** Two small helpers plus one evaluator in `payload/tools/heuristics_eval.py` (mirroring the `_eval_rework_signal` score-joined-window pattern), one optional argparse flag in `payload/tools/score_task.py`, and the seed rulebook's H5 block moved from the Planned lane into the active body. Adding `"H5"` to `EVALUABLE_RULES` is also what makes the drifted LIVE rulebook (`~/.claude/learning/HEURISTICS.md`, where H5 is already ACTIVE) lint-clean — the live file itself is never edited.

**Tech Stack:** Python 3 stdlib only (argparse, json), `unittest` suites run by `payload/tools/tests/run_all.sh`.

**Spec:** `docs/superpowers/specs/2026-07-16-h5-route-cost-evaluator-design.md` (commit b0c521d).

## Global Constraints

- Repo: `~/dev/claude-agent-loop`, branch `feat/h5-route-cost-evaluator`. All paths below are repo-relative.
- The tools under `~/.claude/tools/` are **symlinks into this repo's `payload/tools/`** — the checked-out branch is the live engine. Do not edit `~/.claude/learning/HEURISTICS.md` (a real file, out of scope).
- `DOWNGRADE_RULES` stays exactly `{"H1", "H7"}` — H5 must NOT join it (locked decision).
- Only `"opus"` counts as an H5 hit; `"fable"`/`"mythos"` map to `"session"` and are deliberately NOT outliers.
- `--task-shape` choices are exactly `["planning", "creation", "mechanical"]`; when omitted, the score record has **no** `task_shape` key (never a junk `"unknown"` value).
- Firing metric name is exactly `"mechanical_tasks_routed_to_opus"`; evidence value format is exactly `"mechanical -> <dominant-model-id>"`.
- Commit protocol: every commit body carries `(1) Task & Change` / `(2) Tests created or modified` / `(3) Test results — evidence` with verbatim output, ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Stage explicitly with `git add <paths>`; never `git add -A`.
- Grammar: proofread all prose you emit (comments, docstrings, help text, CHANGELOG copy) — number-aware a/an, subject–verb agreement, no double spaces.
- Test suites use `python3 -m unittest` via `run_all.sh`; run single files as `cd payload/tools/tests && python3 -m unittest test_score_task -v` (module name, no `.py`).
- The shell resets its working directory between commands — prefix every command with `cd /Users/ryanhurst/dev/claude-agent-loop && …` (or the tests directory) as shown.

---

### Task 1: `score_task.py --task-shape` flag

**Files:**
- Modify: `payload/tools/score_task.py` (parser ~line 230-258; record dict ~line 143-155)
- Test: `payload/tools/tests/test_score_task.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: score records optionally carrying a top-level `"task_shape"` key with value `"planning"`, `"creation"`, or `"mechanical"`. Task 2's evaluator reads exactly this key from the joined score record (top level, NOT inside `"scales"`).

- [ ] **Step 1: Write the failing tests**

Append to the `TestScoreTask` class in `payload/tools/tests/test_score_task.py` (the class already provides `self._run(argv)` → `(rc, out, err)`, `self._score_args(*extra)` which appends `--metrics-dir`/`--scales-file`, `self._shard()`, and the module-level `_records(shard)`):

```python
    # --- task shape (H5 route-cost signal) ------------------------------------

    def test_task_shape_flag_lands_on_record(self):
        rc, _, err = self._run(self._score_args(
            "--task-id", "session-shape1",
            "--scale", "outcome=good",
            "--task-shape", "mechanical"))
        self.assertEqual(rc, 0, err)
        score = [r for r in _records(self._shard()) if r["kind"] == "score"][-1]
        self.assertEqual(score["task_shape"], "mechanical")

    def test_task_shape_omitted_leaves_key_absent(self):
        rc, _, err = self._run(self._score_args(
            "--task-id", "session-shape2", "--scale", "outcome=good"))
        self.assertEqual(rc, 0, err)
        score = [r for r in _records(self._shard()) if r["kind"] == "score"][-1]
        self.assertNotIn("task_shape", score)

    def test_task_shape_invalid_value_rejected(self):
        with self.assertRaises(SystemExit) as ctx:
            self._run(self._score_args(
                "--task-id", "session-shape3", "--scale", "outcome=good",
                "--task-shape", "huge"))
        self.assertNotEqual(ctx.exception.code, 0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests && python3 -m unittest test_score_task -v 2>&1 | tail -15`
Expected: the first test FAILS (argparse rejects the unknown `--task-shape` flag → `SystemExit: 2`, surfacing as an error), the second passes trivially, the third passes for the wrong reason (unknown flag also exits 2) — confirm at least one failure mentioning `--task-shape`.

- [ ] **Step 3: Implement the flag**

In `payload/tools/score_task.py`, inside `_build_parser()` (after the existing `--scale`/`--note` arguments — read the span first to place it with its siblings), add:

```python
    ap.add_argument("--task-shape", dest="task_shape",
                    choices=["planning", "creation", "mechanical"],
                    help="how the work was classified when routed (H5 "
                         "route-cost evidence); omit when unclassified")
```

In `_score(args)`, immediately after the `record = { ... }` dict is built (the dict ending with `"resources_deployed": _lookup_resources(args.metrics_dir, task_id),`) and BEFORE `hm._append_record(args.metrics_dir, record)`, add:

```python
    if args.task_shape:
        record["task_shape"] = args.task_shape
```

- [ ] **Step 4: Run the file's suite to verify green**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests && python3 -m unittest test_score_task -v 2>&1 | tail -5`
Expected: `OK` with the full count (all prior cases + 3 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop && \
git add payload/tools/score_task.py payload/tools/tests/test_score_task.py && \
git commit -m "$(cat <<'EOF'
feat(score_task): add the optional --task-shape flag for H5

(1) Task & Change
Task 1 of the H5 route-cost-outlier plan (spec b0c521d, Approach B). Adds an
optional --task-shape {planning,creation,mechanical} argument to
payload/tools/score_task.py. When passed, the score record gains a top-level
"task_shape" key; when omitted, the key is absent, so shards never carry junk
"unknown" values. This is the only new input H5 needs — the route tier is
derived later from the task record's existing "models" field.

(2) Tests created / modified
- payload/tools/tests/test_score_task.py — three new cases:
  test_task_shape_flag_lands_on_record (key present with the given value),
  test_task_shape_omitted_leaves_key_absent (no key when the flag is omitted),
  test_task_shape_invalid_value_rejected (argparse exits non-zero on a value
  outside the three choices).

(3) Test results — evidence
<paste the exact command and the final "Ran N tests ... OK" lines here>

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `_route_tier` / `_eval_route_cost` and engine wiring

**Files:**
- Modify: `payload/tools/heuristics_eval.py` (constants block ~lines 83-102; new functions after `_eval_rework_signal`, which ends ~line 412; dispatch chain in `evaluate_rule` ~lines 507-549)
- Test: `payload/tools/tests/test_heuristics_eval.py` (new test class), `payload/tools/tests/test_lint_heuristics.py` (one new case)

**Interfaces:**
- Consumes: score records whose top-level `"task_shape"` key Task 1 defined.
- Produces: `_dominant_model(rec) -> str | None`, `_route_tier(rec) -> str` (one of `"opus"`, `"sonnet"`, `"haiku"`, `"session"`, `"unknown"`), and `_eval_route_cost(rule, tasks, scores) -> dict | None`, plus `"H5"` membership in `EVALUABLE_RULES` and `GLOBAL_TASK`. Task 3's end-to-end tests rely on the dispatch branch `elif hid == "H5":` and on the firing dict's exact field values below.

- [ ] **Step 1: Write the failing tests**

Append a new test class to `payload/tools/tests/test_heuristics_eval.py` (module already imports `heuristics_eval as he`; module-level `_ts(day)` exists). Add it after the existing `TestHeuristicsEval` class:

```python
class TestRouteCost(unittest.TestCase):
    """Direct unit tests for the H5 helpers and evaluator (no store needed)."""

    @staticmethod
    def _rule():
        # Shape mirrors lint_heuristics.parse_heuristics output for the seed H5.
        return {"id": "H5", "slug": "route-cost-outlier", "then": "theme-note",
                "retired": False, "planned": False,
                "fields": {"WINDOW": "last 10 tasks",
                           "THRESHOLD": "2 or more mechanical tasks routed to Opus",
                           "THEN": "theme-note", "CONFIDENCE": "seed"}}

    @staticmethod
    def _trec(task_id, models):
        return {"schema": 1, "kind": "task", "task_id": task_id,
                "ts_end": _ts(1), "resources_source": "task", "models": models}

    # --- _route_tier / _dominant_model ---------------------------------------

    def test_dominant_model_picks_largest_out(self):
        rec = self._trec("t1", {"claude-opus-4-8": {"out": 100},
                                "claude-sonnet-5": {"out": 5000}})
        self.assertEqual(he._dominant_model(rec), "claude-sonnet-5")
        self.assertEqual(he._route_tier(rec), "sonnet")

    def test_dominant_model_tie_breaks_lexicographically(self):
        rec = self._trec("t1", {"claude-sonnet-5": {"out": 100},
                                "claude-haiku-4-5": {"out": 100}})
        self.assertEqual(he._dominant_model(rec), "claude-haiku-4-5")
        self.assertEqual(he._route_tier(rec), "haiku")

    def test_route_tier_substring_map(self):
        cases = [("claude-opus-4-8", "opus"), ("claude-sonnet-5", "sonnet"),
                 ("claude-haiku-4-5-20251001", "haiku"),
                 ("claude-fable-5", "session"), ("claude-mythos-5", "session"),
                 ("gpt-x", "unknown")]
        for mid, tier in cases:
            rec = self._trec("t1", {mid: {"out": 10}})
            self.assertEqual(he._route_tier(rec), tier, mid)

    def test_route_tier_missing_or_malformed_models(self):
        self.assertEqual(he._route_tier({"task_id": "t1"}), "unknown")
        self.assertEqual(he._route_tier(self._trec("t1", {})), "unknown")
        # A non-numeric "out" counts as 0; the numeric sibling dominates.
        rec = self._trec("t1", {"claude-opus-4-8": {"out": "many"},
                                "claude-sonnet-5": {"out": 1}})
        self.assertEqual(he._route_tier(rec), "sonnet")

    # --- _eval_route_cost ------------------------------------------------------

    def _population(self, shapes_and_models):
        """shapes_and_models: list of (task_shape or None, models dict)."""
        tasks, scores = [], {}
        for i, (shape, models) in enumerate(shapes_and_models, 1):
            tid = "t%d" % i
            tasks.append(self._trec(tid, models))
            score = {"kind": "score", "task_id": tid}
            if shape is not None:
                score["task_shape"] = shape
            scores[tid] = score
        return tasks, scores

    OPUS = {"claude-opus-4-8": {"out": 900}}
    SONNET = {"claude-sonnet-5": {"out": 900}}
    FABLE = {"claude-fable-5": {"out": 900}}

    def test_eval_route_cost_fires_at_two_hits(self):
        rows = [("creation", self.SONNET)] * 8
        rows += [("mechanical", self.OPUS), ("mechanical", self.OPUS)]
        tasks, scores = self._population(rows)
        f = he._eval_route_cost(self._rule(), tasks, scores)
        self.assertIsNotNone(f)
        self.assertEqual(f["rule"], "H5")
        self.assertEqual(f["action"], "theme-note")
        self.assertEqual(f["scope"], "global")
        self.assertEqual(f["metric"], "mechanical_tasks_routed_to_opus")
        self.assertEqual(f["computed"], 2)
        self.assertEqual(f["comparator"], ">=")
        self.assertEqual(f["threshold"], 2)
        self.assertEqual(f["samples"], 10)
        self.assertEqual(f["window"], 10)
        self.assertEqual(f["min_samples"], 2)
        self.assertEqual([e["task_id"] for e in f["evidence"]], ["t9", "t10"])
        self.assertEqual(f["evidence"][0]["value"],
                         "mechanical -> claude-opus-4-8")

    def test_eval_route_cost_one_hit_no_firing(self):
        rows = [("creation", self.SONNET)] * 9 + [("mechanical", self.OPUS)]
        tasks, scores = self._population(rows)
        self.assertIsNone(he._eval_route_cost(self._rule(), tasks, scores))

    def test_eval_route_cost_session_model_not_a_hit(self):
        rows = [("creation", self.SONNET)] * 8
        rows += [("mechanical", self.FABLE), ("mechanical", self.FABLE)]
        tasks, scores = self._population(rows)
        self.assertIsNone(he._eval_route_cost(self._rule(), tasks, scores))

    def test_eval_route_cost_unlabeled_tasks_never_enter_window(self):
        # One labeled task (mechanical + opus): below the 2-sample floor even
        # though it is a hit; the eleven unlabeled/unscored rows do not count.
        rows = [(None, self.OPUS)] * 11 + [("mechanical", self.OPUS)]
        tasks, scores = self._population(rows)
        del scores["t3"]  # an unscored task, not merely an unlabeled one
        self.assertIsNone(he._eval_route_cost(self._rule(), tasks, scores))

    def test_h5_in_evaluable_and_global_sets(self):
        self.assertIn("H5", he.EVALUABLE_RULES)
        self.assertIn("H5", he.GLOBAL_TASK)
        self.assertNotIn("H5", he.DOWNGRADE_RULES)
```

Append one case to the lint suite in `payload/tools/tests/test_lint_heuristics.py`, in the "evaluator integrity (I2a)" section right after `test_active_rule_without_evaluator_flagged` (the module already provides `build_rule(hid=..., slug=..., fields=None)` and `self._lint(text)`):

```python
    def test_active_h5_lints_clean_now_that_evaluator_exists(self):
        # Pins the live-rulebook fix: an ACTIVE H5 block must lint clean
        # because "H5" is now in heuristics_eval.EVALUABLE_RULES.
        errs = self._lint("# Title\n" + build_rule(hid="H5",
                                                   slug="route-cost-outlier"))
        self.assertEqual(errs, [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests && python3 -m unittest test_heuristics_eval.TestRouteCost test_lint_heuristics -v 2>&1 | tail -20`
Expected: every `TestRouteCost` case ERRORS with `AttributeError: module 'heuristics_eval' has no attribute '_dominant_model'` (or `_eval_route_cost`), `test_h5_in_evaluable_and_global_sets` FAILS, and the new lint case FAILS with an "H5 ... evaluator" error string.

- [ ] **Step 3: Implement the helpers, the evaluator, and the wiring**

In `payload/tools/heuristics_eval.py`, first Read lines 80-105, then replace the constants block:

```python
DOWNGRADE_RULES = {"H1", "H7"}
EVALUABLE_RULES = {"H1", "H2", "H3", "H4", "H6", "H7", "H8"}
# Which rules read a per-resource window vs a global task window. H4 is
# session-scoped (bare-match streak, falls back to project-recent). H5 is
# PLANNED (parked in HEURISTICS.md's ## Planned section — no route-tier /
# task-shape signal in the metrics schema yet) and never reaches the engine.
PER_RESOURCE = {"H1", "H7", "H8"}
GLOBAL_TASK = {"H2", "H3", "H6"}
SESSION_RULES = {"H4"}
```

with:

```python
# Downgrade exists only for improve-now rules (coarse evidence softens their
# THEN to theme-note); H5 is theme-note by design and must NOT join this set.
DOWNGRADE_RULES = {"H1", "H7"}
EVALUABLE_RULES = {"H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8"}
# Which rules read a per-resource window vs a global task window. H4 is
# session-scoped (bare-match streak, falls back to project-recent). H5 is
# global: its route tier is derived from each task record's ``models`` field
# (dominant model by ``out`` tokens) and its task shape from the joined score
# record's ``task_shape`` key (score_task.py --task-shape).
PER_RESOURCE = {"H1", "H7", "H8"}
GLOBAL_TASK = {"H2", "H3", "H5", "H6"}
SESSION_RULES = {"H4"}
```

Then insert the following immediately AFTER the end of `_eval_rework_signal` (the function ending with the `"evidence": [_ev_row(r, "rework=major") for r in majors],` return, ~line 412):

```python
_KNOWN_SHAPES = {"planning", "creation", "mechanical"}
_TIER_MAP = (("opus", "opus"), ("sonnet", "sonnet"), ("haiku", "haiku"),
             ("fable", "session"), ("mythos", "session"))


def _dominant_model(rec):
    """The model id with the largest ``out`` token count on this task record.

    Missing or non-numeric ``out`` counts as 0; ties break lexicographically
    by model id so the result is deterministic. Returns None when the record
    has no usable ``models`` dict.
    """
    models = rec.get("models") or {}
    if not isinstance(models, dict) or not models:
        return None

    def _out(mid):
        usage = models.get(mid)
        val = usage.get("out") if isinstance(usage, dict) else None
        return val if isinstance(val, (int, float)) else 0

    return sorted(models, key=lambda m: (-_out(m), str(m)))[0]


def _route_tier(rec):
    """Map a task record's dominant model to a route tier.

    Substring match, first hit wins: opus / sonnet / haiku, then fable or
    mythos -> "session" (a subagent inheriting the session model is not a
    per-dispatch routing decision). Anything else -> "unknown". Only "opus"
    ever counts as an H5 hit.
    """
    mid = _dominant_model(rec)
    if mid is None:
        return "unknown"
    low = str(mid).lower()
    for needle, tier in _TIER_MAP:
        if needle in low:
            return tier
    return "unknown"


def _eval_route_cost(rule, tasks, scores):
    """H5 route-cost-outlier (global): mechanical-shaped tasks whose dominant
    model was Opus, over the last N tasks the owner labeled with a shape at
    scoring time. Unscored or unlabeled tasks never enter the window, so they
    can neither fire the rule nor pad the sample floor.
    """
    _cmp_op, count = parse_threshold(rule["fields"]["THRESHOLD"])
    window, explicit_min = parse_window(rule["fields"]["WINDOW"])
    labeled = [r for r in tasks
               if (scores.get(r.get("task_id")) or {}).get("task_shape")
               in _KNOWN_SHAPES]
    win = labeled[-window:] if window else labeled
    need = _min_samples(window, explicit_min, count_threshold=count)
    if len(win) < need:
        return None
    hits = [r for r in win
            if scores[r["task_id"]].get("task_shape") == "mechanical"
            and _route_tier(r) == "opus"]
    if len(hits) < count:
        return None
    return {
        "rule": rule["id"], "action": rule["then"], "scope": "global",
        "metric": "mechanical_tasks_routed_to_opus", "computed": len(hits),
        "comparator": ">=", "threshold": int(count),
        "samples": len(win), "window": window, "min_samples": need,
        "coarse_samples": _coarse_count(hits),
        "precise_samples": _precise_count(hits),
        "evidence": [_ev_row(r, "mechanical -> %s" % _dominant_model(r))
                     for r in hits],
    }
```

Then wire the dispatch: in `evaluate_rule`, insert this branch between the existing `elif hid == "H3":` block and the `elif hid == "H7":` block:

```python
        elif hid == "H5":
            f = _eval_route_cost(rule, ctx.tasks, ctx.scores)
            if f:
                out.append(f)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests && python3 -m unittest test_heuristics_eval test_lint_heuristics -v 2>&1 | tail -8`
Expected: `OK` for both modules — all pre-existing cases (including `test_parse_seed_returns_seven_active_and_one_planned`, still valid because the seed is untouched in this task) plus the new ones.

- [ ] **Step 5: Commit**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop && \
git add payload/tools/heuristics_eval.py payload/tools/tests/test_heuristics_eval.py payload/tools/tests/test_lint_heuristics.py && \
git commit -m "$(cat <<'EOF'
feat(heuristics_eval): add the H5 route-cost-outlier evaluator

(1) Task & Change
Task 2 of the H5 plan (spec b0c521d). Adds _dominant_model / _route_tier
(dominant model by "out" tokens, lexicographic tie-break, substring tier map
where only "opus" is an H5 hit and fable/mythos are the session tier) and
_eval_route_cost (global, mirrors the _eval_rework_signal score-joined-window
pattern; unlabeled tasks never enter the window). Wires H5 into
EVALUABLE_RULES, GLOBAL_TASK, and the evaluate_rule dispatch; DOWNGRADE_RULES
stays {"H1", "H7"} with a guard comment. Adding H5 to EVALUABLE_RULES is what
makes the drifted live rulebook lint-clean with no live-file edit.

(2) Tests created / modified
- payload/tools/tests/test_heuristics_eval.py — new TestRouteCost class:
  dominant-by-out selection, lexicographic tie-break, the full substring map,
  malformed/missing models, evaluator fires at 2 hits with the exact firing
  fields, one hit no firing, session model not a hit, unlabeled tasks below
  the sample floor, and H5 set membership.
- payload/tools/tests/test_lint_heuristics.py — new case: an ACTIVE H5 block
  lints clean now that the evaluator exists (pins the live-rulebook fix).

(3) Test results — evidence
<paste the exact command and the final "Ran N tests ... OK" lines here>

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Seed rulebook activation, end-to-end tests, and the CHANGELOG entry

**Files:**
- Modify: `payload/learning/HEURISTICS.md` (move H5 active; delete the Planned section)
- Modify: `payload/tools/tests/test_lint_heuristics.py` (update the seed-count test, ~lines 51-60)
- Modify: `payload/tools/tests/test_heuristics_eval.py` (extend the `_task`/`_score` helpers; add end-to-end H5 cases)
- Modify: `CHANGELOG.md` (new Unreleased section)

**Interfaces:**
- Consumes: Task 2's dispatch branch and evaluator, and Task 1's `task_shape` record key.
- Produces: a seed rulebook with eight active rules and no Planned section — which `test_heuristics_eval.py` (whose `_run_json` always points `--heuristics-file` at the seed) needs before H5 can fire end to end.

- [ ] **Step 1: Update the seed-count lint test (it will fail once the seed changes — flip it first, TDD-style)**

In `payload/tools/tests/test_lint_heuristics.py`, replace (read lines 45-65 first; the test currently asserts seven active and one planned):

```python
        self.assertEqual([r["id"] for r in active],
                         ["H1", "H2", "H3", "H4", "H6", "H7", "H8"])
        self.assertEqual([r["id"] for r in planned], ["H5"])
```

with:

```python
        self.assertEqual([r["id"] for r in active],
                         ["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8"])
        self.assertEqual([r["id"] for r in planned], [])
```

and rename the test method from `test_parse_seed_returns_seven_active_and_one_planned` to `test_parse_seed_returns_eight_active_and_none_planned`. Keep the rest of the method body (the `by_id` THEN-token assertions) unchanged. If the module docstring or a comment near it still describes the seed as "seven active + one planned", update that wording to "eight active" as well.

- [ ] **Step 2: Write the failing end-to-end tests**

In `payload/tools/tests/test_heuristics_eval.py`, extend the two planting helpers in `TestHeuristicsEval` (exact current signatures shown; add only the new keyword-only behavior):

`_task` — change the signature line to

```python
    def _task(self, task_id, day, resources=None, error_rate=0.0,
              cache=0.85, interrupted=0, failed=0, source="task", models=None):
```

and, just before `hm._append_record(str(self.metrics), rec)`, add:

```python
        if models is not None:
            rec["models"] = models
```

`_score` — replace the helper with:

```python
    def _score(self, task_id, day, outcome="good", rework="none",
               task_shape=None):
        rec = {
            "schema": 1, "kind": "score", "task_id": task_id,
            "project": "demo_project", "ts_end": _ts(day),
            "scales": {"outcome": outcome, "rework": rework},
        }
        if task_shape is not None:
            rec["task_shape"] = task_shape
        hm._append_record(str(self.metrics), rec)
```

Then add these cases inside `TestHeuristicsEval`, after the existing H7/H8 sections:

```python
    # --- H5 route-cost-outlier ------------------------------------------------

    _OPUS = {"claude-opus-4-8": {"in": 100, "out": 900}}
    _SONNET = {"claude-sonnet-5": {"in": 100, "out": 900}}
    _FABLE = {"claude-fable-5": {"in": 100, "out": 900}}

    def _plant_labeled(self, shapes_models):
        """shapes_models: list of (task_shape or None, models dict or None)."""
        for i, (shape, models) in enumerate(shapes_models, 1):
            tid = "t%d" % i
            self._task(tid, min(i, 28), models=models)
            if shape is not None:
                self._score(tid, min(i, 28), task_shape=shape)

    def test_h5_fires_end_to_end_with_theme_note(self):
        rows = [("creation", self._SONNET)] * 8
        rows += [("mechanical", self._OPUS), ("mechanical", self._OPUS)]
        self._plant_labeled(rows)
        rc, payload, err = self._run_json([])
        self.assertEqual(rc, 0, err)
        fired = self._fired(payload)
        self.assertIn("H5", fired)
        f = fired["H5"]
        self.assertEqual(f["computed"], 2)
        self.assertEqual(f["metric"], "mechanical_tasks_routed_to_opus")
        self.assertEqual(f["action"], "theme-note")
        self.assertEqual(f["effective_action"], "theme-note")
        self.assertEqual(f["scope"], "global")
        self.assertEqual([e["task_id"] for e in f["evidence"]], ["t9", "t10"])
        self.assertEqual(f["evidence"][0]["value"],
                         "mechanical -> claude-opus-4-8")

    def test_h5_below_threshold_does_not_fire(self):
        rows = [("creation", self._SONNET)] * 9 + [("mechanical", self._OPUS)]
        self._plant_labeled(rows)
        rc, payload, err = self._run_json([])
        self.assertEqual(rc, 0, err)
        self.assertNotIn("H5", self._fired(payload))

    def test_h5_session_model_mechanical_not_a_hit(self):
        rows = [("creation", self._SONNET)] * 8
        rows += [("mechanical", self._FABLE), ("mechanical", self._FABLE)]
        self._plant_labeled(rows)
        rc, payload, err = self._run_json([])
        self.assertEqual(rc, 0, err)
        self.assertNotIn("H5", self._fired(payload))

    def test_h5_unlabeled_tasks_excluded_from_window(self):
        # Eleven unlabeled tasks plus a single labeled mechanical+opus task:
        # only the labeled one enters the population, which is below the
        # 2-sample floor, so H5 stays quiet even though the one row is a hit.
        rows = [(None, self._OPUS)] * 11 + [("mechanical", self._OPUS)]
        self._plant_labeled(rows)
        rc, payload, err = self._run_json([])
        self.assertEqual(rc, 0, err)
        self.assertNotIn("H5", self._fired(payload))
```

- [ ] **Step 3: Run the new tests to verify they fail for the right reason**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests && python3 -m unittest test_heuristics_eval.TestHeuristicsEval.test_h5_fires_end_to_end_with_theme_note test_lint_heuristics -v 2>&1 | tail -12`
Expected: the H5 end-to-end test FAILS (`'H5' not found in ...` — the seed still parses H5 as PLANNED, so the engine skips it) and the renamed lint test FAILS (the seed still has seven active and one planned).

- [ ] **Step 4: Edit the seed rulebook**

In `payload/learning/HEURISTICS.md`, make two edits.

Edit A — insert the active H5 block between H4 and H6. Replace:

```
- LAST-REVIEWED: 2026-07-07

## H6 — cache-efficiency-floor
```

with:

```
- LAST-REVIEWED: 2026-07-07

## H5 — route-cost-outlier
- WHEN: a task classified as mechanical work is routed to the Opus model tier
- WINDOW: last 10 tasks
- THRESHOLD: 2 or more mechanical tasks routed to Opus
- THEN: theme-note
- CONFIDENCE: seed
- LAST-REVIEWED: 2026-07-16
- NOTE: the route tier is derived from the task record's `models` field (dominant model by `out` tokens); the task shape comes from `score_task.py --task-shape`; tasks without a shape label are ignored

## H6 — cache-efficiency-floor
```

Edit B — delete the whole Planned section (header, its two explanatory lines, and the old H5 block) at the end of the file. Replace:

```
## Planned (not yet computable)

These rules are fully specified but their metric is not in the store yet, so the
engine parses them as PLANNED and never evaluates them. Their ids stay reserved.

## H5 — route-cost-outlier
- WHEN: a task classified as mechanical work is routed to the Opus model tier
- WINDOW: last 10 tasks
- THRESHOLD: 2 or more mechanical tasks routed to Opus
- THEN: theme-note
- CONFIDENCE: seed
- LAST-REVIEWED: 2026-07-07
- NOTE: needs a task-shape/route-tier field at ANNOUNCE time — not in the metrics schema yet
```

with nothing (also remove the now-dangling blank line so the file ends cleanly after the H8 block with a single trailing newline).

- [ ] **Step 5: Add the CHANGELOG entry**

In `CHANGELOG.md`, insert directly above the line `## [2.0.0] - 2026-07-07`:

```markdown
## [Unreleased]

### Added
- `score_task.py --task-shape {planning,creation,mechanical}` — an optional
  scoring-time label; when omitted, the score record carries no `task_shape`
  key at all.
- The H5 (route-cost-outlier) evaluator in `heuristics_eval.py`: the route
  tier is derived from each task record's `models` field (dominant model by
  `out` tokens; only Opus is a hit, and the session tier never is), joined to
  the score's `task_shape`. H5 is now the eighth evaluable rule, which also
  makes rulebooks with an ACTIVE H5 lint-clean.

### Changed
- Seed `learning/HEURISTICS.md`: H5 moved from the "Planned (not yet
  computable)" lane into the active body; the emptied Planned section was
  removed.

```

(Keep one blank line between the new section and the `## [2.0.0]` heading.)

- [ ] **Step 6: Run both suites to verify green**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests && python3 -m unittest test_heuristics_eval test_lint_heuristics -v 2>&1 | tail -6`
Expected: `OK` for both modules — the four end-to-end H5 cases pass, the renamed seed test passes with eight active ids, and `test_seed_file_passes` still passes (the linter accepts the edited seed).

- [ ] **Step 7: Commit**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop && \
git add payload/learning/HEURISTICS.md payload/tools/tests/test_heuristics_eval.py payload/tools/tests/test_lint_heuristics.py CHANGELOG.md && \
git commit -m "$(cat <<'EOF'
feat(rulebook): activate H5 in the seed and prove it end to end

(1) Task & Change
Task 3 of the H5 plan (spec b0c521d). Moves the seed H5 block out of the
"Planned (not yet computable)" lane into the active body (between H4 and H6,
LAST-REVIEWED 2026-07-16, NOTE rewritten around the derived route tier and the
--task-shape label) and deletes the emptied Planned section. Updates the
seed-count lint test to eight active / zero planned, extends the
test_heuristics_eval planting helpers with models/task_shape, and adds four
end-to-end H5 cases driven through the real seed. Adds the CHANGELOG
Unreleased entry for the feature.

(2) Tests created / modified
- payload/tools/tests/test_heuristics_eval.py — _task gains models=, _score
  gains task_shape=; new end-to-end cases: H5 fires with theme-note and exact
  evidence, below threshold quiet, session-model mechanical not a hit,
  unlabeled tasks excluded from the window.
- payload/tools/tests/test_lint_heuristics.py — seed test renamed to
  test_parse_seed_returns_eight_active_and_none_planned with the updated
  expectations; test_seed_file_passes now covers the edited seed.

(3) Test results — evidence
<paste the exact command and the final "Ran N tests ... OK" lines here>

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Final verification (no file changes)

**Files:**
- None. This task runs the acceptance evidence end to end.

**Interfaces:**
- Consumes: everything from Tasks 1-3.
- Produces: recorded evidence that the full suite is green and that the lint passes against BOTH rulebooks (the repo seed and the drifted live file), which is the spec's acceptance bar.

- [ ] **Step 1: Full suite**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests && bash run_all.sh > /tmp/h5_run_all.log 2>&1; echo "exit=$?"; tail -5 /tmp/h5_run_all.log`
Expected: `exit=0` and a final summary line reporting 0 failures across all suites.

- [ ] **Step 2: Lint the repo seed**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop && python3 payload/tools/lint_heuristics.py payload/learning/HEURISTICS.md`
Expected: `lint_heuristics: OK (0 error(s))`, exit 0.

- [ ] **Step 3: Lint the LIVE rulebook (the standing failure this branch fixes)**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop && python3 payload/tools/lint_heuristics.py ~/.claude/learning/HEURISTICS.md`
Expected: `lint_heuristics: OK (0 error(s))`, exit 0 — the live file was NOT edited; it goes green purely because "H5" is now in `EVALUABLE_RULES`. If this still fails, the failure lines are the finding — do not edit the live file to make it pass.

- [ ] **Step 4: No commit**

This task changes no files; its output is the evidence above (quote the decisive lines with the `/tmp/h5_run_all.log` path). When it passes, the branch's purpose is complete: proceed to the final whole-branch review and then superpowers:finishing-a-development-branch (push and open a PR against main summarizing spec + Tasks 1-3).

---

## Self-Review

**1. Spec coverage.** Data model → Task 1 (flag + absent-key semantics) and Task 2 (`_dominant_model`/`_route_tier` with the exact tie-break and substring map). Evaluator algorithm steps 1-6 → Task 2 (`_eval_route_cost` uses the exact `rule["fields"]["THRESHOLD"]`/`rule["fields"]["WINDOW"]` access, the labeled population, `_min_samples`, the hit test, the standard firing dict, and the dispatch branch). Set and comment updates → Task 2 Step 3 (EVALUABLE_RULES, GLOBAL_TASK, the DOWNGRADE_RULES guard comment, the rewritten scope-sets block). Seed rulebook update → Task 3 Step 4 (both edits verbatim, LAST-REVIEWED 2026-07-16, Planned section deleted). Live-file no-edit invariant → Global Constraints + Task 4 Step 3. Testing plan: all six heuristics_eval cases (route-tier unit coverage in Task 2; fire/no-fire/unlabeled/session-model/effective_action end to end in Task 3), all three score_task cases (Task 1), and the lint regression (Task 2). Acceptance evidence → Task 4. Out-of-scope items appear nowhere in the tasks. The one addition beyond the spec is the CHANGELOG entry (house convention for this repo) and the required update of the pre-existing seed-count lint test the seed edit breaks — both folded into Task 3.

**2. Placeholder scan.** No TBD/TODO/"implement later"; every code step carries complete code; commands carry expected output. The one intentional non-literal spot is the evidence-paste markers inside commit bodies (`<paste the exact command ...>` — filled at commit time per the commit protocol, never left verbatim). The Task 2 lint-test case was verified against the real helpers in `test_lint_heuristics.py` (`build_rule(hid=..., slug=...)`, `self._lint`, the `"# Title\n"` prefix) — no hedges remain.

**3. Type consistency.** `task_shape` is a top-level score-record key everywhere (Task 1 implementation, Task 2 direct tests, Task 3 helper and end-to-end tests) — never inside `scales`. `_dominant_model` returns `str | None`; `_route_tier` returns one of five strings; `_eval_route_cost(rule, tasks, scores)` matches the dispatch call `_eval_route_cost(rule, ctx.tasks, ctx.scores)`. The metric string, evidence format, and firing fields are identical in Task 2's implementation, Task 2's direct assertions, and Task 3's end-to-end assertions. The Task 3 day values pass `min(i, 28)` so `_ts` never builds an invalid day-of-month for 12-item populations.
