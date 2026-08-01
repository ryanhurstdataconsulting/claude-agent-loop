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

    def test_longest_overdue_sorts_first(self):
        # "a" was audited recently at its (moved) head -> not due.
        # "b" is overdue by a lot; give it a real git repo and matching
        # recorded head so it is due purely on interval, not on "unknown".
        pkg_b = pathlib.Path(self.ws) / "b"
        pkg_b.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(pkg_b), capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"],
                        cwd=str(pkg_b), capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"],
                        cwd=str(pkg_b), capture_output=True)
        (pkg_b / "f.txt").write_text("x")
        subprocess.run(["git", "add", "f.txt"], cwd=str(pkg_b), capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"],
                        cwd=str(pkg_b), capture_output=True)
        sha_b = subprocess.run(["git", "-C", str(pkg_b), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        run_dir_b = pathlib.Path(self.tmp) / "audit" / "runs" / "b"
        run_dir_b.mkdir(parents=True)
        (run_dir_b / "2026-01-01.json").write_text(json.dumps({
            "last_audit_date": "2026-01-01T00:00:00Z",
            "last_audited_sha": "some-old-sha-not-" + sha_b,
        }))
        cfg = {"schema": 1, "per_night_cap": 4, "tiers": {
            "weekly": {"interval_days": 7, "packages": ["b"]}}}
        picked = ad.select_due(self.tmp, cfg, self.ws, NOW)
        self.assertEqual(picked[0]["package"], "b")
        self.assertIn("due", picked[0]["reason"].lower())


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


class TestMainCli(unittest.TestCase):
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
            rc = ad.main(["--root", self.tmp, "--workspace", self.ws, "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual({e["package"] for e in payload}, {"a", "b"})

    def test_human_output_is_one_line_per_package(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ad.main(["--root", self.tmp, "--workspace", self.ws])
        self.assertEqual(rc, 0)
        lines = [l for l in buf.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
