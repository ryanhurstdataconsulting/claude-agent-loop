import pathlib, subprocess, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import worktree_exec as we
import plan_task
import bb_common as bb
import bb_read
from score_task import step_task_id


def _git(args, cwd):
    out = subprocess.run(["git"] + [str(a) for a in args], cwd=str(cwd),
                          capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


class WorktreeFixture(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = pathlib.Path(td.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        _git(["init", "-q", "-b", "main"], self.repo)
        _git(["config", "user.email", "test@example.com"], self.repo)
        _git(["config", "user.name", "Test"], self.repo)
        (self.repo / "README.md").write_text("hello\n")
        _git(["add", "README.md"], self.repo)
        _git(["commit", "-q", "-m", "init"], self.repo)

        self.state_dir = self.root / "plans"
        self.db = str(self.root / "blackboard.db")
        self.worktrees_dir = self.root / "worktrees"
        self.plan = {
            "schema": 2, "task_id": "wo-20260813-test-abc123", "goal": "g",
            "supervisor_reasoning": "", "steps": [
                {"id": "S1", "agent": "generalist", "depends_on": [],
                 "budget_tokens": None, "worktree": True, "brief": "b",
                 "status": "pending", "return": None, "skills": [], "model": "sonnet"},
                {"id": "S2", "agent": "generalist", "depends_on": [],
                 "budget_tokens": None, "worktree": False, "brief": "b",
                 "status": "pending", "return": None, "skills": [], "model": "sonnet"},
            ],
            "termination": {"success_when": "", "max_steps": 8},
            "created": "2026-08-13T00:00:00Z", "project": "p", "git_branch": "main",
            "source": "test",
        }
        plan_task.save(str(self.state_dir), self.plan)


class TestCreate(WorktreeFixture):
    def test_create_makes_worktree_and_records_checkpoint(self):
        wt_path = we.create(str(self.state_dir), self.db, "wo-20260813-test-abc123", "S1",
                             str(self.repo), worktrees_dir=str(self.worktrees_dir))
        self.assertTrue(pathlib.Path(wt_path).is_dir())
        self.assertTrue((pathlib.Path(wt_path) / "README.md").is_file())
        conn = bb.connect(self.db)
        self.addCleanup(conn.close)
        step = self.plan["steps"][0]
        join_key = step_task_id(self.plan, step)
        rows = bb_read.fetch(conn, "workflow_state", task_id=join_key)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["payload"]["checkpoint"], "worktree-created")
        self.assertEqual(rows[0]["payload"]["parent_branch"], "main")

    def test_create_refuses_step_not_marked_worktree(self):
        with self.assertRaises(we.WorktreeError):
            we.create(str(self.state_dir), self.db, "wo-20260813-test-abc123", "S2",
                       str(self.repo), worktrees_dir=str(self.worktrees_dir))


class TestMerge(WorktreeFixture):
    def _create_and_commit(self, step_id="S1"):
        wt_path = we.create(str(self.state_dir), self.db, "wo-20260813-test-abc123", step_id,
                             str(self.repo), worktrees_dir=str(self.worktrees_dir))
        (pathlib.Path(wt_path) / "new.txt").write_text("work done\n")
        _git(["add", "new.txt"], wt_path)
        _git(["commit", "-q", "-m", "do the step"], wt_path)
        return wt_path

    def test_merge_refuses_without_ok_true_return(self):
        self._create_and_commit()
        with self.assertRaises(we.WorktreeError):
            we.merge(str(self.state_dir), self.db, "wo-20260813-test-abc123", "S1")

    def test_merge_succeeds_after_ok_true_return_and_removes_worktree(self):
        wt_path = self._create_and_commit()
        self.plan["steps"][0]["return"] = {"ok": True}
        plan_task.save(str(self.state_dir), self.plan)

        we.merge(str(self.state_dir), self.db, "wo-20260813-test-abc123", "S1")

        self.assertFalse(pathlib.Path(wt_path).exists())
        log = _git(["log", "main"], self.repo)
        self.assertIn("do the step", log)
        self.assertTrue((self.repo / "new.txt").is_file())

    def test_force_merges_despite_missing_ok_true(self):
        self._create_and_commit()
        we.merge(str(self.state_dir), self.db, "wo-20260813-test-abc123", "S1", force=True)
        self.assertTrue((self.repo / "new.txt").is_file())

    def test_merge_conflict_aborts_and_preserves_worktree(self):
        wt_path = self._create_and_commit()
        (self.repo / "new.txt").write_text("conflicting content\n")
        _git(["add", "new.txt"], self.repo)
        _git(["commit", "-q", "-m", "conflicting change on main"], self.repo)
        self.plan["steps"][0]["return"] = {"ok": True}
        plan_task.save(str(self.state_dir), self.plan)

        with self.assertRaises(we.WorktreeError):
            we.merge(str(self.state_dir), self.db, "wo-20260813-test-abc123", "S1")
        self.assertTrue(pathlib.Path(wt_path).is_dir())


if __name__ == "__main__":
    unittest.main()
