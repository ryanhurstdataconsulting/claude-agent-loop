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
        from opentelemetry.sdk.trace.export import SpanExportResult
        mock_exporter = MagicMock()
        # export_spans() compares by identity/equality against the real
        # SpanExportResult enum, not truthiness (SpanExportResult is a plain
        # Enum, not IntEnum -- bool(SpanExportResult.FAILURE) is ALSO True,
        # confirmed empirically against opentelemetry-sdk 1.41.1), so the
        # mock must return the real success value, not a bare `True`.
        mock_exporter.export.return_value = SpanExportResult.SUCCESS
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
