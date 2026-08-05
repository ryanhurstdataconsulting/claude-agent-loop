"""Tests for obs_emit — the obs.v1 structured event log (Phase 1).

Written TDD-first: imports obs_emit before the module exists (RED =
ModuleNotFoundError), then drives it GREEN. Mirrors test_harvest_metrics.py's
tempfile-per-test, sys.path-insert convention.
"""
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import obs_emit  # noqa: E402


class ObsEmitFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.claude_dir = pathlib.Path(self._tmp.name)
        self._old_env = os.environ.get("CLAUDE_DIR")
        os.environ["CLAUDE_DIR"] = str(self.claude_dir)

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("CLAUDE_DIR", None)
        else:
            os.environ["CLAUDE_DIR"] = self._old_env
        self._tmp.cleanup()

    def _events_file(self):
        events_dir = self.claude_dir / "metrics" / "events"
        files = sorted(events_dir.glob("*.ndjson"))
        self.assertEqual(len(files), 1, "expected exactly one daily shard")
        return files[0]

    def _lines(self):
        return [
            json.loads(line)
            for line in self._events_file().read_text().splitlines()
            if line.strip()
        ]


class TestSchemaShape(ObsEmitFixture):
    def test_emitted_record_matches_obs_v1_shape(self):
        obs_emit.emit(
            "tool.pre", session_id="sess-1", agent_id=None, plan_id=None,
            part_id=None, project="myproj", tool_name="Read",
        )
        records = self._lines()
        self.assertEqual(len(records), 1)
        rec = records[0]
        required = {
            "schema", "ts", "event", "session_id", "agent_id", "trace_id",
            "span_id", "parent_span_id", "plan_id", "part_id", "project",
            "attrs",
        }
        self.assertEqual(set(rec.keys()), required)
        self.assertEqual(rec["schema"], "obs.v1")
        self.assertEqual(rec["event"], "tool.pre")
        self.assertEqual(rec["session_id"], "sess-1")
        self.assertEqual(rec["project"], "myproj")
        self.assertEqual(rec["attrs"], {"tool_name": "Read"})
        self.assertIsInstance(rec["trace_id"], str)
        self.assertEqual(len(rec["trace_id"]), 32)
        self.assertIsInstance(rec["span_id"], str)
        self.assertEqual(len(rec["span_id"]), 16)

    def test_emit_returns_none(self):
        self.assertIsNone(obs_emit.emit("session.start", session_id="sess-1"))


class TestDeterministicIds(ObsEmitFixture):
    def test_same_inputs_same_ids(self):
        obs_emit.emit("tool.pre", session_id="sess-1", component_key="ck-1")
        obs_emit.emit("tool.pre", session_id="sess-1", component_key="ck-1")
        first, second = self._lines()
        self.assertEqual(first["trace_id"], second["trace_id"])
        self.assertEqual(first["span_id"], second["span_id"])

    def test_different_component_key_different_span(self):
        obs_emit.emit("tool.pre", session_id="sess-1", component_key="ck-1")
        obs_emit.emit("tool.pre", session_id="sess-1", component_key="ck-2")
        first, second = self._lines()
        self.assertEqual(first["trace_id"], second["trace_id"])
        self.assertNotEqual(first["span_id"], second["span_id"])

    def test_pure_functions_stable_without_module_state(self):
        # "Stable across process restarts" is true by construction: the ID
        # functions read no counter, no file, no clock — only their args.
        t1 = obs_emit.trace_id_for("sess-1")
        s1 = obs_emit.span_id_for("sess-1", "ck-1")
        t2 = obs_emit.trace_id_for("sess-1")
        s2 = obs_emit.span_id_for("sess-1", "ck-1")
        self.assertEqual(t1, t2)
        self.assertEqual(s1, s2)

    def test_root_task_id_priority_session_over_agent_over_plan(self):
        obs_emit.emit("tool.pre", session_id="sess-1", agent_id="agent-9",
                       plan_id="wo-1", component_key="x")
        obs_emit.emit("tool.pre", session_id="sess-1", component_key="x")
        first, second = self._lines()
        self.assertEqual(first["trace_id"], second["trace_id"],
                         "session_id must win over agent_id/plan_id")


class TestAppendSafety(ObsEmitFixture):
    def test_survives_malformed_last_line(self):
        events_dir = self.claude_dir / "metrics" / "events"
        events_dir.mkdir(parents=True)
        import datetime
        day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        shard = events_dir / ("%s.ndjson" % day)
        shard.write_text("{not valid json\n")

        obs_emit.emit("tool.pre", session_id="sess-1")  # must not raise

        lines = shard.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "{not valid json")
        json.loads(lines[1])  # the new line is still valid JSON


class TestSilentFailure(ObsEmitFixture):
    def test_unwritable_events_dir_does_not_raise(self):
        metrics_dir = self.claude_dir / "metrics"
        metrics_dir.mkdir(parents=True)
        metrics_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # read+exec, no write
        try:
            result = obs_emit.emit("tool.pre", session_id="sess-1")
        finally:
            metrics_dir.chmod(stat.S_IRWXU)  # restore so tempdir cleanup works
        self.assertIsNone(result)
        self.assertFalse((metrics_dir / "events").exists())


if __name__ == "__main__":
    unittest.main()
