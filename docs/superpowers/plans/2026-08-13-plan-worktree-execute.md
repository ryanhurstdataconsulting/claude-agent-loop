# Worktree EXECUTE Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Let a plan step (Phase 1 schema) marked `"worktree": true` run in
an isolated `git worktree` at `~/.claude/worktrees/<task_id>/<step_id>/`,
merging back onto its parent branch only after the step's own recorded
return says `ok: true`.

**Architecture:** One new tool, `worktree_exec.py`, with two operations —
`--create` (before EXECUTE dispatch) and `--merge` (after SCORE). It reuses
`plan_task.load()`/`plan_task.save()` (Phase 1) to read the step's
`worktree` flag and `return.ok`, `score_task.step_task_id()` (Phase 1) for
the same join key the rest of the system already uses, and the blackboard's
`workflow_state` table (Phase 3) to remember which parent branch a worktree
came from — the one piece of state `--merge` needs that isn't already on the
plan file, and a genuine fit for what Phase 3 calls "checkpoints for
long-running plans, resumable across sessions."

**Tech Stack:** Python 3 stdlib only (`subprocess` for git), plus this
repo's own `plan_task`, `score_task`, and `bb_common`/`bb_read` modules
(same-dir cross-tool import, the established pattern —
`route_role.py` already imports `parse_frontmatter` from `lint_roles.py`
this way).

**Spec:** `docs/superpowers/specs/2026-08-06-agent-loop-v2-design.md`
(Phase 4 — "Worktree EXECUTE support")

## Grounding correction (read before Task 1)

The spec's Phase 4 sentence *"Merge-back goes through the normal
loop_autocommit.sh path, so gates 0–5 fire once, on the merge commit"* does
not fit the actual tool. `payload/tools/loop_autocommit.sh` routes every
path to exactly one of two repos it knows about — `FRAMEWORK_REPO` (this
`claude-agent-loop` checkout) or `$HOME/.claude` — and **explicitly refuses**
anything else (line 167: `"path is under neither the framework repo nor
~/.claude: $abs"`, exit 4). It exists for the LEARN loop's own
self-modification of the agent framework's config, with a two-lane
GENERIC-only commit protocol built for exactly that purpose (see its own
header comment: "THE only sanctioned auto-write path for the loop (P5)").

A plan step's worktree, by contrast, can be — usually will be — in an
arbitrary project repo (`plan_task.py`'s own `--new`/`--from-plan` can be run
from any project directory; the plan's `project` field is just
`re.sub(r"[^A-Za-z0-9]+", "-", os.getcwd())` at creation time, a one-way
slug of whatever repo the task happened to be created in). Routing that
merge through `loop_autocommit.sh` would hit its exit-4 refusal for every
project except this one and `~/.claude` itself.

This plan does the only thing that actually generalizes: `--merge` runs a
plain `git merge --no-ff` in the step's own `--repo`, subject to that
project's own normal git hygiene — not the autonomous LEARN loop's
specialized gates, which are a different mechanism solving a different
problem (self-modification safety for one specific pair of repos, not
correctness of an arbitrary project's merge). The spec's actual intent —
"parent branch untouched until SCORE passes" — is honored directly: `--merge`
refuses (exit 2) unless the plan step's own `return.ok` is `true`, `--force`
overrides that check but never a real merge conflict, which always aborts
and preserves the worktree for manual resolution regardless of any flag.

## Global Constraints

- `worktree_exec.py` never invokes `loop_autocommit.sh` — see Grounding
  above.
- `--repo` is always an explicit CLI argument, never derived from the plan's
  `project` field — that field is a lossy one-way slug (non-alphanumeric
  characters collapsed to `-`), not a reversible path.
- Worktrees live at `~/.claude/worktrees/<task_id>/<step_id>/` by default
  (`default_worktrees_dir()`), exactly as the spec states — created via
  `git worktree add --detach`. `create()`/`--create` take an explicit
  `worktrees_dir`/`--worktrees-dir` override for the same reason every other
  tool in this plan set takes one: tests must never touch the real
  `~/.claude/worktrees/` (an early draft of this plan's own tests did,
  leaking a real directory before this override was added — fixed before
  landing, noted here so it isn't reintroduced).
- A step with `"worktree": false` (or missing) is refused by `--create`
  (exit 2) — opt-in per step, never a silent default.
- New tool needs one `payload/registry/REGISTRY.md` row and one
  `payload/registry/guides/<name>.md` (`lint_registry.py`, Phase 2) plus one
  `payload/MANIFEST` line.

---

### Task 1: `worktree_exec.py` — create and merge

**Files:**
- Create: `payload/tools/worktree_exec.py`
- Test: `payload/tools/tests/test_worktree_exec.py`

**Interfaces:**
- Consumes: `plan_task.load(base_dir, task_id)`, `plan_task.save(base_dir,
  plan)`, `plan_task.WorkOrderError`, `plan_task._default_state_dir()`
  (Phase 1); `score_task.step_task_id(plan, step)` (Phase 1); `bb_common.{
  connect, default_db_path, insert_stamped}`, `bb_read.fetch` (Phase 3).
- Produces:
  - `class WorktreeError(Exception)`
  - `worktree_path(task_id, step_id) -> pathlib.Path`
  - `create(state_dir, db_path, task_id, step_id, repo) -> pathlib.Path` —
    raises `WorktreeError` if the step isn't `"worktree": true`.
  - `merge(state_dir, db_path, task_id, step_id, force=False) -> str` (the
    merged commit sha) — raises `WorktreeError` if no `--create` checkpoint
    exists, the step's `return.ok` isn't `true` and `force` is falsy, or a
    real merge conflict occurs (conflict always aborts and preserves the
    worktree, `force` or not).
  - `main(argv=None) -> int`

- [ ] **Step 1: Write the failing tests**

Create `payload/tools/tests/test_worktree_exec.py`:

```python
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
```

- [ ] **Step 2: Run the suite and confirm it fails**

Run: `python3 -m pytest payload/tools/tests/test_worktree_exec.py -v`
Expected: `ModuleNotFoundError: No module named 'worktree_exec'`.

- [ ] **Step 3: Write `payload/tools/worktree_exec.py`**

```python
#!/usr/bin/env python3
"""Create and merge back per-step git worktrees for EXECUTE (agent-loop-v2
design spec, Phase 4). Only steps whose plan schema marks "worktree": true
(Phase 1) get one — opt-in per step, not a universal default.

Usage:
  python3 worktree_exec.py --create --task-id ID --step ID --repo PATH [--state-dir DIR] [--db PATH]
  python3 worktree_exec.py --merge  --task-id ID --step ID [--force] [--state-dir DIR] [--db PATH]

--create creates ~/.claude/worktrees/<task_id>/<step_id>/ via
`git worktree add --detach`, off --repo's currently checked-out branch, and
records that parent branch on the blackboard (workflow_state) so a later
--merge call — possibly in a different session — can find it again.

--merge merges the worktree's HEAD back onto that recorded parent branch and
removes the worktree. It refuses (exit 2) unless the plan step's own
`return.ok` is true — "parent branch untouched until SCORE passes," per the
spec — pass --force to override that check. A real merge conflict always
aborts and preserves the worktree, `--force` or not.

This is NOT loop_autocommit.sh: that tool commits only to the framework repo
or ~/.claude (it explicitly refuses any third repo) and exists for the LEARN
loop's own self-modification, not for a plan step's work in an arbitrary
project repo. A worktree step's merge-back is a normal git merge in ITS OWN
project, subject to that project's own review/commit norms.
"""
import argparse
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bb_common as bb  # noqa: E402
import bb_read  # noqa: E402
import plan_task  # noqa: E402
from score_task import step_task_id  # noqa: E402

PHASE_CREATE = "EXECUTE"
PHASE_MERGE = "MERGE"


class WorktreeError(Exception):
    pass


def _git(args, cwd):
    out = subprocess.run(["git"] + [str(a) for a in args], cwd=str(cwd),
                          capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise WorktreeError("git %s failed in %s: %s"
                             % (" ".join(str(a) for a in args), cwd, out.stderr.strip()))
    return out.stdout.strip()


def _find_step(plan, step_id):
    for s in plan["steps"]:
        if s["id"] == step_id:
            return s
    raise WorktreeError("no step %r on plan %r" % (step_id, plan["task_id"]))


def default_worktrees_dir():
    return pathlib.Path.home() / ".claude" / "worktrees"


def worktree_path(task_id, step_id, worktrees_dir=None):
    base = pathlib.Path(worktrees_dir) if worktrees_dir else default_worktrees_dir()
    return base / task_id / step_id


def create(state_dir, db_path, task_id, step_id, repo, worktrees_dir=None):
    plan = plan_task.load(state_dir, task_id)
    step = _find_step(plan, step_id)
    if not step.get("worktree"):
        raise WorktreeError(
            "step %r is not marked \"worktree\": true on plan %r" % (step_id, task_id))
    parent_branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo)
    if parent_branch == "HEAD":
        raise WorktreeError(
            "repo %s has a detached HEAD — cannot determine a parent branch "
            "to merge back onto" % repo)
    wt_path = worktree_path(task_id, step_id, worktrees_dir=worktrees_dir)
    wt_path.parent.mkdir(parents=True, exist_ok=True)
    _git(["worktree", "add", "--detach", str(wt_path)], repo)
    conn = bb.connect(db_path)
    try:
        bb.insert_stamped(conn, "workflow_state", step_task_id(plan, step), PHASE_CREATE, None, {
            "checkpoint": "worktree-created",
            "repo": str(pathlib.Path(repo).resolve()),
            "parent_branch": parent_branch,
            "worktree_path": str(wt_path),
        })
    finally:
        conn.close()
    return wt_path


def _latest_checkpoint(db_path, join_key):
    conn = bb.connect(db_path)
    try:
        rows = bb_read.fetch(conn, "workflow_state", task_id=join_key)
    finally:
        conn.close()
    created = [r for r in rows if r["payload"].get("checkpoint") == "worktree-created"]
    if not created:
        raise WorktreeError(
            "no worktree-created checkpoint on the blackboard for %r — "
            "was --create run?" % join_key)
    return created[-1]["payload"]


def merge(state_dir, db_path, task_id, step_id, force=False):
    plan = plan_task.load(state_dir, task_id)
    step = _find_step(plan, step_id)
    join_key = step_task_id(plan, step)
    checkpoint = _latest_checkpoint(db_path, join_key)
    repo = checkpoint["repo"]
    parent_branch = checkpoint["parent_branch"]
    wt_path = pathlib.Path(checkpoint["worktree_path"])

    ret = step.get("return") or {}
    if not force and ret.get("ok") is not True:
        raise WorktreeError(
            "step %r has not returned ok:true (parent branch untouched until "
            "SCORE passes) — pass --force to merge anyway" % step_id)
    if not wt_path.is_dir():
        raise WorktreeError("worktree path %s no longer exists" % wt_path)

    wt_head = _git(["rev-parse", "HEAD"], str(wt_path))
    _git(["checkout", parent_branch], repo)
    try:
        _git(["merge", "--no-ff", "-m",
              "merge: worktree step %s (%s)" % (join_key, wt_head[:8]), wt_head], repo)
    except WorktreeError:
        _git(["merge", "--abort"], repo)
        raise WorktreeError(
            "merge conflict for step %r — parent branch left unmerged, "
            "worktree preserved at %s for manual resolution" % (step_id, wt_path))

    _git(["worktree", "remove", str(wt_path)], repo)
    conn = bb.connect(db_path)
    try:
        bb.insert_stamped(conn, "workflow_state", join_key, PHASE_MERGE, None,
                           {"checkpoint": "worktree-merged", "repo": repo, "merged_sha": wt_head})
    finally:
        conn.close()
    return wt_head


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create", action="store_true")
    mode.add_argument("--merge", action="store_true", dest="do_merge")
    p.add_argument("--task-id", required=True)
    p.add_argument("--step", required=True, dest="step_id")
    p.add_argument("--repo", help="required with --create")
    p.add_argument("--force", action="store_true")
    p.add_argument("--state-dir", default=plan_task._default_state_dir())
    p.add_argument("--db", default=str(bb.default_db_path()))
    p.add_argument("--worktrees-dir", default=str(default_worktrees_dir()))
    a = p.parse_args(argv)

    try:
        if a.create:
            if not a.repo:
                print("error: --create requires --repo", file=sys.stderr)
                return 2
            wt_path = create(a.state_dir, a.db, a.task_id, a.step_id, a.repo,
                              worktrees_dir=a.worktrees_dir)
            print("worktree created: %s" % wt_path)
        else:
            merged_sha = merge(a.state_dir, a.db, a.task_id, a.step_id, force=a.force)
            print("merged %s into parent branch" % merged_sha[:8])
    except (WorktreeError, plan_task.WorkOrderError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the suite and confirm it passes**

Run: `python3 -m pytest payload/tools/tests/test_worktree_exec.py -v`
Expected: PASS, 6 passed.

- [ ] **Step 5: Commit**

```bash
git add payload/tools/worktree_exec.py payload/tools/tests/test_worktree_exec.py
git commit -m "feat(worktree): worktree_exec.py — per-step git worktree create/merge"
```

---

### Task 2: Registry row, guide, and ARCHITECTURE.md

**Files:**
- Modify: `payload/registry/REGISTRY.md`
- Create: `payload/registry/guides/worktree-exec.md`
- Modify: `payload/MANIFEST`
- Modify: `ARCHITECTURE.md`

**Interfaces:** none — terminal task.

- [ ] **Step 1: Add the row** (after the `bb-gc` row added by the blackboard plan)

```
| worktree-exec | tool | meta-orchestration | Create/merge a per-step git worktree for an EXECUTE step marked "worktree": true — merge refuses until the step's own return.ok is true |
```

- [ ] **Step 2: Write the guide**

Create `payload/registry/guides/worktree-exec.md`:

```markdown
# Guide — worktree-exec

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
A plan step (agent-loop-v2 design spec, Phase 1 schema) can be marked
`"worktree": true` to run in isolation from the parent branch — Phase 4 of
that same spec. `worktree_exec.py` is the create/merge lifecycle for that
isolation; it is NOT `loop_autocommit.sh` (that tool refuses any repo other
than this framework repo and `~/.claude` — see its own routing logic).

## When to deploy (triggers)
Before dispatching an EXECUTE step whose plan JSON has `"worktree": true`
for that step — run `--create` first, dispatch the step's brief inside the
printed worktree path, then run `--merge` only after that step's return
records `ok: true` (or pass `--force` to override deliberately).

## Interface (how to invoke)
```
python3 ~/.claude/tools/worktree_exec.py --create --task-id <id> --step <id> --repo <path>
python3 ~/.claude/tools/worktree_exec.py --merge --task-id <id> --step <id> [--force]
```

## Composition (pairs with / hands off to)
Reads/writes `plan-task`'s own plan file (`load()`/`save()`) and the
`bb-write`/`bb-read` blackboard's `workflow_state` table — the parent
branch a worktree came from is a blackboard checkpoint, not a new plan
schema field.

## Build & maintenance notes
Lives at `~/.claude/tools/worktree_exec.py`. A real merge conflict always
aborts and preserves the worktree for manual resolution, regardless of
`--force` — `--force` only overrides the `return.ok` check, never a
conflict.
```

- [ ] **Step 3: Run `lint_registry.py` and confirm it's clean**

Run: `python3 payload/tools/lint_registry.py payload/registry`
Expected: `lint_registry: OK (0 error(s))`

- [ ] **Step 4: Add the MANIFEST entry**

In `payload/MANIFEST`, add after `link-file tools/audit_store.py` /the bb_*
lines added by the blackboard plan:

```
link-file tools/worktree_exec.py
```

- [ ] **Step 5: Add the ARCHITECTURE.md note**

Immediately after the blackboard bullet added by the blackboard plan (still
inside "### 2. Runtime loop layer"), add:

```
- **`payload/tools/worktree_exec.py`** creates and merges back a per-step
  git worktree at `~/.claude/worktrees/<task_id>/<step_id>/` for any EXECUTE
  step whose plan (Phase 1 schema) marks `"worktree": true` — opt-in per
  step. Merge-back is a normal `git merge` in that step's own project repo,
  gated on the step's recorded `return.ok`, not on `loop_autocommit.sh`
  (which only ever commits to this framework repo or `~/.claude`).
```

- [ ] **Step 6: Run the full relevant test suite**

Run: `python3 -m pytest payload/tools/tests/ -v -k "worktree or registry"`
Expected: all PASS (6 worktree tests + 13 registry tests = 19).

- [ ] **Step 7: Commit**

```bash
git add payload/registry/REGISTRY.md payload/registry/guides/worktree-exec.md \
        payload/MANIFEST ARCHITECTURE.md
git commit -m "docs(worktree): registry row, guide, and architecture note for worktree-exec"
```

---

## Testing & rollback

Both commits are independently revertable via `git revert` (Task 2 depends
on Task 1 existing to document, not the reverse for correctness — reverting
Task 2 alone leaves a working, just undocumented, tool).

Final check:

```bash
python3 -m pytest payload/tools/tests/ -v -k "worktree"
python3 payload/tools/lint_registry.py payload/registry
```

Expected: 6 tests passed; `lint_registry: OK (0 error(s))`.

Nothing in this phase touches the live `~/.claude` install or creates a real
worktree outside a test's own tempdir-backed repo — same dev-repo-only
boundary the prior phases of this spec have drawn.
