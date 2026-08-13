#!/usr/bin/env python3
"""Tests for audit_store — the consolidated repo-security-audit output store.

Hermetic: every case builds its store under ``tempfile.mkdtemp()`` and tears
it down afterward. Nothing here touches the real ``~/.claude`` tree.
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS / "dispatch"))
import store as st  # noqa: E402  (path set up above)


class TestStoreRoot(unittest.TestCase):
    def test_returns_the_default_metrics_path_as_a_string(self):
        root = st.store_root()
        self.assertIsInstance(root, str)
        self.assertTrue(root.endswith("/.claude/metrics"))


class TestEnsureStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_creates_the_layout(self):
        st.ensure_store(self.tmp)
        for sub in ("audit/runs", "audit/findings", "audit/digests"):
            self.assertTrue((pathlib.Path(self.tmp) / sub).is_dir(), sub)

    def test_initialises_a_git_repo(self):
        st.ensure_store(self.tmp)
        self.assertTrue((pathlib.Path(self.tmp) / ".git").exists())

    def test_is_idempotent(self):
        st.ensure_store(self.tmp)
        st.ensure_store(self.tmp)  # must not raise
        self.assertTrue((pathlib.Path(self.tmp) / ".git").exists())

    def test_returns_a_status_dict(self):
        status = st.ensure_store(self.tmp)
        self.assertIsInstance(status, dict)

    def test_writes_a_gitignore(self):
        st.ensure_store(self.tmp)
        gi = pathlib.Path(self.tmp) / ".gitignore"
        self.assertTrue(gi.is_file())

    def test_creates_quarantine_and_logs_directories(self):
        st.ensure_store(self.tmp)
        for sub in ("audit/quarantine", "audit/logs"):
            self.assertTrue((pathlib.Path(self.tmp) / sub).is_dir(), sub)


class TestGitignoreScope(unittest.TestCase):
    """The store root IS the metrics tree, so the ignore file must be narrow.

    An empty ``.gitignore`` (what earlier versions wrote) leaves the resource
    loop's monthly shards, budget checkpoints, and every other sibling of
    ``audit/`` untracked-but-not-ignored — one ``git add -A`` run in that
    directory by a human or an agent sweeps the whole ~2.5 MB tree into a
    commit. These cases pin the two halves of the scope: siblings out,
    ``audit/`` in.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        st.ensure_store(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ignored(self, relpath):
        target = pathlib.Path(self.tmp) / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x")
        result = subprocess.run(
            ["git", "-C", self.tmp, "check-ignore", "-q", str(target)],
            capture_output=True, text=True,
        )
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.returncode == 0

    def test_sibling_metrics_shard_is_ignored(self):
        self.assertTrue(self._ignored("2026-07.jsonl"))

    def test_sibling_state_tree_is_ignored(self):
        self.assertTrue(self._ignored("state/budget/checkpoints/session.md"))

    def test_audit_run_logs_are_tracked(self):
        self.assertFalse(self._ignored("audit/runs/pkg/2026-07-31.json"))

    def test_audit_digests_are_tracked(self):
        self.assertFalse(self._ignored("audit/digests/2026-07-31.md"))

    def test_audit_quarantine_is_tracked(self):
        self.assertFalse(
            self._ignored("audit/quarantine/nested/pkg/2026-07-31-SECURITY_AUDIT.md"))

    def test_job_logs_are_not_tracked(self):
        self.assertTrue(self._ignored("audit/logs/repo-audit.out.log"))

    def test_an_empty_gitignore_from_an_older_store_is_repaired(self):
        gi = pathlib.Path(self.tmp) / ".gitignore"
        gi.write_text("")
        st.ensure_store(self.tmp)
        self.assertIn("!/audit/", gi.read_text())


class TestCommitPaths(unittest.TestCase):
    """The store's git history has to be real, not just initialised."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        st.ensure_store(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, relpath):
        target = pathlib.Path(self.tmp) / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n")
        return target

    def _tracked(self):
        out = subprocess.run(["git", "-C", self.tmp, "ls-files"],
                             capture_output=True, text=True).stdout
        return set(out.split())

    def test_commits_an_artifact_and_returns_a_sha(self):
        self._write("audit/runs/pkg/2026-07-31.json")
        sha = st.commit_paths(self.tmp, ["audit/runs/pkg/2026-07-31.json"], "msg")
        self.assertTrue(sha)
        self.assertIn("audit/runs/pkg/2026-07-31.json", self._tracked())

    def test_accepts_absolute_paths_inside_the_store(self):
        target = self._write("audit/digests/2026-07-31.md")
        self.assertTrue(st.commit_paths(self.tmp, [target], "msg"))
        self.assertIn("audit/digests/2026-07-31.md", self._tracked())

    def test_the_gitignore_is_committed_by_ensure_store(self):
        self.assertIn(".gitignore", self._tracked())

    def test_the_commit_cli_stages_an_artifact(self):
        target = self._write("audit/runs/pkg/2026-07-31.json")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = st.main(["--root", self.tmp, "--message", "audit(store): via cli",
                          "commit", str(target)])
        self.assertEqual(rc, 0)
        self.assertTrue(buf.getvalue().strip())  # the new commit's sha
        self.assertIn("audit/runs/pkg/2026-07-31.json", self._tracked())

    def test_a_path_outside_the_store_is_never_staged(self):
        outside = pathlib.Path(tempfile.mkdtemp()) / "secret.txt"
        outside.write_text("nope")
        self.addCleanup(shutil.rmtree, str(outside.parent), ignore_errors=True)
        self.assertIsNone(st.commit_paths(self.tmp, [outside], "msg"))
        # Only the ignore file ensure_store commits — nothing from outside.
        self.assertEqual(self._tracked(), {".gitignore"})

    def test_a_missing_path_is_skipped_rather_than_raising(self):
        self.assertIsNone(
            st.commit_paths(self.tmp, ["audit/runs/pkg/nope.json"], "msg"))

    def test_nothing_to_commit_returns_none(self):
        self._write("audit/runs/pkg/2026-07-31.json")
        st.commit_paths(self.tmp, ["audit/runs/pkg/2026-07-31.json"], "msg")
        self.assertIsNone(
            st.commit_paths(self.tmp, ["audit/runs/pkg/2026-07-31.json"], "msg"))

    def test_a_store_with_no_repo_is_not_an_error(self):
        plain = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, plain, ignore_errors=True)
        (pathlib.Path(plain) / "f.json").write_text("{}")
        self.assertIsNone(st.commit_paths(plain, ["f.json"], "msg"))

    def test_the_store_never_gains_a_remote(self):
        self._write("audit/runs/pkg/2026-07-31.json")
        st.commit_paths(self.tmp, ["audit/runs/pkg/2026-07-31.json"], "msg")
        st.assert_no_remote(self.tmp)  # must not raise


class TestNoRemoteInvariant(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        st.ensure_store(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clean_store_passes(self):
        st.assert_no_remote(self.tmp)  # must not raise

    def test_a_remote_is_refused(self):
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.com/x.git"],
            cwd=self.tmp,
            capture_output=True,
        )
        with self.assertRaises(st.StoreUnsafe):
            st.assert_no_remote(self.tmp)

    def test_refusal_names_the_reason(self):
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.com/x.git"],
            cwd=self.tmp,
            capture_output=True,
        )
        try:
            st.assert_no_remote(self.tmp)
        except st.StoreUnsafe as exc:
            self.assertIn("remote", str(exc).lower())
        else:
            self.fail("expected StoreUnsafe")

    def test_unverifiable_remote_check_fails_closed(self):
        """A store WITH a remote whose `git remote` call cannot even run must

        still be refused. Corrupting .git/config (rather than chmod 000,
        which behaves differently when tests run as root) makes `git remote`
        exit non-zero with empty stdout — the exact condition under which
        the old implementation read stdout as "no remotes" and passed. This
        regression test pins the fail-closed behavior: inability to verify
        the no-remote invariant must never be read as the invariant holding.
        """
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.com/x.git"],
            cwd=self.tmp,
            capture_output=True,
        )
        git_config = pathlib.Path(self.tmp) / ".git" / "config"
        git_config.write_text("[garbage\nnot valid ini")
        with self.assertRaises(st.StoreUnsafe):
            st.assert_no_remote(self.tmp)


class TestNestedRepoGuard(unittest.TestCase):
    """The store must never be tracked by an enclosing repo as a gitlink/submodule."""

    def setUp(self):
        self.parent = tempfile.mkdtemp()
        self.tmp = os.path.join(self.parent, "store")
        os.makedirs(self.tmp)
        st.ensure_store(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.parent, ignore_errors=True)

    def test_parent_not_a_git_repo_passes(self):
        st.assert_no_remote(self.tmp)  # must not raise — parent has no .git

    def test_parent_repo_that_does_not_ignore_the_store_is_refused(self):
        subprocess.run(["git", "init", "-q"], cwd=self.parent, capture_output=True)
        with self.assertRaises(st.StoreUnsafe):
            st.assert_no_remote(self.tmp)

    def test_parent_repo_that_ignores_the_store_passes(self):
        subprocess.run(["git", "init", "-q"], cwd=self.parent, capture_output=True)
        (pathlib.Path(self.parent) / ".gitignore").write_text("store/\n")
        st.assert_no_remote(self.tmp)  # must not raise


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        st.ensure_store(self.tmp)
        self.cfg = pathlib.Path(self.tmp) / "audit" / "config.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_loads_tiers(self):
        self.cfg.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "per_night_cap": 3,
                    "tiers": {"weekly": {"interval_days": 7, "packages": ["a"]}},
                }
            )
        )
        cfg = st.load_config(self.tmp)
        self.assertEqual(cfg["tiers"]["weekly"]["interval_days"], 7)

    def test_missing_config_raises(self):
        with self.assertRaises(st.ConfigError):
            st.load_config(self.tmp)

    def test_malformed_config_raises(self):
        self.cfg.write_text("{not json")
        with self.assertRaises(st.ConfigError):
            st.load_config(self.tmp)

    def test_unknown_schema_raises(self):
        self.cfg.write_text(json.dumps({"schema": 99, "tiers": {}}))
        with self.assertRaises(st.ConfigError):
            st.load_config(self.tmp)

    def test_a_package_in_two_tiers_raises(self):
        self.cfg.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "per_night_cap": 3,
                    "tiers": {
                        "weekly": {"interval_days": 7, "packages": ["a"]},
                        "monthly": {"interval_days": 30, "packages": ["a"]},
                    },
                }
            )
        )
        with self.assertRaises(st.ConfigError):
            st.load_config(self.tmp)


if __name__ == "__main__":
    unittest.main()
