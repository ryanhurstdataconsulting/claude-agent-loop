#!/usr/bin/env python3
"""Objective assessment of a work order — the ASSESS stage, channel (a).

No model touches the verdict. Every input is something the machine already
recorded without being asked:

  from the metrics shard   tests passed/failed, tool_errors, error_rate,
                           turns, duration_s
  from git                 commits landed, reverts, follow-up fix commits

Those two months of metrics carry test results on 64% of subagent tasks and a
branch on 100% of them, while the subjective self-score exists on 4.6%. This
tool reads the signal that is actually there.

  assess_task.py <plan-id> [--propose-row]

The verdict is deliberately conservative: a part with no objective signal at all
assesses "unknown", never "clean". Silence is not success.

--propose-row prints a SUBAGENTS.md row for each part that did not come out
clean. It PRINTS only — the local-improvement path never writes inside a client
project, because that content must never reach loop_contribute.py. Stdlib only.
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_task  # noqa: E402

# The same ceiling H1 already uses for a resource's mean tool-error rate.
ERROR_RATE_MAX = 0.25
FOLLOWUP_HOURS = 24


def verdict(evidence):
    """clean / dirty / unknown, from objective fields alone.

    dirty wins over everything: a failed test, a revert, a follow-up fix, or an
    error rate above the ceiling. clean requires at least one real signal, so a
    part nobody measured can never be scored a success.
    """
    ev = evidence or {}
    if (ev.get("tests_failed") or 0) > 0:
        return "dirty"
    if (ev.get("reverts") or 0) > 0:
        return "dirty"
    if (ev.get("followup_fixes") or 0) > 0:
        return "dirty"
    rate = ev.get("error_rate")
    if rate is not None and rate > ERROR_RATE_MAX:
        return "dirty"
    has_signal = bool(ev.get("tests_detected")) or rate is not None \
        or (ev.get("commits") or 0) > 0
    return "clean" if has_signal else "unknown"


def metrics_for(metrics_dir, agent_task_id):
    """Newest kind:"task" record for this id across every monthly shard."""
    if not agent_task_id:
        return None
    d = pathlib.Path(metrics_dir)
    if not d.is_dir():
        return None
    found = None
    for shard in sorted(d.glob("*.jsonl")):
        try:
            text = shard.read_text(errors="replace")
        except Exception:
            continue
        for raw in text.splitlines():
            raw = raw.strip()
            if not raw or agent_task_id not in raw:
                continue
            try:
                rec = json.loads(raw)
            except Exception:
                continue
            if rec.get("kind") == "task" and rec.get("task_id") == agent_task_id:
                found = rec
    return found


def _git(repo, args):
    try:
        out = subprocess.run(["git"] + args, cwd=repo, capture_output=True,
                             text=True, timeout=10)
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def git_evidence(repo, since, until, files):
    """Count commits, reverts, and follow-up fixes on the repo's current branch.

    ``files`` narrows the follow-up-fix count to commits touching the same paths
    the part reported; when it is empty, any fix-subject commit in the window
    counts. A path outside a git repository yields zeroes, never an exception.
    """
    out = {"commits": 0, "reverts": 0, "followup_fixes": 0}
    if not repo:
        return out
    args = ["log", "--no-merges", "--pretty=format:%H%x1f%s"]
    if since:
        args.append("--since=%s" % since)
    if until:
        args.append("--until=%s" % until)
    log = _git(repo, args)
    if not log.strip():
        return out
    subjects = []
    for line in log.splitlines():
        if "\x1f" not in line:
            continue
        sha, subject = line.split("\x1f", 1)
        subjects.append((sha, subject))
    out["commits"] = len(subjects)
    out["reverts"] = sum(1 for _, s in subjects if s.startswith("Revert "))

    fixes = 0
    for sha, subject in subjects:
        if not re.match(r"^fix\b|^fix\(", subject, re.IGNORECASE):
            continue
        if files:
            touched = _git(repo, ["show", "--name-only", "--pretty=format:", sha])
            touched_set = {t.strip() for t in touched.splitlines() if t.strip()}
            if not touched_set.intersection(set(files)):
                continue
        fixes += 1
    out["followup_fixes"] = fixes
    return out


def assess(wo, metrics_dir, repo=None, followup_hours=FOLLOWUP_HOURS):
    """Fill part.evidence and part.verdict for every part of a work order."""
    for part in wo.get("parts", []):
        rec = metrics_for(metrics_dir, part.get("agent_task_id"))
        tests = (rec or {}).get("tests") or {}
        files = ((part.get("log") or {}).get("files_touched")) or None
        git = git_evidence(repo, wo.get("created"), None, files) if repo else \
            {"commits": 0, "reverts": 0, "followup_fixes": 0}

        evidence = {
            "tests_detected": bool(tests.get("detected")),
            "tests_passed": tests.get("passed") or 0,
            "tests_failed": tests.get("failed") or 0,
            "tool_errors": (rec or {}).get("tool_errors"),
            "error_rate": (rec or {}).get("error_rate"),
            "turns": (rec or {}).get("turns"),
            "duration_s": (rec or {}).get("duration_s"),
            "commits": git["commits"],
            "reverts": git["reverts"],
            "followup_fixes": git["followup_fixes"],
            "metrics_record_found": rec is not None,
            "followup_hours": followup_hours,
        }
        part["evidence"] = evidence
        # A part whose own log reported failure cannot assess clean, whatever
        # the surrounding evidence says.
        part["verdict"] = "dirty" if part.get("status") == "failed" else verdict(evidence)
    return wo


def subagents_row(wo, part):
    """One markdown row proposed for a project's .claude/SUBAGENTS.md.

    Returned as text only. Writing it is the owner's decision.
    """
    def flat(s):
        return re.sub(r"\s+", " ", str(s or "")).replace("|", "\\|").strip()

    ev = part.get("evidence") or {}
    bits = []
    if ev.get("tests_failed"):
        bits.append("%d test(s) failed" % ev["tests_failed"])
    if ev.get("reverts"):
        bits.append("%d revert(s)" % ev["reverts"])
    if ev.get("followup_fixes"):
        bits.append("%d follow-up fix(es)" % ev["followup_fixes"])
    if ev.get("error_rate") is not None and ev["error_rate"] > ERROR_RATE_MAX:
        bits.append("tool-error rate %.2f" % ev["error_rate"])
    if not bits:
        bits.append("no objective signal recorded")
    why = "%s on %s (%s)" % (flat(part.get("verdict")), flat(wo.get("plan_id")),
                             "; ".join(bits))
    return "| %s | %s | %s |" % (flat(part.get("role")), why, flat(part.get("goal")))


def main(argv=None):
    home = pathlib.Path.home() / ".claude"
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("plan_id")
    p.add_argument("--state-dir", default=str(home / "metrics" / "state" / "workorders"))
    p.add_argument("--metrics-dir", default=str(home / "metrics"))
    p.add_argument("--repo", default=None,
                   help="repository to read git evidence from (default: none)")
    p.add_argument("--followup-hours", type=int, default=FOLLOWUP_HOURS)
    p.add_argument("--propose-row", action="store_true",
                   help="print a SUBAGENTS.md row per non-clean part; writes nothing")
    a = p.parse_args(argv)

    try:
        wo = plan_task.load(a.state_dir, a.plan_id)
    except plan_task.WorkOrderError as exc:
        sys.stderr.write("%s\n" % exc)
        return 2

    assess(wo, a.metrics_dir, repo=a.repo, followup_hours=a.followup_hours)
    plan_task.save(a.state_dir, wo)

    for part in wo["parts"]:
        ev = part["evidence"]
        print("%s  %-9s %-14s tests %s/%s  errors %s  commits %s  %s" % (
            part["part_id"], part["verdict"], part.get("role") or "-",
            ev["tests_passed"], ev["tests_passed"] + ev["tests_failed"],
            ev["tool_errors"] if ev["tool_errors"] is not None else "-",
            ev["commits"], part.get("goal", "")))

    if a.propose_row:
        rows = [subagents_row(wo, p_) for p_ in wo["parts"] if p_["verdict"] != "clean"]
        if rows:
            print("\nProposed .claude/SUBAGENTS.md rows (NOT written — your call):")
            print("| Agent | Why this one | When to dispatch |")
            print("|---|---|---|")
            for r in rows:
                print(r)
        else:
            print("\nEvery part assessed clean — no SUBAGENTS.md row proposed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
