"""Tests for obs_ship.py — the span-builder sidecar (Phase 2).

Runs against fixture NDJSON, never a live OTLP collector. The OTel SDK
dependency is real (this is an out-of-tree sidecar, not a hook, so the
stdlib-only rule that governs payload/hooks/ does not apply here).

obs_ship.py's own opentelemetry imports are all function-local, so
`import obs_ship` succeeds under any interpreter, including plain system
python3 (confirmed empirically) — but most of these tests exercise code
paths that call into the real SDK (building spans, comparing
SpanExportResult), so a bare python3 run does NOT cleanly signal "missing
dependency": some tests raise ModuleNotFoundError directly (the ones that
import `opentelemetry` themselves, to set up a mock's return value), while
others fail — or even pass — for reasons that have nothing to do with what
they're meant to verify, because export_spans()'s own fault-tolerant
exception handling silently swallows the internal ModuleNotFoundError and
returns False, which happens to satisfy some assertions by coincidence. A
clean `OK` from this suite is only meaningful when run with the obs-venv
interpreter active (see payload/observability/README.md); plain system
python3 is not a reliable substitute either way, for pass OR fail.
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
        from opentelemetry.sdk.trace.export import SpanExportResult
        mock_exporter = MagicMock()
        # export_spans() compares by identity/equality against the real
        # SpanExportResult enum, not truthiness (SpanExportResult is a plain
        # Enum, not IntEnum -- bool(SpanExportResult.FAILURE) is ALSO True,
        # confirmed empirically against opentelemetry-sdk 1.41.1), so the
        # mock must return the real success value, not a bare `True`.
        mock_exporter.export.return_value = SpanExportResult.SUCCESS
        with patch.object(obs_ship, "_build_exporter", return_value=mock_exporter):
            result = obs_ship.run_once(str(events_dir), str(cursor_path))
        self.assertEqual(result.get("reason"), "ok")
        cursor = json.loads(cursor_path.read_text())
        self.assertIn(str(day_file), cursor.get("files", {}))
        self.assertGreater(cursor["files"][str(day_file)], 0)

    def test_run_once_treats_corrupt_cursor_offset_as_unread_from_start(self):
        # A hand-edited or corrupted cursor file can have a non-numeric
        # offset for a given path (e.g. a float string or garbage). This
        # must not crash run_once() under launchd every 60 seconds -- it
        # should fall back to re-reading that one file from the start.
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
        cursor_path.write_text(json.dumps({"files": {str(day_file): "not-a-number"}}))
        from opentelemetry.sdk.trace.export import SpanExportResult
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = SpanExportResult.SUCCESS
        try:
            with patch.object(obs_ship, "_build_exporter", return_value=mock_exporter):
                result = obs_ship.run_once(str(events_dir), str(cursor_path))
        except Exception as exc:  # pragma: no cover - this IS the failure being tested
            self.fail("run_once raised on a corrupt cursor offset: %r" % exc)
        self.assertTrue(result.get("exported"))
        self.assertEqual(result.get("count"), 1)
        mock_exporter.export.assert_called_once()

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
        self.assertEqual(result.get("reason"), "export-failed")
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
        self.assertEqual(result.get("reason"), "export-failed")


class TestMalformedRecords(unittest.TestCase):
    """I1: a line can be valid JSON but not an object (null/list/string/
    number) -- not malformed JSON (json.loads() succeeds on all of these),
    just the wrong shape. fold_spans() must not blow up calling .get() on
    it (AttributeError on None/list/str/int), and the valid records around
    it must still be processed normally."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_run_once_never_raises_on_valid_json_non_dict_lines(self):
        events_dir = self.dir / "events"
        events_dir.mkdir()
        _write_ndjson(events_dir / "2026-08-05.ndjson", [
            None,
            [],
            "a string",
            42,
            {"schema": "obs.v1", "ts": "2026-08-05T10:00:00Z", "event": "turn.stop",
             "session_id": "s4", "trace_id": "t4", "span_id": "sp4",
             "parent_span_id": None, "agent_id": None, "plan_id": None,
             "part_id": None, "project": None, "attrs": {}},
        ])
        cursor_path = self.dir / "obs_ship.cursor.json"
        from opentelemetry.sdk.trace.export import SpanExportResult
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = SpanExportResult.SUCCESS
        try:
            with patch.object(obs_ship, "_build_exporter", return_value=mock_exporter):
                result = obs_ship.run_once(str(events_dir), str(cursor_path))
        except Exception as exc:  # pragma: no cover - this IS the failure being tested
            self.fail("run_once raised on a valid-JSON-non-dict line: %r" % exc)
        # All 5 raw lines were read (4 non-dict + 1 valid record); the valid
        # record still gets folded into a span and exported normally.
        self.assertTrue(result.get("exported"))
        self.assertEqual(result.get("reason"), "ok")
        self.assertEqual(result.get("count"), 5)
        mock_exporter.export.assert_called_once()
        exported_spans = mock_exporter.export.call_args[0][0]
        self.assertEqual(len(exported_spans), 1)  # only the valid record became a span


class TestMalformedSpanConstruction(unittest.TestCase):
    """I2: _to_readable_span() must not run inside export_spans()'s network
    try/except -- one record that can't become a ReadableSpan (e.g. missing
    `ts`, so fold_spans() leaves start_ts=None and _iso_to_ns(None) raises
    ValueError) must not report failure for the WHOLE batch. A failure
    report means the cursor never advances, which means every future run
    hits the exact same unfixable record again -- a permanent, silent
    wedge indistinguishable from "no backend yet"."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_export_spans_returns_true_when_every_span_is_malformed(self):
        bad_span = {"trace_id": "t1", "span_id": "sp1", "start_ts": None,
                    "end_ts": None, "name": "turn.stop", "duration_ms": 0,
                    "events": []}
        # No _build_exporter mocking needed: export_spans() must never even
        # reach the network step once every span has been dropped.
        ok, reason = obs_ship.export_spans([bad_span], "http://127.0.0.1:1")
        self.assertTrue(ok)
        self.assertEqual(reason, "all-spans-dropped")

    def test_export_spans_returns_tracer_unavailable_when_build_tracer_fails(self):
        good_span = {"trace_id": "t1", "span_id": "sp1",
                     "start_ts": "2026-08-05T10:00:00Z",
                     "end_ts": "2026-08-05T10:00:00Z", "name": "turn.stop",
                     "duration_ms": 0, "events": []}
        with patch.object(obs_ship, "_build_tracer", side_effect=RuntimeError("no sdk")):
            ok, reason = obs_ship.export_spans([good_span], "http://127.0.0.1:1")
        self.assertFalse(ok)
        self.assertEqual(reason, "tracer-unavailable")

    def test_run_once_does_not_wedge_cursor_on_one_bad_record_in_a_mixed_batch(self):
        events_dir = self.dir / "events"
        events_dir.mkdir()
        day_file = events_dir / "2026-08-05.ndjson"
        _write_ndjson(day_file, [
            # Missing "ts" entirely -- fold_spans() sets start_ts=None,
            # _to_readable_span() raises constructing this one.
            {"schema": "obs.v1", "event": "turn.stop",
             "session_id": "s5", "trace_id": "tbad", "span_id": "spbad",
             "parent_span_id": None, "agent_id": None, "plan_id": None,
             "part_id": None, "project": None, "attrs": {}},
            {"schema": "obs.v1", "ts": "2026-08-05T10:00:00Z", "event": "turn.stop",
             "session_id": "s5", "trace_id": "tgood", "span_id": "spgood",
             "parent_span_id": None, "agent_id": None, "plan_id": None,
             "part_id": None, "project": None, "attrs": {}},
        ])
        cursor_path = self.dir / "obs_ship.cursor.json"
        from opentelemetry.sdk.trace.export import SpanExportResult
        mock_exporter = MagicMock()
        mock_exporter.export.return_value = SpanExportResult.SUCCESS
        with patch.object(obs_ship, "_build_exporter", return_value=mock_exporter):
            result = obs_ship.run_once(str(events_dir), str(cursor_path))
        self.assertTrue(result.get("exported"))
        self.assertEqual(result.get("reason"), "ok")
        self.assertEqual(result.get("count"), 2)
        # Only the good span reached the exporter -- the bad one was
        # dropped, not raised, and did not abort the batch.
        exported_spans = mock_exporter.export.call_args[0][0]
        self.assertEqual(len(exported_spans), 1)
        # Cursor advanced past BOTH raw events, including the bad one -- it
        # must never retry a permanently-unfixable record forever.
        cursor = json.loads(cursor_path.read_text())
        self.assertIn(str(day_file), cursor.get("files", {}))

    def test_run_once_advances_past_a_batch_that_is_entirely_malformed(self):
        events_dir = self.dir / "events"
        events_dir.mkdir()
        day_file = events_dir / "2026-08-05.ndjson"
        _write_ndjson(day_file, [
            {"schema": "obs.v1", "event": "turn.stop",
             "session_id": "s6", "trace_id": "tbad2", "span_id": "spbad2",
             "parent_span_id": None, "agent_id": None, "plan_id": None,
             "part_id": None, "project": None, "attrs": {}},
        ])
        cursor_path = self.dir / "obs_ship.cursor.json"
        # No exporter mocking at all -- export_spans() must return True
        # before ever reaching the network step, since nothing survives
        # span construction.
        result = obs_ship.run_once(str(events_dir), str(cursor_path))
        self.assertTrue(result.get("exported"))
        self.assertEqual(result.get("reason"), "all-spans-dropped")
        self.assertEqual(result.get("count"), 1)
        cursor = json.loads(cursor_path.read_text())
        self.assertIn(str(day_file), cursor.get("files", {}))
        self.assertGreater(cursor["files"][str(day_file)], 0)


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
