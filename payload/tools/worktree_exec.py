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
