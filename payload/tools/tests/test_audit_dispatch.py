#!/usr/bin/env python3
"""Tests for audit_dispatch — the due-calculation policy for the repo audit scheduler.

Hermetic: every case builds its store and workspace under
``tempfile.mkdtemp()`` and tears them down afterward. Nothing here touches
the real ``~/.claude`` tree, and no package name here is a real client
package — the module under test is generic and only ever sees names like
"a", "b", "p" passed in by the test.
"""
import contextlib
import datetime
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import audit_dispatch as ad  # noqa: E402  (path set up above)
import audit_store as st  # noqa: E402

NOW = datetime.datetime(2026, 7, 31, tzinfo=datetime.timezone.utc)


def state(days_ago=None, sha="aaa"):
    if days_ago is None:
        return {}
    d = NOW - datetime.timedelta(days=days_ago)
    return {"last_audit_date": d.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_audited_sha": sha}


class TestIsDue(unittest.TestCase):
    def test_never_audited_is_due(self):
        due, why = ad.is_due("p", 7, {}, "aaa", NOW)
        self.assertTrue(due)
        self.assertIn("never", why.lower())

    def test_interval_not_elapsed_is_not_due(self):
        due, _ = ad.is_due("p", 7, state(3, "aaa"), "bbb", NOW)
        self.assertFalse(due)

    def test_interval_elapsed_and_head_moved_is_due(self):
        due, _ = ad.is_due("p", 7, state(10, "aaa"), "bbb", NOW)
        self.assertTrue(due)

    def test_interval_elapsed_but_head_unchanged_is_skipped(self):
        due, why = ad.is_due("p", 7, state(10, "aaa"), "aaa", NOW)
        self.assertFalse(due)
        self.assertIn("unchanged", why.lower())

    def test_unknown_head_is_due_rather_than_silently_skipped(self):
        # A package we cannot read a SHA for must not be silently dropped.
        due, why = ad.is_due("p", 7, state(10, "aaa"), None, NOW)
        self.assertTrue(due)
        self.assertIn("unknown", why.lower())

    def test_malformed_date_in_state_is_treated_as_never_audited(self):
        due, _ = ad.is_due("p", 7, {"last_audit_date": "garbage",
                                    "last_audited_sha": "aaa"}, "bbb", NOW)
        self.assertTrue(due)

    def test_unknown_head_wins_even_when_interval_not_elapsed(self):
        # Decision: an unreadable head is loud, not merged into the interval
        # check — a package we can't verify must never be silently skipped
        # just because its last-audit date is recent.
        due, why = ad.is_due("p", 7, state(1, "aaa"), None, NOW)
        self.assertTrue(due)
        self.assertIn("unknown", why.lower())


class TestHeadSha(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_head_sha_for_a_git_repo(self):
        subprocess.run(["git", "init", "-q"], cwd=self.tmp, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"],
                        cwd=self.tmp, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"],
                        cwd=self.tmp, capture_output=True)
        (pathlib.Path(self.tmp) / "f.txt").write_text("x")
        subprocess.run(["git", "add", "f.txt"], cwd=self.tmp, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"],
                        cwd=self.tmp, capture_output=True)
        expected = subprocess.run(
            ["git", "-C", self.tmp, "rev-parse", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(ad.head_sha(self.tmp), expected)

    def test_returns_none_for_a_non_git_directory(self):
        self.assertIsNone(ad.head_sha(self.tmp))

    def test_returns_none_for_a_nonexistent_path(self):
        self.assertIsNone(ad.head_sha(str(pathlib.Path(self.tmp) / "nope")))

    def test_returns_none_rather_than_raising_for_empty_path(self):
        self.assertIsNone(ad.head_sha(""))
        self.assertIsNone(ad.head_sha(None))


class TestLastState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_runs_directory_returns_empty_dict(self):
        self.assertEqual(ad.last_state(self.tmp, "p"), {})

    def test_no_run_files_returns_empty_dict(self):
        (pathlib.Path(self.tmp) / "audit" / "runs" / "p").mkdir(parents=True)
        self.assertEqual(ad.last_state(self.tmp, "p"), {})

    def test_returns_the_most_recent_run_log(self):
        run_dir = pathlib.Path(self.tmp) / "audit" / "runs" / "p"
        run_dir.mkdir(parents=True)
        (run_dir / "2026-07-01.json").write_text(
            json.dumps({"last_audit_date": "2026-07-01T00:00:00Z",
                        "last_audited_sha": "old"}))
        (run_dir / "2026-07-15.json").write_text(
            json.dumps({"last_audit_date": "2026-07-15T00:00:00Z",
                        "last_audited_sha": "new"}))
        self.assertEqual(ad.last_state(self.tmp, "p")["last_audited_sha"], "new")

    def test_malformed_run_log_returns_empty_dict_rather_than_raising(self):
        run_dir = pathlib.Path(self.tmp) / "audit" / "runs" / "p"
        run_dir.mkdir(parents=True)
        (run_dir / "2026-07-01.json").write_text("{not json")
        self.assertEqual(ad.last_state(self.tmp, "p"), {})


class TestSelectDue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        (pathlib.Path(self.tmp) / "audit" / "runs").mkdir(parents=True)
        self.ws = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.ws, ignore_errors=True)

    def cfg(self, cap=3):
        return {"schema": 1, "per_night_cap": cap, "tiers": {
            "weekly": {"interval_days": 7, "packages": ["a", "b", "c", "d"]}}}

    def test_cap_is_enforced(self):
        picked = ad.select_due(self.tmp, self.cfg(cap=2), self.ws, NOW)
        self.assertLessEqual(len(picked), 2)

    def test_excluded_tier_is_never_selected(self):
        cfg = self.cfg()
        cfg["tiers"]["excluded"] = {"interval_days": 0, "packages": ["z"]}
        picked = [p["package"] for p in ad.select_due(self.tmp, cfg, self.ws, NOW)]
        self.assertNotIn("z", picked)

    def test_each_entry_carries_a_reason(self):
        for p in ad.select_due(self.tmp, self.cfg(), self.ws, NOW):
            self.assertTrue(p["reason"])

    def test_package_absent_from_disk_is_due_not_an_error(self):
        # "a" is in config but no such directory exists under the workspace,
        # and it has never been audited (no run log) -> due, not an error.
        picked = {p["package"]: p for p in ad.select_due(self.tmp, self.cfg(), self.ws, NOW)}
        self.assertIn("a", picked)
        self.assertTrue(picked["a"]["due"])
        self.assertIsNone(picked["a"]["head"])

    def test_package_absent_from_disk_with_prior_audit_is_due_as_unknown(self):
        # "a" has a recorded prior audit, but no directory on disk now ->
        # head_sha comes back None -> due as "unknown", not "never audited".
        run_dir = pathlib.Path(self.tmp) / "audit" / "runs" / "a"
        run_dir.mkdir(parents=True)
        (run_dir / "2026-01-01.json").write_text(json.dumps({
            "last_audit_date": "2026-01-01T00:00:00Z",
            "last_audited_sha": "old",
        }))
        # Uncapped, so this isolates the reason-text behavior from the
        # separately-tested cap/sort-priority interaction: a package with
        # real audit history sorts by its actual staleness, not as
        # maximally overdue, so a small cap could legitimately drop it.
        picked = {p["package"]: p for p in ad.select_due(self.tmp, self.cfg(cap=10), self.ws, NOW)}
        self.assertIn("a", picked)
        self.assertIn("unknown", picked["a"]["reason"].lower())

    def _write_run_log(self, pkg, days_ago, sha):
        run_dir = pathlib.Path(self.tmp) / "audit" / "runs" / pkg
        run_dir.mkdir(parents=True)
        (run_dir / "log.json").write_text(json.dumps(state(days_ago, sha)))

    def test_longest_overdue_sorts_first(self):
        # Four due packages at clearly different staleness. None exist on
        # disk under self.ws, so head is unknown for all of them and every
        # one is due regardless of interval — that isolates the *sort*
        # itself (the thing under test) from the due/not-due decision
        # (covered elsewhere). "d" has no run log at all (never audited),
        # which must be the single most-overdue case of the four.
        self._write_run_log("a", 60, "sha-a")
        self._write_run_log("b", 30, "sha-b")
        self._write_run_log("c", 10, "sha-c")
        cfg = {"schema": 1, "per_night_cap": 10, "tiers": {
            "weekly": {"interval_days": 7, "packages": ["a", "b", "c", "d"]}}}
        picked = [p["package"] for p in ad.select_due(self.tmp, cfg, self.ws, NOW)]
        self.assertEqual(picked, ["d", "a", "b", "c"])

    def test_cap_keeps_the_most_overdue_entries(self):
        # Same four packages/staleness as above, but capped to 2 — the two
        # kept must be the two MOST overdue ("d" then "a"), not just any 2
        # of the 4 due packages. Distinguishes a real sort-then-truncate
        # from a cap applied to an arbitrary/insertion order.
        self._write_run_log("a", 60, "sha-a")
        self._write_run_log("b", 30, "sha-b")
        self._write_run_log("c", 10, "sha-c")
        cfg = {"schema": 1, "per_night_cap": 2, "tiers": {
            "weekly": {"interval_days": 7, "packages": ["a", "b", "c", "d"]}}}
        picked = [p["package"] for p in ad.select_due(self.tmp, cfg, self.ws, NOW)]
        self.assertEqual(picked, ["d", "a"])


class TestSelectDueResilience(unittest.TestCase):
    """A broken package must not abort the whole nightly selection."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        (pathlib.Path(self.tmp) / "audit" / "runs").mkdir(parents=True)
        self.ws = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_one_broken_package_does_not_abort_the_rest(self):
        cfg = {"schema": 1, "per_night_cap": 10, "tiers": {
            "weekly": {"interval_days": 7, "packages": ["a", "b"]}}}
        real_head_sha = ad.head_sha

        def boom(pkg_path):
            if pkg_path.rstrip("/").endswith(("/a", "\\a")):
                raise RuntimeError("disk exploded")
            return real_head_sha(pkg_path)

        with mock.patch.object(ad, "head_sha", side_effect=boom):
            picked = ad.select_due(self.tmp, cfg, self.ws, NOW)

        by_name = {p["package"]: p for p in picked}
        self.assertIn("a", by_name)
        self.assertIn("b", by_name)
        self.assertIn("disk exploded", by_name["a"]["reason"])
        self.assertTrue(by_name["a"]["due"])

    def test_non_dict_tier_does_not_abort_other_tiers(self):
        # Reachable from a hand-edited config.json: audit_store.load_config
        # does not validate tier shape. A tier value that isn't a dict must
        # not take the whole selection down with it.
        cfg = {"schema": 1, "per_night_cap": 10, "tiers": {
            "broken": ["not", "a", "dict"],
            "weekly": {"interval_days": 7, "packages": ["a"]}}}
        picked = ad.select_due(self.tmp, cfg, self.ws, NOW)
        names = [p["package"] for p in picked]
        self.assertIn("a", names)

    def test_non_dict_tier_reports_itself_as_a_loud_due_entry(self):
        cfg = {"schema": 1, "per_night_cap": 10, "tiers": {
            "broken": ["not", "a", "dict"]}}
        picked = ad.select_due(self.tmp, cfg, self.ws, NOW)
        self.assertEqual(len(picked), 1)
        self.assertTrue(picked[0]["due"])
        self.assertIn("broken", picked[0]["reason"])

    def test_non_string_package_entry_does_not_abort_the_tier(self):
        # A stray numeric id (or any non-string) in "packages" must become
        # a loud due entry for itself, not an AttributeError/TypeError that
        # takes its sibling packages down with it.
        cfg = {"schema": 1, "per_night_cap": 10, "tiers": {
            "weekly": {"interval_days": 7, "packages": [123, "a"]}}}
        picked = ad.select_due(self.tmp, cfg, self.ws, NOW)
        names = [p["package"] for p in picked]
        self.assertIn("a", names)
        self.assertIn(123, names)
        broken = [p for p in picked if p["package"] == 123][0]
        self.assertTrue(broken["due"])
        self.assertTrue(broken["reason"])


class TestMainCli(unittest.TestCase):
    """The preview surface. Every case is --dry-run: a plain invocation now
    SWEEPS, and a test suite must never be one command-line flag away from
    starting a real, billed agent session."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        st.ensure_store(self.tmp)
        cfg_path = pathlib.Path(self.tmp) / "audit" / "config.json"
        cfg_path.write_text(json.dumps({
            "schema": 1, "per_night_cap": 5,
            "tiers": {"weekly": {"interval_days": 7, "packages": ["a", "b"]}}}))
        self.ws = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_json_output_lists_due_packages(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ad.main(["--root", self.tmp, "--workspace", self.ws,
                          "--json", "--dry-run"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["dry_run"])
        self.assertEqual({e["package"] for e in payload["due"]}, {"a", "b"})

    def test_human_output_names_every_due_package(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ad.main(["--root", self.tmp, "--workspace", self.ws, "--dry-run"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("a — ", out)
        self.assertIn("b — ", out)


class TestLastStateKeyRoundTrip(unittest.TestCase):
    """The store key that gets WRITTEN must be the one that gets READ.

    A key is the package's string in ``config.json``, and real keys are
    workspace-relative paths, so a run log lands at
    ``runs/<client-dir>/<package>/``. While ``audit_run.sh`` re-derived the
    key from the package directory's basename, state was written one level
    shallower than this function looks — so every nested package reported
    "never audited" every single night, at full agent cost. ``--key`` closes
    that; these cases pin it from the reader's side, and
    ``test_audit_run.sh`` case 15 pins the writer's.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, key, name, payload):
        run_dir = pathlib.Path(self.tmp) / "audit" / "runs" / key
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / name).write_text(json.dumps(payload))

    def test_a_nested_key_round_trips(self):
        self._write("client-dir/pkg", "state.json",
                    {"last_audit_date": "2026-07-30T03:00:00Z",
                     "last_audited_sha": "nested"})
        self.assertEqual(
            ad.last_state(self.tmp, "client-dir/pkg")["last_audited_sha"],
            "nested")

    def test_a_nested_key_is_not_found_under_its_basename(self):
        self._write("client-dir/pkg", "state.json",
                    {"last_audit_date": "2026-07-30T03:00:00Z",
                     "last_audited_sha": "nested"})
        self.assertEqual(ad.last_state(self.tmp, "pkg"), {})

    def test_a_nested_package_with_state_is_not_due(self):
        self._write("client-dir/pkg", "state.json",
                    {"last_audit_date": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "last_audited_sha": "same"})
        cfg = {"schema": 1, "per_night_cap": 10, "tiers": {
            "weekly": {"interval_days": 7, "packages": ["client-dir/pkg"]}}}
        ws = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, ws, ignore_errors=True)
        with mock.patch.object(ad, "head_sha", return_value="same"):
            picked = ad.select_due(self.tmp, cfg, ws, NOW)
        self.assertEqual(picked, [])

    def test_last_run_record_ignores_the_state_marker(self):
        self._write("pkg", "state.json", {"verdict": "ok", "marker": True})
        self._write("pkg", "2026-07-31.json", {"verdict": "failed"})
        self.assertEqual(ad.last_run_record(self.tmp, "pkg")["verdict"], "failed")


def _stub_runner(directory, script):
    """Write an executable audit_run.sh stand-in and return its path.

    NO test may invoke a real ``claude`` session, and the cheapest way to
    guarantee that is for no test to invoke the real ``audit_run.sh`` either.
    Every orchestration case injects one of these instead.
    """
    path = pathlib.Path(directory) / "audit-run-stub.sh"
    path.write_text(script)
    path.chmod(0o755)
    return str(path)


class TestOrchestration(unittest.TestCase):
    """Dispatch has to actually drive the sweep, not just describe it.

    The launchd job invokes this module and nothing else, so if the due list
    never reaches ``audit_run.sh`` the whole layer is inert: it decides what
    to audit every night and audits none of it.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        st.ensure_store(self.tmp)
        (pathlib.Path(self.tmp) / "audit" / "config.json").write_text(json.dumps({
            "schema": 1, "per_night_cap": 5,
            "tiers": {"weekly": {"interval_days": 7,
                                 "packages": ["client-dir/a", "client-dir/b"]}}}))
        self.ws = tempfile.mkdtemp()
        self.calls = str(pathlib.Path(self.tmp) / "calls.log")
        self.env = mock.patch.dict(os.environ, {"AUDIT_NOTIFY": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.ws, ignore_errors=True)

    def _runner(self, script):
        return _stub_runner(self.tmp, script)

    def _recording_stub(self, extra=""):
        return (
            "#!/bin/bash\n"
            'printf "%s|%s\\n" "$1" "$4" >> ' + self.calls + "\n" + extra
        )

    def _main(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ad.main(["--root", self.tmp, "--workspace", self.ws] + list(argv))
        return rc, buf.getvalue()

    def _logged_calls(self):
        try:
            return [l for l in pathlib.Path(self.calls).read_text().splitlines() if l]
        except OSError:
            return []

    def test_every_due_package_is_run_sequentially_with_its_key(self):
        runner = self._runner(self._recording_stub())
        rc, _ = self._main("--audit-run-bin", runner)
        self.assertEqual(rc, 0)
        calls = self._logged_calls()
        self.assertEqual(len(calls), 2)
        keys = [line.split("|")[1] for line in calls]
        self.assertEqual(sorted(keys), ["client-dir/a", "client-dir/b"])
        for line in calls:
            path, key = line.split("|")
            self.assertEqual(path, os.path.join(self.ws, key))

    def test_one_failing_package_does_not_abort_the_batch(self):
        runner = self._runner(self._recording_stub(
            extra='case "$4" in */a) exit 1 ;; esac\n'))
        rc, out = self._main("--audit-run-bin", runner)
        self.assertEqual(rc, 0)
        keys = [line.split("|")[1] for line in self._logged_calls()]
        self.assertEqual(sorted(keys), ["client-dir/a", "client-dir/b"])
        self.assertIn("exit 1", out)

    def test_a_runner_that_cannot_be_executed_does_not_abort_the_batch(self):
        rc, out = self._main("--audit-run-bin",
                             str(pathlib.Path(self.tmp) / "does-not-exist.sh"))
        self.assertEqual(rc, 0)
        self.assertIn("client-dir/a", out)
        self.assertIn("client-dir/b", out)

    def test_dry_run_invokes_nothing(self):
        runner = self._runner(self._recording_stub())
        with mock.patch.object(ad.audit_digest, "write_digest") as digest:
            rc, out = self._main("--audit-run-bin", runner, "--dry-run")
        self.assertEqual(rc, 0)
        self.assertEqual(self._logged_calls(), [])
        digest.assert_not_called()
        self.assertIn("would run", out)
        self.assertIn("--key client-dir/a", out)

    def test_the_digest_is_written_once_at_the_end(self):
        runner = self._runner(self._recording_stub())
        with mock.patch.object(ad.audit_digest, "write_digest",
                               return_value="/tmp/digest.md") as digest:
            rc, _ = self._main("--audit-run-bin", runner)
        self.assertEqual(rc, 0)
        self.assertEqual(digest.call_count, 1)

    def test_nothing_due_runs_nothing_and_writes_no_digest(self):
        (pathlib.Path(self.tmp) / "audit" / "config.json").write_text(json.dumps({
            "schema": 1, "per_night_cap": 5, "tiers": {}}))
        runner = self._runner(self._recording_stub())
        with mock.patch.object(ad.audit_digest, "write_digest") as digest:
            rc, out = self._main("--audit-run-bin", runner)
        self.assertEqual(rc, 0)
        self.assertIn("nothing due", out)
        self.assertEqual(self._logged_calls(), [])
        digest.assert_not_called()

    def test_a_run_that_leaves_no_log_is_alerted_rather_than_ignored(self):
        runner = self._runner(self._recording_stub())
        notified = []
        with mock.patch.object(ad, "_notify", side_effect=notified.append):
            rc, out = self._main("--audit-run-bin", runner)
        self.assertEqual(rc, 0)
        self.assertEqual(len(notified), 2)
        self.assertIn("left no log", out)

    def test_a_critical_finding_in_a_run_log_raises_an_alert(self):
        run_dir = pathlib.Path(self.tmp) / "audit" / "runs" / "client-dir" / "a"
        run_dir.mkdir(parents=True)
        future = (datetime.datetime.now(datetime.timezone.utc)
                  + datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        runner = self._runner(self._recording_stub())
        (run_dir / "2026-07-31.json").write_text(json.dumps({
            "package": "client-dir/a", "verdict": "ok", "run_at": future,
            "findings": {"critical": 2, "high": 0, "medium": 0, "low": 0}}))
        notified = []
        with mock.patch.object(ad, "_notify", side_effect=notified.append):
            rc, out = self._main("--audit-run-bin", runner)
        self.assertEqual(rc, 0)
        self.assertIn("2 critical", out)
        self.assertTrue(any("2 critical" in n for n in notified))


class TestAuditRunBinIndirection(unittest.TestCase):
    """The runner is injectable so that no test can ever start a billed run."""

    def test_env_override_wins_over_the_sibling_lookup(self):
        with mock.patch.dict(os.environ, {"AUDIT_RUN_BIN": "/stub/run.sh"}):
            self.assertEqual(ad.audit_run_bin(), "/stub/run.sh")

    def test_an_empty_override_resolves_empty_rather_than_falling_through(self):
        # A harness that computes an empty path must fail loudly, never fall
        # through to the real script and launch a live, billed agent session.
        with mock.patch.dict(os.environ, {"AUDIT_RUN_BIN": ""}):
            self.assertEqual(ad.audit_run_bin(), "")

    def test_an_empty_override_makes_run_package_refuse(self):
        with mock.patch.dict(os.environ, {"AUDIT_RUN_BIN": ""}):
            result = ad.run_package({"package": "p", "path": "/tmp/p"}, "/tmp/store")
        self.assertIsNone(result["returncode"])
        self.assertIn("AUDIT_RUN_BIN", result["error"])

    def test_the_default_is_the_sibling_audit_run_script(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(ad.audit_run_bin(), str(TOOLS / "audit_run.sh"))


if __name__ == "__main__":
    unittest.main()
