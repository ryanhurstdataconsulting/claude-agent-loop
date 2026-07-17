"""Tests for loop_digest — the auto-change digest renderer (P5).

Written TDD-first: imports ``loop_digest`` before it exists (RED). Fixtures are
synthetic. Coverage:
  * every section renders with exact counts from a fixture log + themes + shard;
  * the metrics summary applies last-record-per-(task_id, kind) dedupe;
  * ``.last-digest`` is updated to the run instant;
  * a second run with no new entries takes the "nothing to digest" path;
  * the tool NEVER pushes — asserted by grepping the tool source;
  * the generated digest prose passes the grammar gate (machine-generated text
    is a client-facing deliverable and must be clean).
"""
import io
import json
import pathlib
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import loop_digest as ld  # noqa: E402
import prose_grammar_gate as pg  # noqa: E402

NOW = "2026-07-06T12:00:00Z"
EARLIER = "2026-07-06T10:00:00Z"
MONTH = "2026-07"


class TestLoopDigest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        base = pathlib.Path(self.td.name)
        self.learning = base / "learning"
        self.learning.mkdir()
        self.metrics = base / "metrics"
        self.metrics.mkdir()
        self.fwrepo = base / "fw"
        self.localrepo = base / "loc"
        self.fwb = self.fwrepo.name
        self.locb = self.localrepo.name
        self._git_init(self.fwrepo)
        self._git_init(self.localrepo)

        # AUTO_COMMITS.log: two framework commits, one local, one revert.
        (self.learning / "AUTO_COMMITS.log").write_text("\n".join([
            f"{EARLIER}\t{self.fwb}\tabc1234\tloop: docs one\t-",
            f"{EARLIER}\t{self.fwb}\tdef5678\tloop: docs two\tH4",
            f"{EARLIER}\t{self.locb}\taaa1111\tloop: local one\t-",
            f"{EARLIER}\t{self.fwb}\treva111\tREVERT reva111 of abc1234\t-",
        ]) + "\n", encoding="utf-8")

        # LOOP_THEMES.md: 2 NEW (one is autocommit-blocked), 1 PROMOTED, 1 DISMISSED.
        (self.learning / "LOOP_THEMES.md").write_text(
            "| status | date | project | theme-tag | note | metrics-ref |\n"
            "|---|---|---|---|---|---|\n"
            f"| NEW | 2026-07-06 | {self.fwb} | autocommit-blocked | "
            "gate scrub refused docs three | - |\n"
            "| NEW | 2026-07-06 | proj | slow-intake | intake re-derived | ref |\n"
            "| PROMOTED:slow-thing | 2026-07-01 | proj | slow | note | ref |\n"
            "| DISMISSED:one-off | 2026-06-30 | proj | fluke | note | ref |\n",
            encoding="utf-8")

        # Metrics shard: agent-a appears twice (last wins), plus agent-b.
        shard = self.metrics / (MONTH + ".jsonl")
        recs = [
            {"schema": 1, "kind": "task", "task_id": "agent-a", "ts_end": EARLIER,
             "error_rate": 0.9, "tests": {"passed": 0, "failed": 9},
             "resources_deployed": ["stale"]},
            {"schema": 1, "kind": "task", "task_id": "agent-a", "ts_end": EARLIER,
             "error_rate": 0.1, "tests": {"passed": 5, "failed": 1},
             "resources_deployed": ["resource-loop", "sports-analyst"]},
            {"schema": 1, "kind": "task", "task_id": "agent-b", "ts_end": EARLIER,
             "error_rate": 0.3, "tests": {"passed": 3, "failed": 0},
             "resources_deployed": ["resource-loop"]},
        ]
        shard.write_text("\n".join(json.dumps(r) for r in recs) + "\n",
                         encoding="utf-8")

    def _git_init(self, path):
        import subprocess
        path.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(path))
        (path / "seed").write_text("x")
        subprocess.run(["git", "add", "."], cwd=str(path))
        subprocess.run(["git", "-c", "user.email=t@e.co", "-c", "user.name=t",
                        "commit", "-qm", "init"], cwd=str(path))

    def _argv(self, *extra):
        return list(extra) + [
            "--learning-dir", str(self.learning),
            "--metrics-dir", str(self.metrics),
            "--framework-repo", str(self.fwrepo),
            "--local-root", str(self.localrepo),
            "--now", NOW,
        ]

    def _run(self, *extra):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ld.main(self._argv(*extra))
        return rc, buf.getvalue()

    def _digest_text(self):
        f = self.learning / "digests" / "2026-07-06.md"
        return f.read_text(encoding="utf-8") if f.is_file() else None

    def test_digest_file_written(self):
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("2026-07-06.md", out)
        self.assertIsNotNone(self._digest_text())

    def test_auto_commits_grouped_by_repo(self):
        self._run()
        text = self._digest_text()
        self.assertIn(self.fwb, text)
        self.assertIn(self.locb, text)
        self.assertIn("abc1234", text)
        self.assertIn("def5678", text)
        self.assertIn("aaa1111", text)

    def test_unpushed_note_is_na_without_remote(self):
        self._run()
        self.assertIn("unpushed: n/a", self._digest_text())

    def test_blocked_attempts_section(self):
        self._run()
        text = self._digest_text()
        self.assertIn("Blocked attempts", text)
        self.assertIn("gate scrub refused docs three", text)

    def test_theme_transition_counts(self):
        self._run()
        text = self._digest_text()
        self.assertIn("NEW: 2", text)
        self.assertIn("PROMOTED: 1", text)
        self.assertIn("DISMISSED: 1", text)

    def test_metrics_summary_with_dedupe(self):
        self._run()
        text = self._digest_text()
        self.assertIn("tasks: 2", text)              # agent-a (deduped) + agent-b
        self.assertIn("mean error_rate: 0.2", text)  # (0.1 + 0.3) / 2
        self.assertIn("8 passed", text)              # 5 + 3 (stale 0 dropped)
        self.assertIn("1 failed", text)              # 1 + 0 (stale 9 dropped)
        self.assertIn("resource-loop (2)", text)     # top resource

    def test_last_digest_updated(self):
        self._run()
        marker = (self.learning / ".last-digest").read_text().strip()
        self.assertEqual(marker, NOW)

    def test_push_hint_present(self):
        self._run()
        text = self._digest_text()
        self.assertIn("claude-agent-loop", text)
        self.assertIn("Push now?", text)

    def test_second_run_nothing_to_digest(self):
        self._run()
        rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("nothing to digest", out.lower())

    def test_generated_prose_passes_grammar_gate(self):
        self._run()
        findings = pg.lint_file(str(self.learning / "digests" / "2026-07-06.md"))
        self.assertEqual(findings, [], findings)


class TestNudge(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.learning = pathlib.Path(self.td.name) / "learning"
        self.learning.mkdir()
        self.log = self.learning / "AUTO_COMMITS.log"

    def _write_log(self, n, ts=EARLIER):
        lines = [f"{ts}\tclaude-agent-loop\tsha{i}\tloop: change {i}\t-"
                 for i in range(n)]
        self.log.write_text("\n".join(lines) + ("\n" if lines else ""),
                            encoding="utf-8")

    def _nudge(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ld.main(["--nudge", "--learning-dir", str(self.learning),
                          "--now", NOW])
        return rc, buf.getvalue()

    def test_ten_undigested_fires_nudge(self):
        self._write_log(10)
        rc, out = self._nudge()
        self.assertEqual(rc, 0)
        self.assertIn("Loop digest pending: 10", out)

    def test_no_entries_no_nudge(self):
        self._write_log(0)
        rc, out = self._nudge()
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_few_entries_no_last_digest_fires(self):
        # No .last-digest present + entries → nudge even below 10.
        self._write_log(3)
        rc, out = self._nudge()
        self.assertIn("Loop digest pending: 3", out)

    def test_few_entries_recent_last_digest_no_nudge(self):
        self._write_log(3)
        (self.learning / ".last-digest").write_text("2026-07-06T11:00:00Z")
        # entries are dated EARLIER (10:00) < last-digest (11:00) → 0 undigested.
        rc, out = self._nudge()
        self.assertEqual(out.strip(), "")


class TestUnpushed(unittest.TestCase):
    """BI4: the unpushed count must follow the current branch's upstream, not a
    hardcoded origin/main..main (which is wrong/zero on a feature branch)."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.base = pathlib.Path(self.td.name)

    def _git(self, repo, *args):
        import subprocess
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True)

    def test_unpushed_uses_feature_branch_upstream(self):
        import subprocess
        remote = self.base / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)])
        work = self.base / "work"
        work.mkdir()
        self._git(work, "init", "-q")
        self._git(work, "config", "user.email", "t@e.co")
        self._git(work, "config", "user.name", "t")
        self._git(work, "commit", "--allow-empty", "-qm", "c0")
        # A FEATURE branch (not main) tracking origin/feature.
        self._git(work, "checkout", "-q", "-b", "feature")
        self._git(work, "remote", "add", "origin", str(remote))
        self._git(work, "push", "-q", "-u", "origin", "feature")
        # Two commits ahead of the upstream.
        self._git(work, "commit", "--allow-empty", "-qm", "c1")
        self._git(work, "commit", "--allow-empty", "-qm", "c2")
        # Old code hardcoded origin/main..main → main is absent → None (RED).
        self.assertEqual(ld._unpushed(work), "2")

    def test_unpushed_none_without_upstream(self):
        import subprocess
        solo = self.base / "solo"
        solo.mkdir()
        self._git(solo, "init", "-q")
        self._git(solo, "config", "user.email", "t@e.co")
        self._git(solo, "config", "user.name", "t")
        self._git(solo, "commit", "--allow-empty", "-qm", "c0")
        # No upstream configured → n/a signal (None).
        self.assertIsNone(ld._unpushed(solo))


class TestUnpushedPrintGate(unittest.TestCase):
    """main() must only print the "framework commits are unpushed" console
    hint when _unpushed(framework_repo) is genuinely non-zero — not
    unconditionally on every run."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.base = pathlib.Path(self.td.name)
        self.learning = self.base / "learning"
        self.learning.mkdir()
        self.metrics = self.base / "metrics"
        self.metrics.mkdir()

    def _git(self, repo, *args):
        import subprocess
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True)

    def _init_repo(self, name):
        repo = self.base / name
        repo.mkdir()
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@e.co")
        self._git(repo, "config", "user.name", "t")
        self._git(repo, "commit", "--allow-empty", "-qm", "c0")
        return repo

    def _write_log(self, fwb):
        (self.learning / "AUTO_COMMITS.log").write_text(
            f"{EARLIER}\t{fwb}\tabc1234\tloop: docs one\t-\n", encoding="utf-8")

    def _run(self, fwrepo):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = ld.main([
                "--learning-dir", str(self.learning),
                "--metrics-dir", str(self.metrics),
                "--framework-repo", str(fwrepo),
                "--local-root", str(self.base / "loc-unused"),
                "--now", NOW,
            ])
        return rc, buf.getvalue()

    def test_no_upstream_configured_no_print(self):
        fwrepo = self._init_repo("fw_no_upstream")
        self._write_log(fwrepo.name)
        rc, out = self._run(fwrepo)
        self.assertEqual(rc, 0)
        self.assertNotIn("framework commits are unpushed", out)

    def test_upstream_fully_pushed_no_print(self):
        import subprocess
        remote = self.base / "remote_pushed.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)])
        fwrepo = self._init_repo("fw_pushed")
        self._git(fwrepo, "remote", "add", "origin", str(remote))
        self._git(fwrepo, "push", "-q", "-u", "origin", "HEAD:main")
        self.assertEqual(ld._unpushed(fwrepo), "0")
        self._write_log(fwrepo.name)
        rc, out = self._run(fwrepo)
        self.assertEqual(rc, 0)
        self.assertNotIn("framework commits are unpushed", out)

    def test_upstream_with_unpushed_commits_prints(self):
        import subprocess
        remote = self.base / "remote_ahead.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)])
        fwrepo = self._init_repo("fw_ahead")
        self._git(fwrepo, "remote", "add", "origin", str(remote))
        self._git(fwrepo, "push", "-q", "-u", "origin", "HEAD:main")
        self._git(fwrepo, "commit", "--allow-empty", "-qm", "c1")
        self.assertEqual(ld._unpushed(fwrepo), "1")
        self._write_log(fwrepo.name)
        rc, out = self._run(fwrepo)
        self.assertEqual(rc, 0)
        self.assertIn("framework commits are unpushed", out)


class TestNeverPushes(unittest.TestCase):
    """The tool may DISPLAY a manual push command but must never EXECUTE one."""

    def test_source_has_no_push_execution(self):
        src = pathlib.Path(ld.__file__).read_text(encoding="utf-8")
        # The execution phrase "git push" never appears (the manual hint is
        # rendered as "git -C <repo> push" — never the bare adjacent form).
        self.assertNotIn("git push", src)
        # No exec/subprocess statement references push in any way.
        exec_tokens = ("subprocess", "os.system", "Popen", "check_call",
                       "check_output", ".run(")
        for line in src.splitlines():
            if any(tok in line for tok in exec_tokens):
                self.assertNotIn("push", line, line)
        # The only subprocess this tool ever runs is a read-only rev-list.
        self.assertIn("rev-list", src)


if __name__ == "__main__":
    unittest.main()
