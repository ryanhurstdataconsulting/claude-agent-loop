import contextlib, io, json, os, pathlib, sys, tempfile, unittest
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


SAMPLE_USAGE_HTML = """
<main aria-label="Usage">
  <section aria-label="Session limit">
    <h2>Current session</h2>
    <div role="meter" aria-valuenow="42">42%</div>
    <p>Resets <time datetime="2026-07-17T19:00:00Z">7:00 PM</time></p>
  </section>
  <section aria-label="Weekly limit">
    <h2>Weekly usage</h2>
    <div role="meter" aria-valuenow="68">68%</div>
    <p>Resets <time datetime="2026-07-21T00:00:00Z">Mon 12:00 AM</time></p>
  </section>
</main>
"""

LOGIN_PAGE_HTML = """
<main><h1>Sign in to Claude</h1><button>Continue with Google</button></main>
"""


class TestParseUsageText(unittest.TestCase):
    def test_extracts_both_percentages_and_reset_timestamps(self):
        self.assertEqual(
            up.parse_usage_text(SAMPLE_USAGE_HTML),
            {
                "session_pct": 42,
                "weekly_pct": 68,
                "session_resets_at": "2026-07-17T19:00:00Z",
                "weekly_resets_at": "2026-07-21T00:00:00Z",
            },
        )

    def test_login_page_raises_valueerror(self):
        with self.assertRaises(ValueError):
            up.parse_usage_text(LOGIN_PAGE_HTML)

    def test_out_of_range_percentage_raises(self):
        bad = SAMPLE_USAGE_HTML.replace("42%", "142%")
        with self.assertRaises(ValueError):
            up.parse_usage_text(bad)

    def test_missing_timestamp_raises(self):
        bad = SAMPLE_USAGE_HTML.replace('datetime="2026-07-17T19:00:00Z"', 'datetime=""')
        with self.assertRaises(ValueError):
            up.parse_usage_text(bad)


class TestBuildStatus(unittest.TestCase):
    PARSED = {
        "session_pct": 42, "weekly_pct": 68,
        "session_resets_at": "2026-07-17T19:00:00Z",
        "weekly_resets_at": "2026-07-21T00:00:00Z",
    }

    def test_adds_polled_at_in_iso_utc_z_format(self):
        now = datetime(2026, 7, 17, 14, 32, 0, tzinfo=timezone.utc)
        self.assertEqual(up.build_status(self.PARSED, now=now)["polled_at"],
                         "2026-07-17T14:32:00Z")

    def test_exact_schema_keys_order_and_types(self):
        now = datetime(2026, 7, 17, 14, 32, 0, tzinfo=timezone.utc)
        status = up.build_status(self.PARSED, now=now)
        self.assertEqual(
            list(status.keys()),
            ["polled_at", "session_pct", "weekly_pct",
             "session_resets_at", "weekly_resets_at"],
        )
        self.assertIsInstance(status["polled_at"], str)
        self.assertIsInstance(status["session_pct"], int)
        self.assertIsInstance(status["weekly_pct"], int)
        self.assertIsInstance(status["session_resets_at"], str)
        self.assertIsInstance(status["weekly_resets_at"], str)


class TestAtomicWrite(unittest.TestCase):
    def test_writes_final_file_and_leaves_no_tmp(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "state" / "usage" / "status.json"
            obj = {"polled_at": "2026-07-17T14:32:00Z", "session_pct": 42,
                   "weekly_pct": 68, "session_resets_at": "2026-07-17T19:00:00Z",
                   "weekly_resets_at": "2026-07-21T00:00:00Z"}
            up.atomic_write_json(path, obj)
            self.assertEqual(json.loads(path.read_text()), obj)
            self.assertFalse(pathlib.Path(str(path) + ".tmp").exists())

    def test_uses_tmp_then_rename(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "status.json"
            seen = {}
            real_rename = os.rename

            def spy_rename(src, dst):
                seen["src"], seen["dst"] = str(src), str(dst)
                seen["tmp_existed"] = pathlib.Path(src).exists()
                seen["dest_absent"] = not pathlib.Path(dst).exists()
                return real_rename(src, dst)

            os.rename = spy_rename
            try:
                up.atomic_write_json(path, {"a": 1})
            finally:
                os.rename = real_rename
            self.assertEqual(seen["src"], str(path) + ".tmp")
            self.assertEqual(seen["dst"], str(path))
            self.assertTrue(seen["tmp_existed"])
            self.assertTrue(seen["dest_absent"])


class TestPollOrchestration(unittest.TestCase):
    def _paths(self, d):
        return (pathlib.Path(d) / "state" / "usage" / "status.json",
                pathlib.Path(d) / "logs" / "usage_poll.log")

    def test_successful_poll_writes_cache(self):
        with tempfile.TemporaryDirectory() as d:
            cache_path, log_path = self._paths(d)
            up.poll(cache_path, log_path, storage_state_path="/unused",
                    now=datetime(2026, 7, 17, 14, 32, tzinfo=timezone.utc),
                    fetch=lambda ssp: ("https://claude.ai/settings/usage",
                                       SAMPLE_USAGE_HTML))
            data = json.loads(cache_path.read_text())
            self.assertEqual(data["session_pct"], 42)
            self.assertEqual(data["weekly_pct"], 68)
            self.assertEqual(data["polled_at"], "2026-07-17T14:32:00Z")

    def test_login_redirect_leaves_existing_cache_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            cache_path, log_path = self._paths(d)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text('{"stale": true}')
            up.poll(cache_path, log_path, storage_state_path="/unused",
                    fetch=lambda ssp: ("https://claude.ai/login", "<h1>Sign in</h1>"))
            self.assertEqual(json.loads(cache_path.read_text()), {"stale": True})
            self.assertIn("login", log_path.read_text())

    def test_dom_drift_leaves_cache_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            cache_path, log_path = self._paths(d)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text('{"stale": true}')
            up.poll(cache_path, log_path, storage_state_path="/unused",
                    fetch=lambda ssp: ("https://claude.ai/settings/usage",
                                       "<h1>totally different page</h1>"))
            self.assertEqual(json.loads(cache_path.read_text()), {"stale": True})
            self.assertIn("parse", log_path.read_text().lower())

    def test_fetch_error_leaves_cache_untouched_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            cache_path, log_path = self._paths(d)

            def boom(ssp):
                raise RuntimeError("browser crashed")

            up.poll(cache_path, log_path, storage_state_path="/unused", fetch=boom)
            self.assertFalse(cache_path.exists())
            self.assertIn("browser/fetch error", log_path.read_text())

    def test_cache_write_error_leaves_existing_cache_untouched_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            cache_path, log_path = self._paths(d)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            sentinel = '{"stale": true}'
            cache_path.write_text(sentinel)

            real_rename = os.rename

            def boom_rename(src, dst):
                raise OSError("simulated disk-full error during cache rename")

            os.rename = boom_rename
            try:
                up.poll(cache_path, log_path, storage_state_path="/unused",
                        fetch=lambda ssp: ("https://claude.ai/settings/usage",
                                           SAMPLE_USAGE_HTML))
            finally:
                os.rename = real_rename

            # crux of the test: the pre-existing cache file is byte-for-byte
            # untouched, since atomic_write_json's rename never succeeded.
            self.assertEqual(cache_path.read_text(), sentinel)

            log_lines = log_path.read_text().strip("\n").splitlines()
            self.assertEqual(len(log_lines), 1)
            self.assertIn("poll aborted: could not write cache", log_lines[0])


class TestCli(unittest.TestCase):
    def test_default_mode_is_poll(self):
        self.assertFalse(up.build_arg_parser().parse_args([]).login)

    def test_login_flag_selects_login(self):
        self.assertTrue(up.build_arg_parser().parse_args(["--login"]).login)

    def test_login_and_poll_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            up.build_arg_parser().parse_args(["--login", "--poll"])

    def test_main_dispatches_to_poll_by_default(self):
        called = {}
        orig_poll, orig_login = up.poll, up.login
        up.poll = lambda *a, **k: called.setdefault("poll", True)
        up.login = lambda *a, **k: called.setdefault("login", True)
        try:
            rc = up.main([])
        finally:
            up.poll, up.login = orig_poll, orig_login
        self.assertEqual(rc, 0)
        self.assertTrue(called.get("poll"))
        self.assertNotIn("login", called)

    def test_main_dispatches_to_login_on_flag(self):
        called = {}
        orig_poll, orig_login = up.poll, up.login
        up.poll = lambda *a, **k: called.setdefault("poll", True)
        up.login = lambda *a, **k: (called.setdefault("login", True),
                                    pathlib.Path("/x"))[1]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rc = up.main(["--login"])
        finally:
            up.poll, up.login = orig_poll, orig_login
        self.assertEqual(rc, 0)
        self.assertTrue(called.get("login"))
        self.assertNotIn("poll", called)


class TestMainFailOpen(unittest.TestCase):
    def test_main_returns_zero_when_resolve_paths_raises(self):
        real = up.resolve_paths

        def boom():
            raise RuntimeError("home directory unresolvable")

        up.resolve_paths = boom
        try:
            self.assertEqual(up.main([]), 0)
        finally:
            up.resolve_paths = real


class TestSchemaLock(unittest.TestCase):
    """Locks the exact status.json contract the usage-budget hook (Task 6) reads.
    If this test breaks, the hook's cache read breaks with it."""

    def test_end_to_end_schema_matches_spec_verbatim(self):
        with tempfile.TemporaryDirectory() as d:
            cache_path = pathlib.Path(d) / "state" / "usage" / "status.json"
            log_path = pathlib.Path(d) / "logs" / "usage_poll.log"
            up.poll(cache_path, log_path, storage_state_path="/unused",
                    now=datetime(2026, 7, 17, 14, 32, tzinfo=timezone.utc),
                    fetch=lambda ssp: ("https://claude.ai/settings/usage",
                                       SAMPLE_USAGE_HTML))
            data = json.loads(cache_path.read_text())
            self.assertEqual(
                list(data.keys()),
                ["polled_at", "session_pct", "weekly_pct",
                 "session_resets_at", "weekly_resets_at"])
            self.assertEqual(data, {
                "polled_at": "2026-07-17T14:32:00Z",
                "session_pct": 42,
                "weekly_pct": 68,
                "session_resets_at": "2026-07-17T19:00:00Z",
                "weekly_resets_at": "2026-07-21T00:00:00Z",
            })


class TestLogDiagnosticHygiene(unittest.TestCase):
    def test_log_messages_have_no_double_spaces(self):
        with tempfile.TemporaryDirectory() as d:
            cache_path = pathlib.Path(d) / "state" / "usage" / "status.json"
            log_path = pathlib.Path(d) / "logs" / "usage_poll.log"
            up.poll(cache_path, log_path, storage_state_path="/unused",
                    fetch=lambda ssp: ("https://claude.ai/login?return-to=%2F", ""))
            content = log_path.read_text()
            self.assertIn(
                "poll aborted: claude.ai redirected to login; session expired, "
                "cache left untouched — re-run 'usage_poll.py --login'",
                content)
            self.assertNotIn("  ", content)
            self.assertFalse(cache_path.exists())


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]  # tests->tools->payload->root


class TestLaunchdAndManifest(unittest.TestCase):
    PLIST = REPO_ROOT / "payload" / "launchd" / "com.hdc.claude-agent-loop.usage-poll.plist"
    MANIFEST = REPO_ROOT / "payload" / "MANIFEST"

    def test_plist_exists_and_lints(self):
        self.assertTrue(self.PLIST.exists(), f"missing {self.PLIST}")
        import shutil, subprocess
        if shutil.which("plutil"):  # macOS only; skip the lint on Linux CI
            r = subprocess.run(["plutil", "-lint", str(self.PLIST)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_plist_label_interval_and_poll_mode(self):
        body = self.PLIST.read_text()
        self.assertIn("<string>com.hdc.claude-agent-loop.usage-poll</string>", body)
        self.assertIn("<integer>600</integer>", body)   # USAGE_BUDGET_POLL_SECS
        self.assertIn("--poll", body)
        self.assertIn("usage_poll.py", body)

    def test_manifest_links_tool_and_plist(self):
        lines = self.MANIFEST.read_text().splitlines()
        self.assertIn("link-file tools/usage_poll.py", lines)
        self.assertIn(
            "link-file launchd/com.hdc.claude-agent-loop.usage-poll.plist", lines)


if __name__ == "__main__":
    unittest.main()
