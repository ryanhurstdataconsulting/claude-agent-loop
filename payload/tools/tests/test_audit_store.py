#!/usr/bin/env python3
"""Tests for audit_store — the consolidated repo-security-audit output store.

Hermetic: every case builds its store under ``tempfile.mkdtemp()`` and tears
it down afterward. Nothing here touches the real ``~/.claude`` tree.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import audit_store as st  # noqa: E402  (path set up above)


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
