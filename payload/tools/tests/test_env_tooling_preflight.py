"""Tests for env_tooling_preflight — the advisory interpreter/toolchain scanner.

Written TDD-first: this module imports ``env_tooling_preflight`` before the
tool exists (RED = ModuleNotFoundError), then drives it GREEN.

Check logic is exercised through injectable resolvers (fake `which` / fake
version output) so no real PATH or interpreter state is required.
"""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import env_tooling_preflight as etp


def _fake_which(present):
    """Build a `which`-shaped resolver: returns a fake path for names in `present`."""
    def resolver(name):
        return f"/usr/local/bin/{name}" if name in present else None
    return resolver


class TestToolPresence(unittest.TestCase):
    def test_present_tool_is_green(self):
        status = etp.check_tool("pandoc", which=_fake_which({"pandoc"}))
        self.assertTrue(status.ok)
        self.assertEqual(status.name, "pandoc")

    def test_absent_tool_is_red_with_fix_hint(self):
        status = etp.check_tool("ffmpeg", which=_fake_which(set()))
        self.assertFalse(status.ok)
        self.assertTrue(status.fix, "expected a non-empty fix hint")

    def test_check_tools_returns_one_status_per_name(self):
        names = ["pandoc", "weasyprint", "ffmpeg"]
        statuses = etp.check_tools(names, which=_fake_which({"pandoc"}))
        self.assertEqual([s.name for s in statuses], names)
        self.assertEqual([s.ok for s in statuses], [True, False, False])

    def test_unknown_tool_gets_generic_fix_hint(self):
        status = etp.check_tool("some-obscure-tool", which=_fake_which(set()))
        self.assertFalse(status.ok)
        self.assertIn("some-obscure-tool", status.fix)


class TestVenvPythonVersion(unittest.TestCase):
    def test_no_venv_present_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(etp.check_venv_python(td))

    def test_version_at_or_above_floor_is_green(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / ".venv" / "bin").mkdir(parents=True)
            (root / ".venv" / "bin" / "python").write_text("#!/bin/sh\n")
            status = etp.check_venv_python(
                td, version_resolver=lambda p: "Python 3.11.4"
            )
            self.assertTrue(status.ok)

    def test_version_below_floor_is_red_with_fix_hint(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / ".venv" / "bin").mkdir(parents=True)
            (root / ".venv" / "bin" / "python").write_text("#!/bin/sh\n")
            status = etp.check_venv_python(
                td, version_resolver=lambda p: "Python 3.9.6"
            )
            self.assertFalse(status.ok)
            self.assertTrue(status.fix)

    def test_unparseable_version_is_red(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / ".venv" / "bin").mkdir(parents=True)
            (root / ".venv" / "bin" / "python").write_text("#!/bin/sh\n")
            status = etp.check_venv_python(
                td, version_resolver=lambda p: "garbage output"
            )
            self.assertFalse(status.ok)


class TestMain(unittest.TestCase):
    def test_main_always_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(etp.main([td]), 0)


if __name__ == "__main__":
    unittest.main()
