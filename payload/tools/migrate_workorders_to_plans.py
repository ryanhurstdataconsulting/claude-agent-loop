#!/usr/bin/env python3
"""One-time migration: schema-1 work orders -> schema-2 plans.

  ~/.claude/metrics/state/workorders/<plan_id>.json   (schema 1, parts[])
      -> ~/.claude/plans/<YYYY-MM-DD>/<task_id>.json  (schema 2, steps[])

Originals are MOVED into an archive directory, never deleted — this is a
real, historical, one-shot migration over live user data, not a repeatable
sync. Run with ``--dry-run`` first and inspect the output before running for
real.

Every file is migrated in isolation: a malformed or half-written one is
reported, left where it is, and the run continues with the rest, exiting 1
with a recap at the end. The source directory is written by live concurrent
sessions, so aborting mid-list on the first bad file would leave a
half-migrated tree with no record of where it stopped. Stdlib only.
"""
import argparse
import json
import os
import pathlib
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_task  # noqa: E402  (same-dir tool import)


class MigrationError(Exception):
    """A schema-1 file could not be trusted enough to migrate."""


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


def _require(cond, msg):
    """Raise MigrationError unless ``cond``. Every per-file precondition the
    migration checks goes through here, so a bad file always fails as a stated
    reason rather than as an AttributeError three frames down."""
    if not cond:
        raise MigrationError(msg)


def migrate_one(old):
    """Migrate one schema-1 work-order dict to a schema-2 plan dict.

    Pure function — does not touch the filesystem.
    """
    _require(isinstance(old, dict),
             "not a JSON object (got %s)" % type(old).__name__)
    _require(old.get("plan_id"), "no plan_id — cannot key the migrated plan")
    _require(isinstance(old.get("parts", []), list),
             "parts is %s, expected a list" % type(old.get("parts")).__name__)
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
        # Present and inert in schema 2, exactly like a step's depends_on /
        # budget_tokens / worktree. Schema 1 had no equivalent, so a migrated
        # plan gets the same empty default a freshly created one does.
        "termination": plan_task.termination_for(),
        "steps": [_migrate_step(p) for p in old.get("parts", [])],
        # "forced" (schema 1) is dropped — the creativity-gate override it
        # recorded no longer exists as a concept (Task 1).
    }
    if "closed_at" in old:
        new["closed_at"] = old["closed_at"]
    return new


def migrate_all(state_dir, base_dir, archive_dir, dry_run=False, out=None):
    """Migrate every ``*.json`` in ``state_dir`` to ``base_dir``.

    Unless ``dry_run``, each new plan is written via ``plan_task.save()`` and
    its schema-1 original is moved into ``archive_dir`` (created if absent).

    Returns ``(summaries, failures)``: one summary dict per migrated file
    (``{"task_id", "new_path", "step_count"}``) and one failure dict per file
    that could not be migrated (``{"file", "error"}``).

    **Each file is isolated.** This is a one-shot operation over live user data
    in a directory concurrent sessions are still writing to, so one malformed
    or half-written file must not abort the run and strand the tree half
    migrated. A file that fails is reported, LEFT IN PLACE (never archived, so
    a re-run retries it), and the loop continues. Progress prints as it
    happens, not batched at the end, so an operator watching a real run always
    knows which file a crash landed on.
    """
    out = sys.stdout if out is None else out
    prefix = "[dry-run] " if dry_run else ""
    summaries, failures = [], []
    for src in sorted(pathlib.Path(state_dir).glob("*.json")):
        try:
            old = json.loads(src.read_text())
            new = migrate_one(old)
            task_id = new["task_id"]
            partition = plan_task.date_partition_for(task_id)
            new_path = pathlib.Path(base_dir) / partition / (task_id + ".json")

            if not dry_run:
                plan_task.save(base_dir, new)
                archive = pathlib.Path(archive_dir)
                archive.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(archive / src.name))
        except Exception as exc:
            failures.append({"file": str(src), "error": "%s: %s"
                             % (type(exc).__name__, exc)})
            out.write("%sFAILED %s — %s: %s (left in place)\n"
                      % (prefix, src.name, type(exc).__name__, exc))
            continue

        summaries.append({
            "task_id": task_id,
            "new_path": str(new_path),
            "step_count": len(new["steps"]),
        })
        out.write("%s%s -> %s (%d step%s)\n"
                  % (prefix, task_id, new_path, len(new["steps"]),
                     "" if len(new["steps"]) == 1 else "s"))
    return summaries, failures


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
    prefix = "[dry-run] " if a.dry_run else ""
    # migrate_all prints each file's outcome as it happens; main prints only
    # the totals and the failure recap.
    summaries, failures = migrate_all(a.state_dir, a.base_dir, a.archive_dir,
                                      dry_run=a.dry_run)
    print("%s%d file(s) %s, %d %s"
          % (prefix, len(summaries),
             "would migrate" if a.dry_run else "migrated",
             len(failures), "would fail" if a.dry_run else "failed"))
    if failures:
        print("%sfailures (each original left in place — fix and re-run):"
              % prefix, file=sys.stderr)
        for f in failures:
            print("  %s — %s" % (f["file"], f["error"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
