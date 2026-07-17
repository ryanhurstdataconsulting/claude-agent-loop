import json, os, pathlib, sys, tempfile, unittest
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import usage_poll as up


class TestPathResolution(unittest.TestCase):
    def test_cache_and_log_paths_follow_metrics_dir(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["METRICS_DIR"] = d
            try:
                cache_path, log_path = up.resolve_paths()
            finally:
                del os.environ["METRICS_DIR"]
            self.assertEqual(cache_path,
                             pathlib.Path(d) / "state" / "usage" / "status.json")
            self.assertEqual(log_path,
                             pathlib.Path(d) / "logs" / "usage_poll.log")

    def test_storage_state_path_is_gitignored_home_file(self):
        self.assertEqual(
            up.STORAGE_STATE_PATH,
            pathlib.Path.home() / ".claude-agent-loop" / "usage-session.json",
        )


class TestLoginBootstrap(unittest.TestCase):
    def test_login_persists_storage_state_to_gitignored_path(self):
        with tempfile.TemporaryDirectory() as d:
            target = pathlib.Path(d) / ".claude-agent-loop" / "usage-session.json"
            saved = {}

            def fake_launcher(url, storage_state_path, prompt):
                # emulate Playwright writing the storageState file, then the
                # interactive "press Enter when logged in" prompt.
                pathlib.Path(storage_state_path).write_text('{"cookies": []}')
                saved["url"] = url
                saved["path"] = storage_state_path
                prompt("go")

            prompts = []
            returned = up.login(storage_state_path=target,
                                launcher=fake_launcher,
                                prompt=lambda msg: prompts.append(msg))

            self.assertEqual(saved["url"], up.USAGE_URL)
            self.assertEqual(saved["path"], str(target))
            self.assertTrue(target.exists())
            self.assertEqual(returned, target)
            # secrets-handling convention: parent dir locked to 0700.
            self.assertEqual(oct(target.parent.stat().st_mode & 0o777), "0o700")
            self.assertEqual(len(prompts), 1)

    def test_log_line_appends_timestamped_line(self):
        with tempfile.TemporaryDirectory() as d:
            log_path = pathlib.Path(d) / "logs" / "usage_poll.log"
            up.log_line(log_path, "hello world")
            body = log_path.read_text()
            self.assertTrue(body.endswith("hello world\n"))
            self.assertRegex(body, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z ")


if __name__ == "__main__":
    unittest.main()
