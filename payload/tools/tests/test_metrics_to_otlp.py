"""Tests for metrics_to_otlp — the read-only shard retrofit exporter (P3).

Written TDD-first: imports ``metrics_to_otlp`` before the module exists
(RED = ModuleNotFoundError), then drives it GREEN.

Fixture convention: this tool reads EXISTING metrics-shard records directly
(kind:"task"/"score"/"learn"), the same store ``heuristics_eval.py`` reads —
not Claude Code transcripts (that is what ``harvest_metrics.py`` converts
FROM). The established "shard fixture" convention in this repo for that
shape is ``test_heuristics_eval.py``'s: unittest.TestCase, a per-test
tempfile.TemporaryDirectory (addCleanup-based, not tempfile.mkdtemp +
manual shutil.rmtree), and small parametrized helper methods that plant one
fixture *record* at a time via ``harvest_metrics._append_record`` (the same
real append path the harvester itself uses) rather than large static
module-level transcript dicts (``test_harvest_metrics.py``'s convention,
which is for CC-transcript fixtures feeding ``harvest()`` — a different
input shape than this tool consumes). Mirrored here accordingly.

Every test class that exercises ``run_once()``/``main()``/
``export_aggregates()`` — which always builds a real MeterProvider via
``_build_meter()``, even when the network exporter itself is mocked out via
``_build_exporter`` — is gated with ``@unittest.skipUnless(_HAS_OTEL, ...)``
at the class level. metrics_to_otlp.py defers all its ``opentelemetry.*``
imports into function bodies (see its module docstring), so importing the
module never requires the pip package; only actually building OTel
instruments does. This lets ``payload/tools/tests/run_all.sh`` (plain
``python3 -m unittest``, no venv-awareness) exercise the pure
aggregation/cursor-key/dedup unit tests (``TestPureAggregation``,
``TestLoadLastWins``) cleanly even when opentelemetry isn't installed,
skipping only the classes that need the real SDK, while the obs-venv
interpreter (see payload/observability/README.md) gets full coverage with
no skips.
"""
import datetime
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import metrics_to_otlp as mo  # noqa: E402
import harvest_metrics as hm  # noqa: E402

try:
    import opentelemetry.sdk.metrics  # noqa: F401
    from opentelemetry.sdk.metrics.export import MetricExportResult
    _HAS_OTEL = True
except ImportError:
    MetricExportResult = None
    _HAS_OTEL = False

_OTEL_REASON = "opentelemetry-sdk not installed"

_NOW = datetime.datetime.now(datetime.timezone.utc)


def _ts(day, hour=0):
    """An ISO ts_end in the CURRENT month (mirrors test_heuristics_eval.py's
    ``_ts`` helper — day is 1..28, valid in every month)."""
    return "%04d-%02d-%02dT%02d:00:00Z" % (_NOW.year, _NOW.month, day, hour)


class MetricsToOtlpFixture(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.metrics = pathlib.Path(self.td.name) / "metrics"
        self.metrics.mkdir()
        self.cursor = self.metrics / "state" / "metrics_to_otlp.cursor.json"

    # --- planting helpers, one real shard record at a time -------------------

    def _task(self, task_id, day, verdict="__unset__", error_rate=0.0,
              passed=0, failed=0, resources_source="task"):
        rec = {
            "schema": 1, "kind": "task", "task_id": task_id,
            "project": "demo_project", "ts_end": _ts(day),
            "error_rate": error_rate,
            "tests": {"passed": passed, "failed": failed},
            "resources_source": resources_source,
        }
        if verdict != "__unset__":
            rec["verdict"] = verdict
        hm._append_record(str(self.metrics), rec)
        return rec

    def _score(self, task_id, day, outcome="good"):
        rec = {
            "schema": 1, "kind": "score", "task_id": task_id,
            "project": "demo_project", "ts_end": _ts(day),
            "scales": {"outcome": outcome},
        }
        hm._append_record(str(self.metrics), rec)
        return rec

    def _learn(self, task_id, day, rule, action="theme-note"):
        rec = {
            "schema": 1, "kind": "learn", "task_id": task_id,
            "ts_end": _ts(day), "action": action, "rule": rule,
        }
        hm._append_record(str(self.metrics), rec)
        return rec

    def _run(self, endpoint="http://localhost:4318"):
        return mo.run_once(str(self.metrics), str(self.cursor), endpoint=endpoint)

    def _shard_path(self):
        shards = sorted(self.metrics.glob("*.jsonl"))
        self.assertEqual(len(shards), 1, "expected exactly one shard in this fixture")
        return shards[0]


# --- pure aggregation (no OTel needed) --------------------------------------

class TestPureAggregation(unittest.TestCase):
    def test_aggregate_tests_sums_passed_and_failed(self):
        recs = [
            {"kind": "task", "tests": {"passed": 3, "failed": 1}},
            {"kind": "task", "tests": {"passed": 5, "failed": 0}},
        ]
        self.assertEqual(mo.aggregate_tests(recs), {"passed": 8, "failed": 1})

    def test_aggregate_error_rates_excludes_missing(self):
        recs = [
            {"kind": "task", "error_rate": 0.2},
            {"kind": "task", "error_rate": None},
            {"kind": "task"},
            {"kind": "task", "error_rate": 0.6},
        ]
        self.assertEqual(mo.aggregate_error_rates(recs), [0.2, 0.6])

    def test_aggregate_verdict_buckets_missing_key_separately(self):
        recs = [
            {"kind": "task", "verdict": "clean"},
            {"kind": "task"},   # verdict key absent entirely
            {"kind": "task", "verdict": "dirty"},
            {"kind": "task", "verdict": "clean"},
        ]
        counts = mo.aggregate_verdict(recs)
        self.assertEqual(counts, {"clean": 2, "dirty": 1, mo._MISSING: 1})
        self.assertNotIn("unknown", counts)   # M2: never coerced to "unknown"

    def test_aggregate_verdict_buckets_explicit_null_same_as_missing(self):
        # loop_close.py's task_records() sets verdict=part.get("verdict"),
        # which can itself be None -- an explicit null must land in the SAME
        # bucket as a wholly-absent key, not a third distinct bucket.
        recs = [{"kind": "task", "verdict": None},
                {"kind": "task"}]
        self.assertEqual(mo.aggregate_verdict(recs), {mo._MISSING: 2})

    def test_aggregate_heuristics_counts_literal_rule_string(self):
        recs = [
            {"kind": "learn", "rule": "H1"},
            {"kind": "learn", "rule": "H1"},
            {"kind": "learn", "rule": "H0"},   # outside heuristics_eval.EVALUABLE_RULES
        ]
        counts = mo.aggregate_heuristics(recs)
        self.assertEqual(counts, {"H1": 2, "H0": 1})

    def test_aggregate_resources_source_mix(self):
        recs = [
            {"kind": "task", "resources_source": "workorder"},
            {"kind": "task", "resources_source": "task"},
            {"kind": "task", "resources_source": "session-backfill"},
            {"kind": "task", "resources_source": "session-backfill"},
        ]
        counts = mo.aggregate_resources_source(recs)
        self.assertEqual(counts, {"workorder": 1, "task": 1, "session-backfill": 2})

    def test_build_aggregates_ignores_non_task_non_learn_kinds(self):
        changed = {
            ("t1", "task"): {"kind": "task", "tests": {"passed": 1, "failed": 0},
                             "error_rate": 0.1, "verdict": "clean",
                             "resources_source": "task"},
            ("t1", "score"): {"kind": "score", "scales": {"outcome": "good"}},
        }
        agg = mo.build_aggregates(changed)
        self.assertEqual(agg["tests"], {"passed": 1, "failed": 0})
        self.assertEqual(agg["error_rates"], [0.1])
        self.assertEqual(agg["verdicts"], {"clean": 1})
        self.assertEqual(agg["heuristics"], {})
        self.assertEqual(agg["resources_source"], {"task": 1})


# --- shard scanning + last-wins dedup ---------------------------------------

class TestLoadLastWins(MetricsToOtlpFixture):
    def test_keeps_last_record_per_task_id_kind(self):
        self._task("agent-1", 1, error_rate=0.1)
        self._task("agent-1", 2, error_rate=0.9)   # supersedes: same (task_id, kind)
        by_key = mo.load_last_wins(str(self.metrics))
        self.assertEqual(len(by_key), 1)
        self.assertEqual(by_key[("agent-1", "task")]["error_rate"], 0.9)

    def test_distinct_kinds_for_same_task_id_both_kept(self):
        self._task("agent-1", 1)
        self._score("agent-1", 2)
        by_key = mo.load_last_wins(str(self.metrics))
        self.assertEqual(set(by_key.keys()), {("agent-1", "task"), ("agent-1", "score")})

    def test_malformed_line_skipped_not_fatal(self):
        shard = self.metrics / ("%s.jsonl" % _NOW.strftime("%Y-%m"))
        shard.parent.mkdir(parents=True, exist_ok=True)
        with open(shard, "a") as fh:
            fh.write("not valid json {{{\n")
        self._task("agent-1", 1)
        by_key = mo.load_last_wins(str(self.metrics))
        self.assertEqual(len(by_key), 1)


# --- cursor / idempotency ----------------------------------------------------

@unittest.skipUnless(_HAS_OTEL, _OTEL_REASON)
class TestCursorAndIdempotency(MetricsToOtlpFixture):
    def test_second_run_skips_unchanged_records_no_export_call(self):
        self._task("agent-1", 1, verdict="clean", passed=3, error_rate=0.2)
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = MetricExportResult.SUCCESS
        with patch.object(mo, "_build_exporter", return_value=mock_exporter):
            first = self._run()
            self.assertTrue(first["exported"])
            self.assertEqual(first["count"], 1)
            mock_exporter.export.assert_called_once()

            mock_exporter.reset_mock()
            second = self._run()
        self.assertEqual(second, {"exported": True, "count": 0, "reason": "ok"})
        mock_exporter.export.assert_not_called()

    def test_changed_record_reexports_with_new_value_only(self):
        self._task("agent-1", 1, error_rate=0.1)
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = MetricExportResult.SUCCESS
        with patch.object(mo, "_build_exporter", return_value=mock_exporter):
            first = self._run()
            self.assertTrue(first["exported"])
            # Superseding record for the SAME (task_id, kind): last-wins.
            self._task("agent-1", 2, error_rate=0.9)
            mock_exporter.reset_mock()
            second = self._run()
        self.assertEqual(second["count"], 1)
        mock_exporter.export.assert_called_once()
        exported = mock_exporter.export.call_args[0][0]
        # Only the LATEST value (0.9) was in this run's aggregate, never both.
        values = [dp.sum for rm in exported.resource_metrics
                  for sm in rm.scope_metrics for m in sm.metrics
                  if m.name == "claude_agent_loop.error_rate"
                  for dp in m.data.data_points]
        self.assertEqual(values, [0.9])

    def test_cursor_file_written_atomically_with_content_hash_keys(self):
        self._task("agent-1", 1, error_rate=0.1)
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = MetricExportResult.SUCCESS
        with patch.object(mo, "_build_exporter", return_value=mock_exporter):
            self._run()
        self.assertTrue(self.cursor.is_file())
        data = json.loads(self.cursor.read_text())
        self.assertIn("agent-1:task", data)
        self.assertEqual(len(data["agent-1:task"]), 64)   # sha256 hex digest

    def test_failed_export_does_not_advance_cursor(self):
        self._task("agent-1", 1, error_rate=0.1)
        mock_exporter = MagicMock()
        mock_exporter.export.side_effect = ConnectionError("unreachable")
        with patch.object(mo, "_build_exporter", return_value=mock_exporter):
            result = self._run()
        self.assertFalse(result["exported"])
        self.assertFalse(self.cursor.exists())

    def test_score_only_change_causes_no_export_call(self):
        # A kind that contributes to no metric category (score) is the ONLY
        # thing that changed this run -> aggregates are all empty -> the
        # network exporter must never even be built.
        self._score("agent-1", 1)
        mock_exporter = MagicMock()
        with patch.object(mo, "_build_exporter", return_value=mock_exporter):
            result = self._run()
        self.assertEqual(result, {"exported": True, "count": 1, "reason": "no-data-points"})
        mock_exporter.export.assert_not_called()
        self.assertTrue(self.cursor.is_file())   # still marked seen


# --- never mutates the shard -------------------------------------------------

@unittest.skipUnless(_HAS_OTEL, _OTEL_REASON)
class TestNeverMutatesShard(MetricsToOtlpFixture):
    def test_shard_bytes_identical_before_and_after(self):
        self._task("agent-1", 1, error_rate=0.1, verdict="clean")
        self._learn("agent-1", 2, "H1")
        shard = self._shard_path()
        before = shard.read_bytes()
        mock_exporter = MagicMock()
        with patch.object(mo, "_build_exporter", return_value=mock_exporter):
            self._run()
        after = shard.read_bytes()
        self.assertEqual(before, after)


# --- CLI ---------------------------------------------------------------------

@unittest.skipUnless(_HAS_OTEL, _OTEL_REASON)
class TestMain(MetricsToOtlpFixture):
    def test_main_prints_json_result_and_returns_zero(self):
        self._task("agent-1", 1, error_rate=0.1)
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = MetricExportResult.SUCCESS
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with patch.object(mo, "_build_exporter", return_value=mock_exporter):
            with redirect_stdout(out):
                rc = mo.main(["--metrics-dir", str(self.metrics),
                             "--cursor", str(self.cursor)])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["exported"])
        self.assertEqual(payload["count"], 1)


# --- real OTel instrument construction (obs-venv only) ----------------------

@unittest.skipUnless(_HAS_OTEL, "opentelemetry-sdk not installed")
class TestEmitMetricsRealOtel(MetricsToOtlpFixture):
    def test_full_shard_scenario_exports_expected_metric_shapes(self):
        # kind:"task" with verdict, kind:"task" without verdict, kind:"score"
        # (must be ignored), kind:"learn" with a rule outside H1-H8.
        self._task("agent-1", 1, verdict="clean", passed=34, failed=2,
                   error_rate=0.1, resources_source="workorder")
        self._task("agent-2", 2, passed=5, failed=0, error_rate=0.3,
                   resources_source="session-backfill")   # no verdict key
        self._score("agent-1", 3)
        self._learn("agent-3", 4, "H0")

        mock_exporter = MagicMock()
        mock_exporter.export.return_value = MetricExportResult.SUCCESS
        with patch.object(mo, "_build_exporter", return_value=mock_exporter):
            result = self._run()

        self.assertTrue(result["exported"])
        self.assertEqual(result["count"], 4)   # 2 task + 1 score + 1 learn
        mock_exporter.export.assert_called_once()
        metrics_data = mock_exporter.export.call_args[0][0]

        by_name = {}
        for rm in metrics_data.resource_metrics:
            for sm in rm.scope_metrics:
                for m in sm.metrics:
                    by_name[m.name] = m

        tests_dps = {dp.attributes["result"]: dp.value
                     for dp in by_name["claude_agent_loop.tests"].data.data_points}
        self.assertEqual(tests_dps, {"passed": 39, "failed": 2})

        # error_rate carries no grouping attribute (a single overall
        # distribution), so both values land in ONE HistogramDataPoint:
        # count=2, sum=0.1+0.3.
        error_rate_dps = by_name["claude_agent_loop.error_rate"].data.data_points
        self.assertEqual(len(error_rate_dps), 1)
        self.assertEqual(error_rate_dps[0].count, 2)
        self.assertAlmostEqual(error_rate_dps[0].sum, 0.4, places=6)

        verdict_dps = {dp.attributes["verdict"]: dp.value
                       for dp in by_name["claude_agent_loop.verdict"].data.data_points}
        self.assertEqual(verdict_dps, {"clean": 1, mo._MISSING: 1})

        rule_dps = {dp.attributes["rule"]: dp.value
                    for dp in by_name["claude_agent_loop.heuristic_firings"].data.data_points}
        self.assertEqual(rule_dps, {"H0": 1})

        source_dps = {dp.attributes["resources_source"]: dp.value
                      for dp in by_name["claude_agent_loop.resources_source"].data.data_points}
        self.assertEqual(source_dps, {"workorder": 1, "session-backfill": 1})

    def test_real_exporter_against_unreachable_endpoint_fails_gracefully(self):
        # No _build_exporter mocking here: a real OTLPMetricExporter pointed
        # at a closed port (mirrors test_obs_ship.py's equivalent test),
        # confirming run_once() degrades to (False, "export-failed") rather
        # than raising, end-to-end with the real SDK.
        self._task("agent-1", 1, error_rate=0.1)
        try:
            result = self._run(endpoint="http://127.0.0.1:1")
        except Exception as exc:  # pragma: no cover - this IS the failure being tested
            self.fail("run_once raised instead of degrading silently: %r" % exc)
        self.assertFalse(result["exported"])
        self.assertEqual(result["reason"], "export-failed")


if __name__ == "__main__":
    unittest.main()
