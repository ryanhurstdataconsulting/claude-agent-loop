"""Tests for git_safety_preflight — the advisory repo/file-sync hazard scanner.

Written TDD-first: this module imports ``git_safety_preflight`` before the
tool exists (RED = ModuleNotFoundError), then drives it GREEN.

Uses real temporary git repos (``git init`` in a tempdir) rather than mocked
subprocess output, per the tool's own testability contract: check functions
accept a path and are exercised against a throwaway repo.
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import git_safety_preflight as gsp


def _run(args, cwd):
    res = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert res.returncode == 0, f"git {args} failed: {res.stderr}"
    return res


def _init_repo(path):
    _run(["init", "-q", "-b", "main"], path)
    _run(["config", "user.email", "test@example.com"], path)
    _run(["config", "user.name", "Test"], path)


def _commit_one_file(path, name="a.txt", content="hello\n"):
    (pathlib.Path(path) / name).write_text(content)
    _run(["add", name], path)
    _run(["commit", "-q", "-m", "init"], path)


class TestCleanRepoWithRemote(unittest.TestCase):
    """A repo that is committed, pushed, and tracking a remote: no warnings."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        root = pathlib.Path(self.td.name)
        self.bare = root / "bare.git"
        self.work = root / "work"
        self.work.mkdir()
        _run(["init", "-q", "--bare", "-b", "main", str(self.bare)], root)
        _init_repo(self.work)
        _commit_one_file(self.work)
        _run(["remote", "add", "origin", str(self.bare)], self.work)
        _run(["push", "-q", "-u", "origin", "main"], self.work)

    def test_no_warnings_on_clean_pushed_repo(self):
        findings = gsp.run_checks(self.work)
        self.assertEqual(findings, [], f"unexpected warnings: {findings}")

    def test_main_exits_zero(self):
        self.assertEqual(gsp.main([str(self.work)]), 0)


class TestNoRemote(unittest.TestCase):
    """A committed repo with no remote at all: flagged as at-risk."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.work = pathlib.Path(self.td.name)
        _init_repo(self.work)
        _commit_one_file(self.work)

    def test_no_remote_warning_present(self):
        findings = gsp.run_checks(self.work)
        checks = {f.check for f in findings}
        self.assertIn("no-remote", checks, findings)

    def test_no_remote_finding_has_remediation(self):
        findings = gsp.run_checks(self.work)
        f = next(f for f in findings if f.check == "no-remote")
        self.assertIn("git remote add", f.message)

    def test_main_still_exits_zero_advisory(self):
        self.assertEqual(gsp.main([str(self.work)]), 0)


class TestDirtyTree(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.work = pathlib.Path(self.td.name)
        _init_repo(self.work)
        _commit_one_file(self.work)

    def test_dirty_tree_flagged(self):
        (self.work / "b.txt").write_text("uncommitted\n")
        findings = gsp.run_checks(self.work)
        checks = {f.check for f in findings}
        self.assertIn("dirty-tree", checks, findings)


class TestNotARepo(unittest.TestCase):
    def test_not_a_repo_flagged_and_does_not_crash(self):
        with tempfile.TemporaryDirectory() as td:
            findings = gsp.run_checks(pathlib.Path(td))
            checks = {f.check for f in findings}
            self.assertIn("not-a-repo", checks, findings)

    def test_main_exits_zero_for_non_repo(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(gsp.main([td]), 0)


class TestICloudSyncPath(unittest.TestCase):
    def test_icloud_path_triggers_warning(self):
        icloud_path = (
            pathlib.Path.home()
            / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
            / "Desktop" / "some-project"
        )
        finding = gsp.check_icloud_sync(icloud_path)
        self.assertIsNotNone(finding)
        self.assertEqual(finding.check, "icloud-sync")

    def test_non_icloud_path_is_clean(self):
        with tempfile.TemporaryDirectory() as td:
            finding = gsp.check_icloud_sync(pathlib.Path(td))
            self.assertIsNone(finding)


class TestVenvSymlink(unittest.TestCase):
    def test_missing_venv_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            finding = gsp.check_venv_symlink(pathlib.Path(td))
            self.assertIsNone(finding)

    def test_broken_symlink_is_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            bin_dir = root / ".venv" / "bin"
            bin_dir.mkdir(parents=True)
            (bin_dir / "python").symlink_to(root / "nonexistent-interpreter")
            finding = gsp.check_venv_symlink(root)
            self.assertIsNotNone(finding)
            self.assertEqual(finding.check, "broken-venv-symlink")

    def test_working_interpreter_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            bin_dir = root / ".venv" / "bin"
            bin_dir.mkdir(parents=True)
            real = root / "real-python"
            real.write_text("#!/bin/sh\n")
            real.chmod(0o755)
            (bin_dir / "python").symlink_to(real)
            finding = gsp.check_venv_symlink(root)
            self.assertIsNone(finding)


if __name__ == "__main__":
    unittest.main()
