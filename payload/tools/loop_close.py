#!/usr/bin/env python3
"""Close finished work orders automatically — link, assess, and emit to metrics.

This is the half of the loop that must never need a human. It runs from the
SessionEnd hook and does, unattended, what was previously a person noticing a
JSON file had appeared:

  LINK    resolve each part's agent-<id> by finding the subagent transcript that
          contains the part_id. make_brief.py embeds plan_id and part_id in the
          dispatch prompt, so the identifiers are already sitting in the
          transcript — no agent cooperation and no bookkeeping required.
  ASSESS  reuse assess_task.assess() for the objective verdict.
  EMIT    write one kind:"task" record per part into the monthly metrics shard,
          tagged resources_source="workorder".
  MARK    stamp closed_at on the work order so it is never double-counted.

Why emit task records rather than teach the heuristics engine a new mode: the
engine already evaluates rules over kind:"task" records and weights them by
resources_source. Emitting in that shape means every existing rule starts
working on work-order evidence with no new evaluator — and "workorder" ranks as
PRECISE attribution, because a tool wrote it rather than a regex scraping it out
of prose.

  loop_close.py --all              # close everything ready; the hook's call
  loop_close.py <plan-id>          # close one
  loop_close.py --all --dry-run    # show what would be emitted

A work order is ready when every part has reached done or failed. Stdlib only.
"""
import argparse
import datetime
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assess_task  # noqa: E402
import obs_emit  # noqa: E402
import plan_task  # noqa: E402

SCHEMA = 1
TERMINAL = ("done", "failed")


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_ready(wo):
    """Ready when there is at least one part and every part has finished."""
    parts = wo.get("parts") or []
    if not parts:
        return False
    return all(p.get("status") in TERMINAL for p in parts)


def is_closed(wo):
    return bool(wo.get("closed_at"))


def find_agent_id(projects_dir, part_id, plan_id=None):
    """Find the agent-<id> whose transcript carries this part_id.

    make_brief.py writes both identifiers into the dispatch prompt, so the
    subagent's own transcript contains them. Newest match wins, so a re-dispatch
    of the same part resolves to the most recent attempt.
    """
    root = pathlib.Path(projects_dir)
    if not root.is_dir() or not part_id:
        return None
    best, best_mtime = None, -1.0
    for path in root.glob("*/*/subagents/agent-*.jsonl"):
        try:
            if path.stat().st_mtime <= best_mtime:
                continue
            text = path.read_text(errors="replace")
        except Exception:
            continue
        # Both identifiers must appear; part ids like "p1" are far too short to
        # match on alone.
        if plan_id and plan_id not in text:
            continue
        if part_id not in text:
            continue
        best, best_mtime = path.stem, path.stat().st_mtime
    return best


def link(wo, projects_dir):
    """Fill agent_task_id on any part that lacks one. Returns how many landed."""
    filled = 0
    for part in wo.get("parts") or []:
        if part.get("agent_task_id"):
            continue
        found = find_agent_id(projects_dir, part.get("part_id"), wo.get("plan_id"))
        if found:
            part["agent_task_id"] = found
            filled += 1
    return filled


def _shard_for(metrics_dir, ts_iso):
    return pathlib.Path(metrics_dir) / ("%s.jsonl" % ts_iso[:7])


def task_records(wo):
    """One kind:"task" record per part, in the shape harvest_metrics.py emits.

    resources_deployed carries the part's role and skills — written by
    plan_task.py --assign, never parsed out of prose — so resources_source is
    "workorder" and the attribution is precise.
    """
    out = []
    now = _now_iso()
    for part in wo.get("parts") or []:
        ev = part.get("evidence") or {}
        resources = []
        if part.get("role") and part["role"] != "generalist":
            resources.append(part["role"])
        resources.extend(part.get("skills") or [])
        for s in ((part.get("log") or {}).get("skills_used") or []):
            if s not in resources:
                resources.append(s)
        out.append({
            "schema": SCHEMA,
            "kind": "task",
            "task_id": part.get("agent_task_id") or "%s-%s" % (wo.get("plan_id"), part.get("part_id")),
            "plan_id": wo.get("plan_id"),
            "part_id": part.get("part_id"),
            "session_id": wo.get("session_id"),
            "project": wo.get("project"),
            "git_branch": wo.get("git_branch"),
            "resources_deployed": resources,
            "resources_source": "workorder",
            "announce_found": True,
            "bare": not resources,
            "verdict": part.get("verdict"),
            "tests": {"detected": ev.get("tests_detected", False),
                      "passed": ev.get("tests_passed") or 0,
                      "failed": ev.get("tests_failed") or 0},
            "tool_errors": ev.get("tool_errors") or 0,
            "error_rate": ev.get("error_rate"),
            "turns": ev.get("turns"),
            "duration_s": ev.get("duration_s"),
            "commits": ev.get("commits") or 0,
            "reverts": ev.get("reverts") or 0,
            "followup_fixes": ev.get("followup_fixes") or 0,
            "interrupted": 0,
            "trigger": "loop_close",
            "ts_start": wo.get("created"),
            "ts_end": now,
        })
    return out


def run_records(wo):
    """One kind:"run" (subagent) record per part — a derived outcome/stop_reason
    summary, never asserted. See the Phase 2 plan's design decision #2 for the
    outcome-severity mapping; stop_reason is always "completed" here because no
    process-level signal (CLI exit code, interrupt flag) exists at the part
    level — a documented limitation, not a guess dressed up as data.
    """
    out = []
    now = _now_iso()
    for part in wo.get("parts") or []:
        ev = part.get("evidence") or {}
        verdict = part.get("verdict") or "unknown"
        hard_failure = (ev.get("tests_failed") or 0) > 0 or (ev.get("reverts") or 0) > 0
        if verdict == "clean":
            outcome = "success"
        elif verdict == "dirty" and hard_failure:
            outcome = "failure"
        else:
            outcome = "partial"
        task_id = part.get("agent_task_id") or "%s-%s" % (wo.get("plan_id"), part.get("part_id"))
        out.append({
            "schema": "run.v1",
            "kind": "run",
            "task_id": task_id,
            "run_kind": "subagent",
            "parent_task_id": None,
            "outcome": outcome,
            "stop_reason": "completed",
            "trace_id": obs_emit.trace_id_for(wo.get("plan_id") or "unknown"),
            "plan_id": wo.get("plan_id"),
            "part_id": part.get("part_id"),
            "ts_start": wo.get("created"),
            "ts_end": now,
        })
    return out


def emit(metrics_dir, records):
    """Append records to their monthly shard. O_APPEND, one write per line."""
    if not records:
        return 0
    pathlib.Path(metrics_dir).mkdir(parents=True, exist_ok=True)
    n = 0
    for rec in records:
        shard = _shard_for(metrics_dir, rec.get("ts_end") or _now_iso())
        with open(shard, "a") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        n += 1
    return n


def close_one(wo, metrics_dir, projects_dir, repo=None, dry_run=False):
    """Link, assess, emit, and stamp. Returns a summary dict."""
    linked = link(wo, projects_dir)
    assess_task.assess(wo, metrics_dir, repo=repo)
    records = task_records(wo) + run_records(wo)
    verdicts = {}
    for part in wo.get("parts") or []:
        v = part.get("verdict") or "unknown"
        verdicts[v] = verdicts.get(v, 0) + 1
    if not dry_run:
        emit(metrics_dir, records)
        wo["closed_at"] = _now_iso()
    return {"plan_id": wo.get("plan_id"), "parts": len(wo.get("parts") or []),
            "linked": linked, "verdicts": verdicts, "records": records}


def ready_work_orders(state_dir):
    d = pathlib.Path(state_dir)
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.json")):
        try:
            wo = plan_task.load(state_dir, f.stem)
        except Exception:
            continue
        if is_closed(wo) or not is_ready(wo):
            continue
        out.append(wo)
    return out


def main(argv=None):
    home = pathlib.Path.home() / ".claude"
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("plan_id", nargs="?", help="close one work order")
    p.add_argument("--all", action="store_true", help="close every ready work order")
    p.add_argument("--state-dir", default=str(home / "metrics" / "state" / "workorders"))
    p.add_argument("--metrics-dir", default=str(home / "metrics"))
    p.add_argument("--projects-dir", default=str(home / "projects"))
    p.add_argument("--repo", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true", dest="as_json")
    a = p.parse_args(argv)

    if not a.all and not a.plan_id:
        sys.stderr.write("give a plan id or --all\n")
        return 2

    if a.all:
        targets = ready_work_orders(a.state_dir)
    else:
        try:
            wo = plan_task.load(a.state_dir, a.plan_id)
        except plan_task.WorkOrderError as exc:
            sys.stderr.write("%s\n" % exc)
            return 2
        if is_closed(wo):
            sys.stderr.write("%s is already closed\n" % a.plan_id)
            return 2
        targets = [wo]

    summaries = []
    for wo in targets:
        s = close_one(wo, a.metrics_dir, a.projects_dir, repo=a.repo, dry_run=a.dry_run)
        if not a.dry_run:
            plan_task.save(a.state_dir, wo)
        summaries.append(s)

    if a.as_json:
        print(json.dumps([{k: v for k, v in s.items() if k != "records"}
                          for s in summaries], sort_keys=True))
    else:
        for s in summaries:
            bits = ", ".join("%s %d" % (k, v) for k, v in sorted(s["verdicts"].items()))
            print("closed %s — %d part(s), %d newly linked, %s"
                  % (s["plan_id"], s["parts"], s["linked"], bits or "no verdicts"))
        if not summaries:
            print("nothing ready to close")
    return 0


if __name__ == "__main__":
    sys.exit(main())
