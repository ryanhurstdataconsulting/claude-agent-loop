"""Tests for harvest_metrics — the objective metrics harvester (P2).

Written TDD-first: this module imports ``harvest_metrics`` before the tool
exists (RED = ModuleNotFoundError), then drives it GREEN. All fixtures are
synthetic — no real credential, token, or personal datum appears here.

The fixtures mimic the on-disk Claude Code layout:

    <root>/projects/<slug>/<sid>.jsonl              # main session transcript
    <root>/projects/<slug>/<sid>/subagents/agent-*.jsonl   # subagent transcripts

so the project-slug derivation (the child of a ``projects`` directory) is
exercised by the real code path rather than stubbed.
"""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import harvest_metrics as hm  # noqa: E402

SLUG = "myproj"
SID = "sid123"
MALFORMED = "__MALFORMED__"

# --- agent-aaa: the full-featured task fixture (2026-06 shard) ---------------
AAA_RECS = [
    {"type": "user", "sessionId": SID, "gitBranch": "feature/x",
     "timestamp": "2026-06-11T02:00:00.000Z",
     "message": {"role": "user", "content": "run the tests"}},
    # m1 fragment 1: the ANNOUNCE text (two deployed resources).
    {"type": "assistant", "sessionId": SID, "gitBranch": "feature/x",
     "timestamp": "2026-06-11T02:00:01.000Z",
     "message": {"role": "assistant", "model": "claude-opus-4-8", "id": "m1",
                 "usage": {"input_tokens": 100, "output_tokens": 5,
                           "cache_read_input_tokens": 50,
                           "cache_creation_input_tokens": 20},
                 "content": [{"type": "text", "text":
                              "Resource Loop — deploying: sports-analyst "
                              "(skill), data-visualization (skill) — "
                              "layered viz work"}]}},
    # m1 fragment 2 (SAME message.id): the complete usage wins (out=40) and
    # carries server_tool_use. Tokens for m1 must be counted ONCE.
    {"type": "assistant", "sessionId": SID, "gitBranch": "feature/x",
     "timestamp": "2026-06-11T02:00:02.000Z",
     "message": {"role": "assistant", "model": "claude-opus-4-8", "id": "m1",
                 "usage": {"input_tokens": 100, "output_tokens": 40,
                           "cache_read_input_tokens": 50,
                           "cache_creation_input_tokens": 20,
                           "server_tool_use": {"web_search_requests": 2,
                                               "web_fetch_requests": 1}},
                 "content": [{"type": "tool_use", "name": "Bash", "id": "tu1",
                              "input": {"command": "pytest"}}]}},
    # Bash result carries the test line in BOTH tool_result.content and
    # toolUseResult.stdout — must be counted once (stdout preferred).
    {"type": "user", "sessionId": SID, "gitBranch": "feature/x",
     "timestamp": "2026-06-11T02:00:03.000Z",
     "message": {"role": "user", "content": [
         {"type": "tool_result", "tool_use_id": "tu1", "is_error": False,
          "content": "34 passed, 2 failed in 1.20s"}]},
     "toolUseResult": {"stdout": "34 passed, 2 failed in 1.20s",
                       "interrupted": False}},
    # m2 (distinct message), gitBranch flips to feature/y (last-seen wins).
    {"type": "assistant", "sessionId": SID, "gitBranch": "feature/y",
     "timestamp": "2026-06-11T02:00:04.000Z",
     "message": {"role": "assistant", "model": "claude-opus-4-8", "id": "m2",
                 "usage": {"input_tokens": 200, "output_tokens": 30,
                           "cache_read_input_tokens": 100,
                           "cache_creation_input_tokens": 0},
                 "content": [{"type": "tool_use", "name": "Read", "id": "tu2",
                              "input": {"file_path": "/x"}}]}},
    # Re-run output: the LAST "passed" count per result wins (12, not 10).
    {"type": "user", "sessionId": SID, "gitBranch": "feature/y",
     "timestamp": "2026-06-11T02:00:05.000Z",
     "message": {"role": "user", "content": [
         {"type": "tool_result", "tool_use_id": "tu2", "is_error": False,
          "content": "line1\nfirst 10 passed then after fix 12 passed"}]},
     "toolUseResult": {"stdout": "first 10 passed then after fix 12 passed",
                       "interrupted": False}},
    # m3 (distinct message): a second Bash that errors and is interrupted.
    {"type": "assistant", "sessionId": SID, "gitBranch": "feature/y",
     "timestamp": "2026-06-11T02:00:06.000Z",
     "message": {"role": "assistant", "model": "claude-opus-4-8", "id": "m3",
                 "usage": {"input_tokens": 10, "output_tokens": 10,
                           "cache_read_input_tokens": 10,
                           "cache_creation_input_tokens": 10},
                 "content": [{"type": "tool_use", "name": "Bash", "id": "tu3",
                              "input": {"command": "pytest again"}}]}},
    {"type": "user", "sessionId": SID, "gitBranch": "feature/y",
     "timestamp": "2026-06-11T02:00:07.000Z",
     "message": {"role": "user", "content": [
         {"type": "tool_result", "tool_use_id": "tu3", "is_error": True,
          "content": "Traceback: boom"}]},
     "toolUseResult": {"stdout": "", "stderr": "boom", "interrupted": True}},
    # Synthetic model: excluded from token/web sums, still an assistant record.
    {"type": "assistant", "sessionId": SID, "gitBranch": "feature/y",
     "timestamp": "2026-06-11T02:00:08.000Z",
     "message": {"role": "assistant", "model": "<synthetic>", "id": "m4",
                 "usage": {"input_tokens": 9999, "output_tokens": 9999,
                           "cache_read_input_tokens": 9999,
                           "cache_creation_input_tokens": 9999},
                 "content": [{"type": "text", "text": "(no response requested)"}]}},
    MALFORMED,
    {"type": "user", "sessionId": SID, "gitBranch": "feature/y",
     "timestamp": "2026-06-11T02:00:09.000Z",
     "message": {"role": "user", "content": "thanks"}},
]

# --- agent-bbb: the bare-announce fixture (lands in the 2026-07 shard) -------
BBB_RECS = [
    {"type": "user", "sessionId": SID, "gitBranch": "main",
     "timestamp": "2026-07-02T10:00:00.000Z",
     "message": {"role": "user", "content": "do a thing"}},
    {"type": "assistant", "sessionId": SID, "gitBranch": "main",
     "timestamp": "2026-07-02T10:00:01.000Z",
     "message": {"role": "assistant", "model": "claude-sonnet-4", "id": "n1",
                 "usage": {"input_tokens": 10, "output_tokens": 2,
                           "cache_read_input_tokens": 0,
                           "cache_creation_input_tokens": 0},
                 "content": [{"type": "text", "text":
                              "Resource Loop — no registry match; "
                              "proceeding bare."}]}},
    {"type": "assistant", "sessionId": SID, "gitBranch": "main",
     "timestamp": "2026-07-02T10:00:02.000Z",
     "message": {"role": "assistant", "model": "claude-sonnet-4", "id": "n1",
                 "usage": {"input_tokens": 10, "output_tokens": 8,
                           "cache_read_input_tokens": 0,
                           "cache_creation_input_tokens": 0},
                 "content": [{"type": "tool_use", "name": "Read", "id": "tb1",
                              "input": {}}]}},
    {"type": "user", "sessionId": SID, "gitBranch": "main",
     "timestamp": "2026-07-02T10:00:03.000Z",
     "message": {"role": "user", "content": [
         {"type": "tool_result", "tool_use_id": "tb1", "is_error": False,
          "content": "ok"}]},
     "toolUseResult": {"stdout": "ok", "interrupted": False}},
]

# --- the main session transcript (2026-06 shard) ----------------------------
SESSION_RECS = [
    {"type": "operation", "operation": "init", "sessionId": SID,
     "timestamp": "2026-06-11T01:59:00.000Z"},
    {"type": "user", "sessionId": SID, "gitBranch": "main",
     "timestamp": "2026-06-11T01:59:30.000Z",
     "message": {"role": "user", "content": "start work"}},
    {"type": "assistant", "sessionId": SID, "gitBranch": "main",
     "timestamp": "2026-06-11T02:00:00.000Z",
     "message": {"role": "assistant", "model": "claude-opus-4-8", "id": "s1",
                 "usage": {"input_tokens": 50, "output_tokens": 5,
                           "cache_read_input_tokens": 0,
                           "cache_creation_input_tokens": 0},
                 "content": [{"type": "text", "text":
                              "Resource Loop — deploying: token-efficiency "
                              "(skill) — keep it cheap"}]}},
    {"type": "assistant", "sessionId": SID, "gitBranch": "main",
     "timestamp": "2026-06-11T02:00:01.000Z",
     "message": {"role": "assistant", "model": "claude-opus-4-8", "id": "s1",
                 "usage": {"input_tokens": 50, "output_tokens": 20,
                           "cache_read_input_tokens": 0,
                           "cache_creation_input_tokens": 0},
                 "content": [{"type": "tool_use", "name": "Bash", "id": "s_tu1",
                              "input": {}}]}},
    {"type": "user", "sessionId": SID, "gitBranch": "main",
     "timestamp": "2026-06-11T02:00:02.000Z",
     "message": {"role": "user", "content": [
         {"type": "tool_result", "tool_use_id": "s_tu1", "is_error": False,
          "content": "5 passed in 0.1s"}]},
     "toolUseResult": {"stdout": "5 passed in 0.1s", "interrupted": False}},
]


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for r in records:
        if r == MALFORMED:
            lines.append("this is not valid json {{{")
        else:
            lines.append(json.dumps(r))
    path.write_text("\n".join(lines) + "\n")


def read_shard_records(metrics_dir, month):
    shard = pathlib.Path(metrics_dir) / ("%s.jsonl" % month)
    if not shard.is_file():
        return []
    return [json.loads(line) for line in shard.read_text().splitlines()
            if line.strip()]


def all_records(metrics_dir):
    out = []
    for shard in sorted(pathlib.Path(metrics_dir).glob("*.jsonl")):
        for line in shard.read_text().splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


class HarvestFixture(unittest.TestCase):
    """Base: builds a projects/<slug> tree with two subagents + a session file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        root = pathlib.Path(self.tmp)
        self.metrics = root / "metrics"
        proj = root / "projects" / SLUG
        self.session_file = proj / ("%s.jsonl" % SID)
        self.aaa = proj / SID / "subagents" / "agent-aaa.jsonl"
        self.bbb = proj / SID / "subagents" / "agent-bbb.jsonl"
        write_jsonl(self.session_file, SESSION_RECS)
        write_jsonl(self.aaa, AAA_RECS)
        write_jsonl(self.bbb, BBB_RECS)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestTaskRecord(HarvestFixture):
    def _harvest_aaa(self):
        emitted = hm.harvest(str(self.aaa), "SubagentStop", str(self.metrics))
        self.assertEqual(len(emitted), 1)
        return emitted[0]

    def test_identity_and_timing(self):
        rec = self._harvest_aaa()
        self.assertEqual(rec["schema"], 1)
        self.assertEqual(rec["kind"], "task")
        self.assertEqual(rec["task_id"], "agent-aaa")
        self.assertEqual(rec["session_id"], SID)
        self.assertEqual(rec["project"], SLUG)
        self.assertEqual(rec["git_branch"], "feature/y")   # last-seen wins
        self.assertEqual(rec["trigger"], "SubagentStop")
        self.assertEqual(rec["ts_start"], "2026-06-11T02:00:00.000Z")
        self.assertEqual(rec["ts_end"], "2026-06-11T02:00:09.000Z")
        self.assertEqual(rec["duration_s"], 9.0)
        # turns = distinct assistant message.id (m1 spans two fragments): m1,
        # m2, m3, m4(synthetic) => 4, not the 5 raw assistant records.
        self.assertEqual(rec["turns"], 4)
        self.assertEqual(rec["resources_source"], "task")   # announced its own

    def test_token_sums_dedup_by_message_id(self):
        rec = self._harvest_aaa()
        self.assertEqual(list(rec["models"].keys()), ["claude-opus-4-8"])
        m = rec["models"]["claude-opus-4-8"]
        # m1 (last frag: 100/40/50/20) + m2 (200/30/100/0) + m3 (10/10/10/10)
        self.assertEqual(m, {"in": 310, "out": 80,
                             "cache_read": 160, "cache_creation": 30})
        self.assertNotIn("<synthetic>", rec["models"])

    def test_cache_efficiency_formula(self):
        rec = self._harvest_aaa()
        # cache_read / max(1, in + cache_read + cache_creation) = 160/500
        self.assertAlmostEqual(rec["cache_efficiency"], 0.32, places=4)

    def test_tools_and_error_rate(self):
        rec = self._harvest_aaa()
        self.assertEqual(rec["tools"], {"Bash": 2, "Read": 1})
        self.assertEqual(rec["tool_errors"], 1)
        self.assertAlmostEqual(rec["error_rate"], 1 / 3, places=4)

    def test_interrupted(self):
        rec = self._harvest_aaa()
        self.assertEqual(rec["interrupted"], 1)

    def test_tests_parsing_both_and_last_wins(self):
        rec = self._harvest_aaa()
        # 34 passed (both-counts result) + 12 passed (last of "10 ... 12")
        self.assertEqual(rec["tests"],
                         {"detected": True, "passed": 46, "failed": 2})

    def test_web_from_server_tool_use(self):
        rec = self._harvest_aaa()
        self.assertEqual(rec["web"], {"search": 2, "fetch": 1})

    def test_announce_names_extracted(self):
        rec = self._harvest_aaa()
        self.assertEqual(rec["resources_deployed"],
                         ["sports-analyst", "data-visualization"])
        self.assertTrue(rec["announce_found"])
        self.assertFalse(rec["bare"])

    def test_compactions_zero_at_task_level(self):
        rec = self._harvest_aaa()
        self.assertEqual(rec["compactions"], 0)

    def test_month_shard_from_ts_end(self):
        self._harvest_aaa()
        self.assertTrue((self.metrics / "2026-06.jsonl").is_file())
        self.assertEqual(len(read_shard_records(self.metrics, "2026-06")), 1)


class TestBareAndDedup(HarvestFixture):
    def test_bare_announce_and_july_shard(self):
        emitted = hm.harvest(str(self.bbb), "SubagentStop", str(self.metrics))
        rec = emitted[0]
        self.assertEqual(rec["task_id"], "agent-bbb")
        self.assertTrue(rec["bare"])
        self.assertTrue(rec["announce_found"])
        self.assertEqual(rec["resources_deployed"], [])
        self.assertEqual(rec["tests"]["detected"], False)
        self.assertEqual(rec["tools"], {"Read": 1})
        # n1 spans two records; last-wins usage => out=8, not 10.
        self.assertEqual(rec["models"]["claude-sonnet-4"],
                         {"in": 10, "out": 8, "cache_read": 0,
                          "cache_creation": 0})
        # ts_end is in July => the July shard, not June.
        self.assertTrue((self.metrics / "2026-07.jsonl").is_file())
        self.assertFalse((self.metrics / "2026-06.jsonl").is_file())


class TestCursorIdempotency(HarvestFixture):
    def test_unchanged_transcript_emits_nothing_on_second_run(self):
        first = hm.harvest(str(self.aaa), "SubagentStop", str(self.metrics))
        self.assertEqual(len(first), 1)
        second = hm.harvest(str(self.aaa), "SubagentStop", str(self.metrics))
        self.assertEqual(second, [])
        self.assertEqual(len(read_shard_records(self.metrics, "2026-06")), 1)

    def test_cursor_file_written_atomically(self):
        hm.harvest(str(self.aaa), "SubagentStop", str(self.metrics))
        cursor = self.metrics / "state" / "harvest.cursor.json"
        self.assertTrue(cursor.is_file())
        data = json.loads(cursor.read_text())
        key = str(self.aaa.resolve())
        self.assertIn(key, data)
        self.assertIn("mtime", data[key])
        self.assertIn("size", data[key])
        self.assertEqual(data[key]["records_emitted"], 1)

    def test_grown_transcript_appends_replacement_last_wins(self):
        hm.harvest(str(self.aaa), "SubagentStop", str(self.metrics))
        # Grow the transcript with one more Bash tool call (changes size).
        extra = {"type": "assistant", "sessionId": SID, "gitBranch": "feature/y",
                 "timestamp": "2026-06-11T02:00:10.000Z",
                 "message": {"role": "assistant", "model": "claude-opus-4-8",
                             "id": "m9",
                             "usage": {"input_tokens": 1, "output_tokens": 1,
                                       "cache_read_input_tokens": 0,
                                       "cache_creation_input_tokens": 0},
                             "content": [{"type": "tool_use", "name": "Bash",
                                          "id": "tu9", "input": {}}]}}
        with open(self.aaa, "a") as f:
            f.write(json.dumps(extra) + "\n")
        again = hm.harvest(str(self.aaa), "SubagentStop", str(self.metrics))
        self.assertEqual(len(again), 1)   # a replacement record was appended
        recs = read_shard_records(self.metrics, "2026-06")
        task_recs = [r for r in recs
                     if r["task_id"] == "agent-aaa" and r["kind"] == "task"]
        self.assertEqual(len(task_recs), 2)   # both kept; consumers take last
        last = task_recs[-1]
        self.assertEqual(last["tools"], {"Bash": 3, "Read": 1})   # grew by one Bash
        self.assertEqual(last["ts_end"], "2026-06-11T02:00:10.000Z")


class TestSessionRollup(HarvestFixture):
    def test_session_end_rollup_and_catchup(self):
        emitted = hm.harvest(str(self.session_file), "SessionEnd",
                             str(self.metrics))
        # Two catch-up tasks + one session record + one session-backfill
        # re-emit for the un-announced agent-bbb (agent-aaa announced its own
        # resources, so it is NOT backfilled) => four records.
        kinds = sorted(r["kind"] for r in emitted)
        self.assertEqual(kinds, ["session", "task", "task", "task"])
        session = [r for r in emitted if r["kind"] == "session"][0]
        self.assertEqual(session["task_id"], "session-%s" % SID)
        self.assertEqual(session["trigger"], "SessionEnd")
        self.assertEqual(session["resources_source"], "session")
        self.assertEqual(session["tasks_harvested"], 2)   # cursor catch-up only
        # turns = distinct assistant message.id: s1 spans two fragments => 1.
        self.assertEqual(session["turns"], 1)
        self.assertEqual(session["tools"], {"Bash": 1})
        self.assertEqual(session["tests"],
                         {"detected": True, "passed": 5, "failed": 0})
        self.assertEqual(session["resources_deployed"], ["token-efficiency"])
        self.assertEqual(session["models"]["claude-opus-4-8"],
                         {"in": 50, "out": 20, "cache_read": 0,
                          "cache_creation": 0})
        self.assertEqual(session["ts_end"], "2026-06-11T02:00:02.000Z")
        # The two subagent tasks were harvested as kind:"task"; agent-bbb also
        # gets a backfill re-emit, so it appears twice.
        task_ids = sorted(r["task_id"] for r in emitted if r["kind"] == "task")
        self.assertEqual(task_ids, ["agent-aaa", "agent-bbb", "agent-bbb"])

    def test_catchup_skips_already_cursored_subagents(self):
        # Harvest agent-aaa first (as if at its own SubagentStop).
        hm.harvest(str(self.aaa), "SubagentStop", str(self.metrics))
        emitted = hm.harvest(str(self.session_file), "SessionEnd",
                             str(self.metrics))
        session = [r for r in emitted if r["kind"] == "session"][0]
        # Only agent-bbb is un-cursored now => 1 catch-up task. tasks_harvested
        # counts cursor catch-up only, never the backfill re-emit.
        self.assertEqual(session["tasks_harvested"], 1)
        harvested_tasks = sorted(r["task_id"] for r in emitted
                                 if r["kind"] == "task")
        # agent-bbb catch-up task + agent-bbb session-backfill re-emit.
        self.assertEqual(harvested_tasks, ["agent-bbb", "agent-bbb"])

    def test_session_backfill_enriches_unannounced_tasks(self):
        # C1: a session that announced (token-efficiency) + two subagents,
        # one that announced its own resources (agent-aaa) and one that did
        # not (agent-bbb, a bare announce => empty). SessionEnd must backfill
        # only the un-announced task, via a last-wins replacement record.
        hm.harvest(str(self.session_file), "SessionEnd", str(self.metrics))
        recs = all_records(self.metrics)

        session = [r for r in recs if r["kind"] == "session"][0]
        self.assertEqual(session["resources_deployed"], ["token-efficiency"])
        self.assertEqual(session["resources_source"], "session")

        # agent-aaa announced its own resources => one record, source "task",
        # NOT backfilled (no unchanged-duplicate re-emit).
        aaa = [r for r in recs if r["task_id"] == "agent-aaa"]
        self.assertEqual(len(aaa), 1)
        self.assertEqual(aaa[-1]["resources_source"], "task")
        self.assertEqual(aaa[-1]["resources_deployed"],
                         ["sports-analyst", "data-visualization"])

        # agent-bbb announced bare (empty) => two records; its LAST record is
        # the backfill carrying the session's resources + "session-backfill".
        bbb = [r for r in recs if r["task_id"] == "agent-bbb"]
        self.assertEqual(len(bbb), 2)
        self.assertEqual(bbb[0]["resources_source"], "task")
        self.assertEqual(bbb[0]["resources_deployed"], [])
        self.assertEqual(bbb[-1]["kind"], "task")
        self.assertEqual(bbb[-1]["resources_source"], "session-backfill")
        self.assertEqual(bbb[-1]["resources_deployed"], ["token-efficiency"])

    def test_repeated_session_end_backfills_once(self):
        # N1: resumed sessions fire SessionEnd repeatedly. Three consecutive
        # SessionEnd harvests of an UNCHANGED session must emit exactly ONE
        # backfill record total — the shard must not grow on runs 2 and 3.
        hm.harvest(str(self.session_file), "SessionEnd", str(self.metrics))
        count_after_first = len(all_records(self.metrics))
        second = hm.harvest(str(self.session_file), "SessionEnd",
                            str(self.metrics))
        third = hm.harvest(str(self.session_file), "SessionEnd",
                           str(self.metrics))
        self.assertEqual(second, [])
        self.assertEqual(third, [])
        recs = all_records(self.metrics)
        self.assertEqual(len(recs), count_after_first)   # shard stable
        backfills = [r for r in recs
                     if r.get("resources_source") == "session-backfill"]
        self.assertEqual(len(backfills), 1)

    def test_backfill_self_heals_after_task_reemit(self):
        # N1 case (a): after a backfill, the subagent transcript grows and a
        # post-backfill SubagentStop re-emits a fresh empty-resources task
        # record that supersedes the backfill (last-wins). The next SessionEnd
        # must emit a NEW backfill so the task's LAST record is enriched again.
        hm.harvest(str(self.session_file), "SessionEnd", str(self.metrics))
        extra = {"type": "assistant", "sessionId": SID, "gitBranch": "main",
                 "timestamp": "2026-07-02T10:00:04.000Z",
                 "message": {"role": "assistant", "model": "claude-sonnet-4",
                             "id": "n2",
                             "usage": {"input_tokens": 5, "output_tokens": 5,
                                       "cache_read_input_tokens": 0,
                                       "cache_creation_input_tokens": 0},
                             "content": [{"type": "text",
                                          "text": "more work"}]}}
        with open(self.bbb, "a") as f:
            f.write(json.dumps(extra) + "\n")
        hm.harvest(str(self.bbb), "SubagentStop", str(self.metrics))
        hm.harvest(str(self.session_file), "SessionEnd", str(self.metrics))
        bbb = [r for r in all_records(self.metrics)
               if r["task_id"] == "agent-bbb"]
        backfills = [r for r in bbb
                     if r["resources_source"] == "session-backfill"]
        self.assertEqual(len(backfills), 2)   # a NEW backfill was emitted
        self.assertEqual(bbb[-1]["resources_source"], "session-backfill")
        self.assertEqual(bbb[-1]["resources_deployed"], ["token-efficiency"])

    def test_backfill_reemitted_when_session_resources_change(self):
        # N1 case (c): the session's resource list changes between SessionEnds
        # (parse_announce is first-match-wins, so the change must edit the
        # announce line itself — an appended second announce is ignored by
        # design). A new backfill with the NEW list must be emitted once, and
        # a further unchanged SessionEnd must emit nothing.
        import copy
        hm.harvest(str(self.session_file), "SessionEnd", str(self.metrics))
        recs = copy.deepcopy(SESSION_RECS)
        for r in recs:
            if r.get("type") != "assistant":
                continue
            for block in r["message"].get("content", []):
                if (isinstance(block, dict) and block.get("type") == "text"
                        and "deploying" in block.get("text", "")):
                    block["text"] = ("Resource Loop — deploying: "
                                     "token-efficiency (skill), extra-skill "
                                     "(skill) — broader work")
        write_jsonl(self.session_file, recs)
        hm.harvest(str(self.session_file), "SessionEnd", str(self.metrics))
        hm.harvest(str(self.session_file), "SessionEnd", str(self.metrics))
        bbb = [r for r in all_records(self.metrics)
               if r["task_id"] == "agent-bbb"]
        backfills = [r for r in bbb
                     if r["resources_source"] == "session-backfill"]
        self.assertEqual(len(backfills), 2)   # one per distinct resource list
        self.assertEqual(bbb[-1]["resources_source"], "session-backfill")
        self.assertEqual(bbb[-1]["resources_deployed"],
                         ["token-efficiency", "extra-skill"])

    def test_session_with_no_announce_emits_no_backfill(self):
        # A session whose main thread never announced has no resources to
        # backfill, so NO session-backfill records are emitted even though
        # agent-bbb is un-announced.
        import copy
        recs = copy.deepcopy(SESSION_RECS)
        for r in recs:
            if r.get("type") == "assistant":
                for block in r["message"].get("content", []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        block["text"] = "working on it"
        write_jsonl(self.session_file, recs)

        emitted = hm.harvest(str(self.session_file), "SessionEnd",
                             str(self.metrics))
        session = [r for r in emitted if r["kind"] == "session"][0]
        self.assertEqual(session["resources_deployed"], [])
        backfills = [r for r in all_records(self.metrics)
                     if r.get("resources_source") == "session-backfill"]
        self.assertEqual(backfills, [])


class TestCliAndErrors(HarvestFixture):
    def test_missing_transcript_exits_zero(self):
        missing = str(pathlib.Path(self.tmp) / "does-not-exist.jsonl")
        rc = hm.main(["--transcript", missing, "--event", "SubagentStop",
                      "--metrics-dir", str(self.metrics)])
        self.assertEqual(rc, 0)
        self.assertEqual(all_records(self.metrics), [])

    def test_unknown_event_exits_two(self):
        rc = hm.main(["--transcript", str(self.aaa), "--event", "BogusEvent",
                      "--metrics-dir", str(self.metrics)])
        self.assertEqual(rc, 2)

    def test_cli_happy_path_writes_record(self):
        rc = hm.main(["--transcript", str(self.aaa), "--event", "SubagentStop",
                      "--metrics-dir", str(self.metrics)])
        self.assertEqual(rc, 0)
        self.assertEqual(len(read_shard_records(self.metrics, "2026-06")), 1)

    def test_session_id_override(self):
        rec = hm.harvest(str(self.aaa), "SubagentStop", str(self.metrics),
                         session_id="override-sid")[0]
        self.assertEqual(rec["session_id"], "override-sid")


class TestParsingUnits(unittest.TestCase):
    def test_parse_announce_multi(self):
        names, found, bare = hm.parse_announce([
            "Resource Loop — deploying: sports-analyst (skill), "
            "data-visualization (skill) — layered viz work"])
        self.assertEqual(names, ["sports-analyst", "data-visualization"])
        self.assertTrue(found)
        self.assertFalse(bare)

    def test_parse_announce_semicolon(self):
        names, found, bare = hm.parse_announce([
            "Resource Loop — deploying: alpha (skill); beta (tool)"])
        self.assertEqual(names, ["alpha", "beta"])
        self.assertTrue(found)

    def test_parse_announce_single(self):
        names, found, bare = hm.parse_announce([
            "chatter first",
            "Resource Loop — deploying: token-efficiency (skill) — cheap"])
        self.assertEqual(names, ["token-efficiency"])

    def test_parse_announce_bare(self):
        names, found, bare = hm.parse_announce([
            "Resource Loop — no registry match; proceeding bare."])
        self.assertEqual(names, [])
        self.assertTrue(found)
        self.assertTrue(bare)

    def test_parse_announce_none(self):
        names, found, bare = hm.parse_announce(["just some prose", "no loop here"])
        self.assertEqual(names, [])
        self.assertFalse(found)
        self.assertFalse(bare)

    def test_parse_announce_first_match_wins(self):
        names, found, bare = hm.parse_announce([
            "Resource Loop — deploying: first-one (skill)",
            "Resource Loop — no registry match; proceeding bare."])
        self.assertEqual(names, ["first-one"])
        self.assertFalse(bare)

    def test_announce_name_is_redacted(self):
        # A stored resource name is passed through redact() — a JWT-shaped
        # token in the name must not survive into the record.
        names, _, _ = hm.parse_announce([
            "Resource Loop — deploying: eyJabc.def.ghi (skill)"])
        self.assertEqual(len(names), 1)
        self.assertIn("[REDACTED", names[0])

    def test_parse_tests_both_counts(self):
        self.assertEqual(hm.parse_tests("34 passed, 2 failed in 1.2s"),
                         (34, 2, True))

    def test_parse_tests_last_wins(self):
        self.assertEqual(hm.parse_tests("10 passed then 12 passed"),
                         (12, 0, True))

    def test_parse_tests_vitest(self):
        p, f, d = hm.parse_tests("Test Files  1 failed | 3 passed (4)")
        self.assertEqual((p, f, d), (3, 1, True))

    def test_parse_tests_two_frameworks_summed(self):
        # I2: pytest + vitest summaries in one result must both be counted —
        # per-framework last match, then summed: 34+3 passed, 2+1 failed.
        p, f, d = hm.parse_tests(
            "34 passed, 2 failed\nTest Files  1 failed | 3 passed (4)")
        self.assertEqual((p, f, d), (37, 3, True))

    def test_parse_tests_none(self):
        self.assertEqual(hm.parse_tests("no test output here"), (0, 0, False))

    def test_turns_dedupe_fragmented_assistant_messages(self):
        # I1: three assistant records, two distinct message.id values — one
        # streamed turn split across two fragments (id "x") plus a second turn
        # (id "y"). turns must dedupe to 2, matching the token dedup identity.
        recs = [
            {"type": "assistant", "sessionId": "s",
             "timestamp": "2026-06-01T00:00:00.000Z",
             "message": {"role": "assistant", "model": "claude-opus-4-8",
                         "id": "x",
                         "usage": {"input_tokens": 1, "output_tokens": 1,
                                   "cache_read_input_tokens": 0,
                                   "cache_creation_input_tokens": 0},
                         "content": [{"type": "text", "text": "part one"}]}},
            {"type": "assistant", "sessionId": "s",
             "timestamp": "2026-06-01T00:00:01.000Z",
             "message": {"role": "assistant", "model": "claude-opus-4-8",
                         "id": "x",
                         "usage": {"input_tokens": 1, "output_tokens": 2,
                                   "cache_read_input_tokens": 0,
                                   "cache_creation_input_tokens": 0},
                         "content": [{"type": "tool_use", "name": "Read",
                                      "id": "t", "input": {}}]}},
            {"type": "assistant", "sessionId": "s",
             "timestamp": "2026-06-01T00:00:02.000Z",
             "message": {"role": "assistant", "model": "claude-opus-4-8",
                         "id": "y",
                         "usage": {"input_tokens": 1, "output_tokens": 1,
                                   "cache_read_input_tokens": 0,
                                   "cache_creation_input_tokens": 0},
                         "content": [{"type": "text", "text": "second"}]}},
        ]
        agg = hm._aggregate(recs)
        self.assertEqual(agg["turns"], 2)


if __name__ == "__main__":
    unittest.main()
