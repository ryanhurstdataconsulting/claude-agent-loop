"""Tests for heuristics_eval — the heuristic-scoring engine (P6).

Written TDD-first: imports ``heuristics_eval`` before it exists (RED). Fixtures
are synthetic metric records planted in a temp metrics dir via
``harvest_metrics._append_record`` (the same append path the harvester uses), so
the store contract — dedupe to the LAST record per ``(task_id, kind)`` before any
aggregation — is exercised end to end. Rules are read from the shipped seed
``learning/HEURISTICS.md`` so the thresholds under test are the real ones.

This is heuristic scoring over recorded metrics, NOT model training.
"""
import datetime
import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import heuristics_eval as he  # noqa: E402
import harvest_metrics as hm  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_HEUR = ROOT / "learning" / "HEURISTICS.md"
SEED_SCALES = ROOT / "learning" / "SCALES.md"

_NOW = datetime.datetime.now(datetime.timezone.utc)


def _ts(day, hour=0):
    """An ISO ts_end in the CURRENT month (so load_metrics' shard scan sees it).

    ``day`` is 1..28 (valid in every month, February included); increasing day
    gives a deterministic time order for streak windows.
    """
    return "%04d-%02d-%02dT%02d:00:00Z" % (_NOW.year, _NOW.month, day, hour)


class TestHeuristicsEval(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.metrics = pathlib.Path(self.td.name) / "metrics"
        self.metrics.mkdir()

    # --- planting helpers ----------------------------------------------------

    def _task(self, task_id, day, resources=None, error_rate=0.0,
              cache=0.85, interrupted=0, failed=0, source="task"):
        # cache defaults high and error/interrupt/fail default clean so an
        # isolated rule under test is the only thing that can fire. Passing
        # ``cache=None`` OMITS the cache_efficiency field entirely (used to
        # prove the mean rules exclude records missing the metric — M1).
        rec = {
            "schema": 1, "kind": "task", "task_id": task_id,
            "project": "demo_project", "ts_end": _ts(day),
            "resources_deployed": resources or [], "resources_source": source,
            "error_rate": error_rate,
            "interrupted": interrupted, "tests": {"failed": failed, "passed": 1},
        }
        if cache is not None:
            rec["cache_efficiency"] = cache
        hm._append_record(str(self.metrics), rec)

    def _score(self, task_id, day, outcome="good", rework="none"):
        hm._append_record(str(self.metrics), {
            "schema": 1, "kind": "score", "task_id": task_id,
            "project": "demo_project", "ts_end": _ts(day),
            "scales": {"outcome": outcome, "rework": rework},
        })

    def _bare(self, task_id, day, session_id, project="demo_project"):
        # A "proceeding bare" announcement record (H4 counts these). Planted as
        # a kind:"session" row so it never lands in the kind:"task" population
        # the other rules read.
        hm._append_record(str(self.metrics), {
            "schema": 1, "kind": "session", "task_id": task_id,
            "project": project, "ts_end": _ts(day),
            "bare": True, "session_id": session_id,
            "resources_deployed": [], "resources_source": "session",
        })

    def _run_json(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = he.main(argv + ["--metrics-dir", str(self.metrics),
                                  "--heuristics-file", str(SEED_HEUR),
                                  "--scales-file", str(SEED_SCALES), "--json"])
        return rc, json.loads(out.getvalue()), err.getvalue()

    def _run_text(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = he.main(argv + ["--metrics-dir", str(self.metrics),
                                  "--heuristics-file", str(SEED_HEUR),
                                  "--scales-file", str(SEED_SCALES)])
        return rc, out.getvalue(), err.getvalue()

    def _fired(self, payload):
        return {f["rule"]: f for f in payload["firings"]}

    # --- H1 resource-error-spike --------------------------------------------

    def test_h1_fires_over_threshold_with_min_samples(self):
        # 5 tasks deploying demo-res, mean error_rate 0.46 > 0.25, one backfilled.
        rates = [0.5, 0.4, 0.3, 0.6, 0.5]
        for i, r in enumerate(rates, 1):
            src = "session-backfill" if i == 2 else "task"
            self._task("agent-%d" % i, i, resources=["demo-res"],
                       error_rate=r, source=src)
        rc, payload, _ = self._run_json(["--task-id", "agent-1"])
        self.assertEqual(rc, 0)
        fired = self._fired(payload)
        self.assertIn("H1", fired)
        h1 = fired["H1"]
        self.assertEqual(h1["action"], "improve-now")
        self.assertGreater(h1["computed"], 0.25)
        self.assertEqual(h1["samples"], 5)
        # The session-backfill sample is annotated coarse in the evidence.
        coarse = [e for e in h1["evidence"] if e["coarse"]]
        self.assertEqual(len(coarse), 1)
        self.assertEqual(coarse[0]["resources_source"], "session-backfill")

    def test_h1_does_not_fire_just_under_threshold(self):
        for i in range(1, 6):
            self._task("agent-%d" % i, i, resources=["demo-res"], error_rate=0.20)
        rc, payload, _ = self._run_json(["--task-id", "agent-1"])
        self.assertEqual(rc, 0)
        self.assertNotIn("H1", self._fired(payload))

    def test_h1_does_not_fire_with_too_few_samples(self):
        # 4 high-error tasks — below H1's minimum sample count → no fire.
        for i in range(1, 5):
            self._task("agent-%d" % i, i, resources=["demo-res"], error_rate=0.9)
        rc, payload, _ = self._run_json(["--task-id", "agent-1"])
        self.assertEqual(rc, 0)
        self.assertNotIn("H1", self._fired(payload))

    def test_last_record_per_task_kind_dedupe_honored(self):
        # agent-1 planted twice: a stale high-error record then a current clean
        # one. Deduped mean stays under threshold; counting the stale record
        # would push it over — so a firing here proves the dedupe failed.
        self._task("agent-1", 1, resources=["demo-res"], error_rate=0.9)   # stale
        self._task("agent-1", 2, resources=["demo-res"], error_rate=0.0)   # wins
        for i in range(2, 6):
            self._task("agent-%d" % i, i + 2, resources=["demo-res"],
                       error_rate=0.2)
        rc, payload, _ = self._run_json(["--task-id", "agent-1"])
        self.assertEqual(rc, 0)
        self.assertNotIn("H1", self._fired(payload))

    # --- H3 test-fail-streak -------------------------------------------------

    def test_h3_fires_on_three_consecutive_failing_tasks(self):
        for i in range(1, 4):
            self._task("agent-f%d" % i, i, failed=2)
        rc, payload, _ = self._run_json(["--window"])
        self.assertEqual(rc, 0)
        fired = self._fired(payload)
        self.assertIn("H3", fired)
        self.assertEqual(fired["H3"]["action"], "theme-note")
        self.assertGreaterEqual(fired["H3"]["computed"], 3)

    def test_h3_does_not_fire_below_streak(self):
        for i in range(1, 3):     # only two failing tasks
            self._task("agent-f%d" % i, i, failed=1)
        rc, payload, _ = self._run_json(["--window"])
        self.assertEqual(rc, 0)
        self.assertNotIn("H3", self._fired(payload))

    # --- H8 positive-streak --------------------------------------------------

    def test_h8_fires_on_eight_clean_scored_tasks(self):
        for i in range(1, 9):
            self._task("agent-s%d" % i, i, resources=["streak-res"])
            self._score("agent-s%d" % i, i, outcome="good", rework="none")
        rc, payload, _ = self._run_json(["--task-id", "agent-s1"])
        self.assertEqual(rc, 0)
        fired = self._fired(payload)
        self.assertIn("H8", fired)
        self.assertEqual(fired["H8"]["action"], "no-action")

    def test_h8_does_not_fire_when_a_task_reworked(self):
        for i in range(1, 9):
            rework = "major" if i == 4 else "none"
            self._task("agent-s%d" % i, i, resources=["streak-res"])
            self._score("agent-s%d" % i, i, outcome="good", rework=rework)
        rc, payload, _ = self._run_json(["--task-id", "agent-s1"])
        self.assertEqual(rc, 0)
        self.assertNotIn("H8", self._fired(payload))

    # --- no rules fire -------------------------------------------------------

    def test_no_rules_fire_prints_cleanly(self):
        self._task("agent-1", 1, resources=["demo-res"], error_rate=0.0)
        rc, out, _ = self._run_text(["--window"])
        self.assertEqual(rc, 0)
        self.assertIn("no rules fired", out.lower())

    def test_empty_metrics_no_fire(self):
        rc, out, _ = self._run_text(["--window"])
        self.assertEqual(rc, 0)
        self.assertIn("no rules fired", out.lower())

    # --- --emit-learn --------------------------------------------------------

    def test_emit_learn_writes_learn_record(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = he.main(["--emit-learn", "theme-note", "--rule", "H3",
                          "--task-id", "agent-x",
                          "--metrics-dir", str(self.metrics)])
        self.assertEqual(rc, 0, err.getvalue())
        shard = sorted(self.metrics.glob("*.jsonl"))[-1]
        recs = [json.loads(ln) for ln in shard.read_text().splitlines()
                if ln.strip()]
        learn = [r for r in recs if r["kind"] == "learn"]
        self.assertEqual(len(learn), 1)
        self.assertEqual(learn[0]["action"], "theme-note")
        self.assertEqual(learn[0]["rule"], "H3")
        self.assertEqual(learn[0]["task_id"], "agent-x")
        self.assertEqual(learn[0]["schema"], 1)
        self.assertIn("ts_end", learn[0])

    def test_emit_learn_records_no_action_as_positive_signal(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = he.main(["--emit-learn", "no-action", "--rule", "H8",
                          "--task-id", "agent-y",
                          "--metrics-dir", str(self.metrics)])
        self.assertEqual(rc, 0, err.getvalue())
        shard = sorted(self.metrics.glob("*.jsonl"))[-1]
        recs = [json.loads(ln) for ln in shard.read_text().splitlines()
                if ln.strip()]
        self.assertTrue(any(r["kind"] == "learn" and r["action"] == "no-action"
                            for r in recs))

    def test_emit_learn_bad_action_exits_2(self):
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = he.main(["--emit-learn", "bogus", "--rule", "H1",
                          "--task-id", "agent-x",
                          "--metrics-dir", str(self.metrics)])
        self.assertEqual(rc, 2)

    def test_emit_learn_missing_task_id_exits_2(self):
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = he.main(["--emit-learn", "no-action", "--rule", "H1",
                          "--metrics-dir", str(self.metrics)])
        self.assertEqual(rc, 2)

    # --- programmer errors ---------------------------------------------------

    def test_missing_heuristics_file_exits_2(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = he.main(["--task-id", "agent-1",
                          "--metrics-dir", str(self.metrics),
                          "--heuristics-file", "/nonexistent/HEURISTICS.md",
                          "--scales-file", str(SEED_SCALES)])
        self.assertEqual(rc, 2)

    def test_no_mode_exits_2(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = he.main(["--metrics-dir", str(self.metrics),
                          "--heuristics-file", str(SEED_HEUR),
                          "--scales-file", str(SEED_SCALES)])
        self.assertEqual(rc, 2)

    # --- C1 coarse-evidence downgrade (H1) -----------------------------------

    def test_h1_all_backfill_downgraded_to_theme_note(self):
        # 5 tasks deploying demo-res at error 0.9 — ALL session-backfill. H1
        # crosses the mean threshold, but session-backfill does NOT establish
        # demo-res actually ran on these tasks, so the autonomous improve-now is
        # downgraded to theme-note.
        for i in range(1, 6):
            self._task("agent-%d" % i, i, resources=["demo-res"],
                       error_rate=0.9, source="session-backfill")
        rc, payload, _ = self._run_json(["--task-id", "agent-1"])
        self.assertEqual(rc, 0)
        h1 = self._fired(payload)["H1"]
        self.assertEqual(h1["action"], "improve-now")           # raw THEN kept
        self.assertEqual(h1["effective_action"], "theme-note")  # downgraded
        self.assertTrue(h1["downgrade_reason"])
        self.assertIn("coarse-dominated", h1["downgrade_reason"])
        # NOT recommended as an autonomous improve-now.
        self.assertNotEqual(payload["firings"][0]["effective_action"],
                            "improve-now")

    def test_h1_precise_over_threshold_stays_improve_now(self):
        # 5 precise (task-sourced) high-error tasks → improve-now survives.
        for i in range(1, 6):
            self._task("agent-%d" % i, i, resources=["demo-res"],
                       error_rate=0.9, source="task")
        rc, payload, _ = self._run_json(["--task-id", "agent-1"])
        self.assertEqual(rc, 0)
        h1 = self._fired(payload)["H1"]
        self.assertEqual(h1["effective_action"], "improve-now")
        self.assertIsNone(h1["downgrade_reason"])
        self.assertEqual(h1["precise_samples"], 5)

    def test_h1_coarse_just_under_line_stays_improve_now(self):
        # 4 precise + 3 coarse (7 rows): coarse 3/7 ~= 0.43 <= 0.50, precise
        # 4 >= 3 → improve-now survives.
        for i in range(1, 5):
            self._task("agent-%d" % i, i, resources=["demo-res"],
                       error_rate=0.9, source="task")
        for i in range(5, 8):
            self._task("agent-%d" % i, i, resources=["demo-res"],
                       error_rate=0.9, source="session-backfill")
        rc, payload, _ = self._run_json(["--task-id", "agent-1"])
        self.assertEqual(rc, 0)
        h1 = self._fired(payload)["H1"]
        self.assertEqual(h1["effective_action"], "improve-now")
        self.assertIsNone(h1["downgrade_reason"])

    def test_h1_coarse_just_over_line_downgraded(self):
        # 3 precise + 4 coarse (7 rows): coarse 4/7 ~= 0.57 > 0.50 → downgrade
        # even though precise (3) meets the floor.
        for i in range(1, 4):
            self._task("agent-%d" % i, i, resources=["demo-res"],
                       error_rate=0.9, source="task")
        for i in range(4, 8):
            self._task("agent-%d" % i, i, resources=["demo-res"],
                       error_rate=0.9, source="session-backfill")
        rc, payload, _ = self._run_json(["--task-id", "agent-1"])
        self.assertEqual(rc, 0)
        h1 = self._fired(payload)["H1"]
        self.assertEqual(h1["effective_action"], "theme-note")
        self.assertIn("coarse-dominated", h1["downgrade_reason"])
        self.assertEqual(h1["precise_samples"], 3)

    # --- H2 interrupt-pressure boundary (I4) ---------------------------------

    def test_h2_interrupt_ratio_fires_just_over_boundary(self):
        # 10 tasks, 4 interrupted → ratio 0.40 > 0.30.
        for i in range(1, 11):
            self._task("agent-i%d" % i, i, interrupted=1 if i <= 4 else 0)
        rc, payload, _ = self._run_json(["--window"])
        self.assertEqual(rc, 0)
        h2 = self._fired(payload)["H2"]
        self.assertEqual(h2["action"], "theme-note")
        self.assertAlmostEqual(h2["computed"], 0.4)

    def test_h2_interrupt_ratio_does_not_fire_at_boundary(self):
        # 10 tasks, 3 interrupted → ratio 0.30, NOT > 0.30.
        for i in range(1, 11):
            self._task("agent-i%d" % i, i, interrupted=1 if i <= 3 else 0)
        rc, payload, _ = self._run_json(["--window"])
        self.assertEqual(rc, 0)
        self.assertNotIn("H2", self._fired(payload))

    # --- H6 cache-efficiency floor (I4 + M1) ---------------------------------

    def test_h6_fires_below_cache_floor(self):
        for i in range(1, 11):
            self._task("agent-c%d" % i, i, cache=0.4)
        rc, payload, _ = self._run_json(["--window"])
        self.assertEqual(rc, 0)
        h6 = self._fired(payload)["H6"]
        self.assertEqual(h6["action"], "theme-note")
        self.assertAlmostEqual(h6["computed"], 0.4)

    def test_h6_does_not_fire_above_cache_floor(self):
        for i in range(1, 11):
            self._task("agent-c%d" % i, i, cache=0.6)
        rc, payload, _ = self._run_json(["--window"])
        self.assertEqual(rc, 0)
        self.assertNotIn("H6", self._fired(payload))

    def test_h6_excludes_records_missing_cache_efficiency(self):
        # 5 healthy readings (0.9) + 5 records with NO cache_efficiency field.
        # Coercing absent->0 would drag the mean to 0.45 and spuriously fire;
        # excluding them leaves a clean 0.9 mean over 5 samples.
        for i in range(1, 6):
            self._task("agent-c%d" % i, i, cache=0.9)
        for i in range(6, 11):
            self._task("agent-n%d" % i, i, cache=None)
        rc, payload, _ = self._run_json(["--window"])
        self.assertEqual(rc, 0)
        self.assertNotIn("H6", self._fired(payload))

    # --- H4 bare-match-streak: count, candidate-stub, session filter (I3/I4) --

    def test_h4_session_filter_counts_only_current_session(self):
        for i in range(1, 4):
            self._bare("session-A%d" % i, i, "sessA")
        for i in range(1, 3):
            self._bare("session-B%d" % i, 10 + i, "sessB")
        rc, payload, _ = self._run_json(["--window", "--session-id", "sessA"])
        self.assertEqual(rc, 0)
        h4 = self._fired(payload)["H4"]
        self.assertEqual(h4["computed"], 3)
        # H4 is a resource-GAP signal, owner-gated to a candidate stub — its
        # improve-now is EXEMPT from the coarse downgrade.
        self.assertEqual(h4["action"], "improve-now")
        self.assertEqual(h4["effective_action"], "improve-now")

    def test_h4_session_filter_excludes_other_session(self):
        for i in range(1, 4):
            self._bare("session-A%d" % i, i, "sessA")
        for i in range(1, 3):
            self._bare("session-B%d" % i, 10 + i, "sessB")
        rc, payload, _ = self._run_json(["--window", "--session-id", "sessB"])
        self.assertEqual(rc, 0)
        self.assertNotIn("H4", self._fired(payload))

    def test_h4_without_session_id_falls_back_to_project_recent(self):
        for i in range(1, 4):
            self._bare("session-A%d" % i, i, "sessA")
        for i in range(1, 3):
            self._bare("session-B%d" % i, 10 + i, "sessB")
        rc, payload, _ = self._run_json(["--window"])
        self.assertEqual(rc, 0)
        h4 = self._fired(payload)["H4"]
        self.assertEqual(h4["computed"], 5)   # both sessions, project-recent
        self.assertIn("project-recent", h4.get("note", ""))

    # --- H7 rework-signal: fires on 2, skips unscored, coarse downgrade (I4) --

    def test_h7_fires_on_two_major(self):
        for i in range(1, 3):
            self._task("agent-m%d" % i, i, resources=["rw-res"])
            self._score("agent-m%d" % i, i, rework="major")
        for i in range(3, 5):
            self._task("agent-m%d" % i, i, resources=["rw-res"])
            self._score("agent-m%d" % i, i, rework="none")
        rc, payload, _ = self._run_json(["--task-id", "agent-m1"])
        self.assertEqual(rc, 0)
        h7 = self._fired(payload)["H7"]
        self.assertEqual(h7["action"], "improve-now")
        self.assertEqual(h7["computed"], 2)

    def test_h7_skips_unscored_tasks(self):
        # 2 scored-major + 3 unscored tasks deploying rw-res. Only scored count.
        for i in range(1, 3):
            self._task("agent-m%d" % i, i, resources=["rw-res"])
            self._score("agent-m%d" % i, i, rework="major")
        for i in range(3, 6):
            self._task("agent-u%d" % i, i, resources=["rw-res"])   # no score
        rc, payload, _ = self._run_json(["--task-id", "agent-m1"])
        self.assertEqual(rc, 0)
        h7 = self._fired(payload)["H7"]
        self.assertEqual(h7["samples"], 2)     # only the two scored tasks
        self.assertEqual(h7["computed"], 2)

    def test_h7_coarse_majors_downgraded_to_theme_note(self):
        # 3 major-rework tasks deploying rw-res, ALL session-backfill: the
        # attribution never established rw-res ran on them → downgrade.
        for i in range(1, 4):
            self._task("agent-b%d" % i, i, resources=["rw-res"],
                       source="session-backfill")
            self._score("agent-b%d" % i, i, rework="major")
        rc, payload, _ = self._run_json(["--task-id", "agent-b1"])
        self.assertEqual(rc, 0)
        h7 = self._fired(payload)["H7"]
        self.assertEqual(h7["action"], "improve-now")
        self.assertEqual(h7["effective_action"], "theme-note")
        self.assertIn("coarse-dominated", h7["downgrade_reason"])

    def test_h7_precise_majors_stays_improve_now(self):
        for i in range(1, 4):
            self._task("agent-p%d" % i, i, resources=["rw-res"], source="task")
            self._score("agent-p%d" % i, i, rework="major")
        rc, payload, _ = self._run_json(["--task-id", "agent-p1"])
        self.assertEqual(rc, 0)
        h7 = self._fired(payload)["H7"]
        self.assertEqual(h7["effective_action"], "improve-now")
        self.assertIsNone(h7["downgrade_reason"])

    # --- _priority_key ordering (I4) -----------------------------------------

    def test_priority_key_orders_action_then_confidence_then_hid(self):
        firings = [
            {"rule": "H2", "action": "theme-note",
             "effective_action": "theme-note", "confidence": "seed"},
            {"rule": "H8", "action": "no-action",
             "effective_action": "no-action", "confidence": "high"},
            {"rule": "H7", "action": "improve-now",
             "effective_action": "improve-now", "confidence": "seed"},
            {"rule": "H1", "action": "improve-now",
             "effective_action": "improve-now", "confidence": "high"},
        ]
        firings.sort(key=he._priority_key)
        self.assertEqual([f["rule"] for f in firings], ["H1", "H7", "H2", "H8"])
        self.assertEqual(firings[0]["rule"], "H1")   # the recommended pick

    def test_priority_key_downgraded_improve_now_sorts_as_theme_note(self):
        firings = [
            {"rule": "H1", "action": "improve-now",
             "effective_action": "theme-note", "confidence": "seed",
             "downgrade_reason": "coarse-dominated: 5/5 backfill"},
            {"rule": "H3", "action": "theme-note",
             "effective_action": "theme-note", "confidence": "high"},
        ]
        firings.sort(key=he._priority_key)
        # a genuine high-confidence theme-note outranks the downgraded H1.
        self.assertEqual(firings[0]["rule"], "H3")


if __name__ == "__main__":
    unittest.main()
