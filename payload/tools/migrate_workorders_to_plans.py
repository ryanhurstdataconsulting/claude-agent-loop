#!/usr/bin/env python3
"""One-time migration: schema-1 work orders -> schema-2 plans.

  ~/.claude/metrics/state/workorders/<plan_id>.json   (schema 1, parts[])
      -> ~/.claude/plans/<YYYY-MM-DD>/<task_id>.json  (schema 2, steps[])

Originals are MOVED into an archive directory, never deleted — this is a
real, historical, one-shot migration over live user data, not a repeatable
sync. Run with ``--dry-run`` first and inspect the output before running for
real. Stdlib only.
"""
import argparse
import json
import os
import pathlib
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_task  # noqa: E402  (same-dir tool import)


def _migrate_step(part):
    """Map one schema-1 part to one schema-2 step per the field-mapping table."""
    status = part.get("status")
    if status == "assigned":
        status = "pending"

    evidence = part.get("evidence")
    verdict = part.get("verdict")
    if evidence is not None and verdict is not None:
        assessment = {"evidence": evidence, "verdict": verdict}
    else:
        assessment = None

    return {
        "id": part.get("part_id"),
        "goal": part.get("goal"),
        "status": status,
        "agent": part.get("role"),
        "agent_score": part.get("role_score"),
        "skills": part.get("skills"),
        "model": part.get("model"),
        "agent_task_id": part.get("agent_task_id"),
        "depends_on": [],
        "budget_tokens": None,
        "worktree": False,
        # brief was rendered on demand under schema 1 and never persisted, so
        # there is no historical text to carry over for any step, open or
        # closed. A still-open step re-renders one via `plan_task.py
        # --assign` before it is ever re-dispatched; a closed step's brief is
        # never read again.
        "brief": "",
        "return": part.get("log"),
        "assessment": assessment,
        # "score" (schema 1) is dropped — no schema-2 equivalent (Task 1).
    }


def migrate_one(old):
    """Migrate one schema-1 work-order dict to a schema-2 plan dict.

    Pure function — does not touch the filesystem.
    """
    new = {
        "schema": 2,
        "task_id": old.get("plan_id"),
        "task": old.get("task"),
        "supervisor_reasoning": "",
        "source": old.get("source"),
        "plan_doc": old.get("plan_doc"),
        "created": old.get("created"),
        "project": old.get("project"),
        "git_branch": old.get("git_branch"),
        "steps": [_migrate_step(p) for p in old.get("parts", [])],
        # "forced" (schema 1) is dropped — the creativity-gate override it
        # recorded no longer exists as a concept (Task 1).
    }
    if "closed_at" in old:
        new["closed_at"] = old["closed_at"]
    return new


def migrate_all(state_dir, base_dir, archive_dir, dry_run=False):
    """Migrate every ``*.json`` in ``state_dir`` to ``base_dir``.

    Unless ``dry_run``, each new plan is written via ``plan_task.save()`` and
    its schema-1 original is moved into ``archive_dir`` (created if absent).
    Returns one summary dict per file: ``{"task_id", "new_path", "step_count"}``.
    """
    summaries = []
    for src in sorted(pathlib.Path(state_dir).glob("*.json")):
        old = json.loads(src.read_text())
        new = migrate_one(old)
        task_id = new["task_id"]
        new_path = pathlib.Path(base_dir) / plan_task.date_partition_for(task_id) / (task_id + ".json")

        if not dry_run:
            plan_task.save(base_dir, new)
            archive = pathlib.Path(archive_dir)
            archive.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(archive / src.name))

        summaries.append({
            "task_id": task_id,
            "new_path": str(new_path),
            "step_count": len(new["steps"]),
        })
    return summaries


# --- CLI ---------------------------------------------------------------------
def _default_state_dir():
    return str(pathlib.Path.home() / ".claude" / "metrics" / "state" / "workorders")


def _default_base_dir():
    return str(pathlib.Path.home() / ".claude" / "plans")


def _default_archive_dir():
    return str(pathlib.Path.home() / ".claude" / "metrics" / "state" / "workorders_archive")


def _build_parser():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--state-dir", default=_default_state_dir(),
                    help="schema-1 work-order source directory")
    p.add_argument("--base-dir", default=_default_base_dir(),
                    help="schema-2 plan destination directory")
    p.add_argument("--archive-dir", default=_default_archive_dir(),
                    help="where schema-1 originals are moved after a real run")
    p.add_argument("--dry-run", action="store_true",
                    help="report what would happen; write nothing")
    return p


def main(argv=None):
    a = _build_parser().parse_args(argv)
    summaries = migrate_all(a.state_dir, a.base_dir, a.archive_dir, dry_run=a.dry_run)
    prefix = "[dry-run] " if a.dry_run else ""
    for s in summaries:
        print("%s%s -> %s (%d step%s)" % (
            prefix, s["task_id"], s["new_path"], s["step_count"],
            "" if s["step_count"] == 1 else "s"))
    print("%s%d file(s)" % (prefix, len(summaries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
