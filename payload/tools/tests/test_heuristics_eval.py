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
        # isolated rule under test is the only thing that can fire.
        hm._append_record(str(self.metrics), {
            "schema": 1, "kind": "task", "task_id": task_id,
            "project": "demo_project", "ts_end": _ts(day),
            "resources_deployed": resources or [], "resources_source": source,
            "error_rate": error_rate, "cache_efficiency": cache,
            "interrupted": interrupted, "tests": {"failed": failed, "passed": 1},
        })

    def _score(self, task_id, day, outcome="good", rework="none"):
        hm._append_record(str(self.metrics), {
            "schema": 1, "kind": "score", "task_id": task_id,
            "project": "demo_project", "ts_end": _ts(day),
            "scales": {"outcome": outcome, "rework": rework},
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


if __name__ == "__main__":
    unittest.main()
