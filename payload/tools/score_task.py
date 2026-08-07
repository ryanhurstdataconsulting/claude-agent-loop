#!/usr/bin/env python3
"""score_task.py — append a score to the metrics store (P3).

At task close, after the objective evidence is in, the Resource Loop's SCORE
step records an assessment against the scales in ``learning/SCALES.md``. This
CLI writes one ``kind:"score"`` record, joined to its task by ``task_id``.

Three modes:

* **score** (default): ``--task-id <id>`` plus one or more
  ``--scale name=level`` pairs — a subjective self-score. The task id is
  normalized to the harvester's join keys — ``agent-<id>`` (a subagent's own
  score) and ``session-*`` pass through, but a bare id is main-thread work and
  is prefixed ``session-`` (a note is printed). Each pair is validated against
  SCALES.md — an unknown scale or an unknown level for a known scale exits 2
  (the valid levels are printed). An optional ``--note`` is scrubbed through
  ``distill_transcripts.redact()`` before storage. ``resources_deployed`` is
  copied from the LAST task record for that ``task_id`` in the current and
  previous month shards (the store's last-wins join); for a ``session-*`` id
  with no task record it falls back to the LAST session record, else an empty
  list.

* **--auto <task_id>**: an objective assessment — no model touches the
  verdict. Loads the plan (``plan_task.load()``), fills every step's
  ``assessment`` from test results, tool errors, and git evidence (reverts,
  follow-up-fix commits) via ``auto_assess()``, saves the plan back, then
  appends ONE rolled-up ``kind:"score"`` record whose ``scales.evidence``
  reflects the worst verdict across every step (dirty beats unknown beats
  clean) plus ``scales.rework`` when any step shows a revert (``"major"``) or
  a follow-up fix (``"minor"``). Ported from the now-legacy
  ``assess_task.py`` — see ``verdict()``/``metrics_for()``/``git_evidence()``.

* **--new-scale**: ``--new-scale <id> --levels "a>b>c" --applies-to "<text>"
  --desc "<text>"`` appends a row under ``## Extended (learned on this
  machine)``. A duplicate id is refused (exit 2); after the append the file is
  re-linted in-process and the append is REVERTED if lint fails. Committing the
  edited scales file is the loop's autocommit duty (P5), not this tool's.

Records are appended via ``harvest_metrics._append_record`` so a score lands in
the same monthly shard scheme (``metrics/YYYY-MM.jsonl``) as tasks. Stdlib only.
"""
import argparse
import datetime
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

SCHEMA = 1
EXTENDED_HEADER = "## Extended (learned on this machine)"

# --- objective auto-assessment (ASSESS stage, channel (a); ported from
# assess_task.py so loop_close.py can call one tool for both the subjective
# self-score and the objective evidence) -------------------------------------
# The same ceiling H1 already uses for a resource's mean tool-error rate.
# MUST be defined before importing harvest_metrics (which imports it) to avoid
# circular import: score_task.py imports harvest_metrics at line 51; if
# harvest_metrics then tries to import ERROR_RATE_MAX before line 63, the
# module is not yet fully initialized.
ERROR_RATE_MAX = 0.25

import harvest_metrics as hm  # noqa: E402
import distill_transcripts as dt  # noqa: E402
import lint_scales as ls  # noqa: E402
import plan_task as pt  # noqa: E402

FOLLOWUP_HOURS = 24
# clean/dirty/unknown -> the SCALES.md evidence scale. "partial" is never
# emitted by this mapping (a signal either fully backs the claim or it
# doesn't), but the scale's third level remains valid for a human's own
# --scale evidence=partial.
EVIDENCE_SCALE = {"clean": "proven", "dirty": "asserted", "unknown": "asserted"}
# dirty > unknown > clean when rolling many steps' verdicts into one score —
# dirty wins so a bad step is never masked by good ones.
_VERDICT_RANK = {"clean": 0, "unknown": 1, "dirty": 2}


def _now_iso():
    """Current UTC instant as an ISO-8601 string with a trailing Z."""
    return (datetime.datetime.now(datetime.timezone.utc)
            .isoformat().replace("+00:00", "Z"))


def _month_keys_now():
    """[previous-month, current-month] as YYYY-MM keys, oldest first."""
    now = datetime.datetime.now(datetime.timezone.utc)
    prev = (now.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
    return [prev, now.strftime("%Y-%m")]


def _normalize_task_id(task_id):
    """Return ``(normalized_id, note_or_None)`` for a --task-id.

    Main-thread work is scored with a bare session id, but the harvester keys
    the main session rollup ``session-<sid>`` (and a subagent's own task record
    ``agent-<id>``). A --task-id that is already ``session-*`` or ``agent-*``
    passes through untouched; anything else is main-thread work and is prefixed
    ``session-`` so the score joins the session rollup. The returned note is
    printed by the caller when a normalization happened.
    """
    if task_id.startswith("session-") or task_id.startswith("agent-"):
        return task_id, None
    norm = "session-%s" % task_id
    note = ("score_task: normalized --task-id %r to %r "
            "(main-thread work joins the session record)" % (task_id, norm))
    return norm, note


def _lookup_resources(metrics_dir, task_id):
    """resources_deployed joined to a score on task_id (else []).

    Scans the previous then current month shard in order, so a later record
    supersedes an earlier one — the store's last-wins-per-(task_id, kind)
    contract. The LAST ``kind:"task"`` record for task_id is preferred. A
    main-thread score carries a normalized ``session-*`` id for which there is
    usually no task record, so the LAST ``kind:"session"`` record with the same
    task_id is used as a fallback. A task record still wins when both exist.
    """
    task_found = None       # last task record's resources (None = none seen)
    session_found = None    # last session record's resources (None = none seen)
    want_session = task_id.startswith("session-")
    for key in _month_keys_now():
        shard = pathlib.Path(metrics_dir) / ("%s.jsonl" % key)
        if not shard.is_file():
            continue
        for raw in shard.read_text(errors="replace").splitlines():
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if rec.get("task_id") != task_id:
                continue
            kind = rec.get("kind")
            if kind == "task":
                task_found = rec.get("resources_deployed") or []
            elif kind == "session" and want_session:
                session_found = rec.get("resources_deployed") or []
    if task_found is not None:
        return list(task_found)
    if session_found is not None:
        return list(session_found)
    return []


def verdict(evidence):
    """clean / dirty / unknown, from objective fields alone.

    dirty wins over everything: a failed test, a revert, a follow-up fix, or an
    error rate above the ceiling. clean requires at least one real signal, so a
    step nobody measured can never be scored a success.
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
    the step reported; when it is empty, any fix-subject commit in the window
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


def auto_assess(plan, metrics_dir, repo=None, followup_hours=FOLLOWUP_HOURS):
    """Fill every step's ``assessment`` and return the plan.

    ``plan["steps"][i]["assessment"]`` becomes ``{"evidence": ..., "verdict":
    ...}``. Ported from ``assess_task.assess()``: ``wo``/``parts``/``part_id``
    became ``plan``/``steps``/``id``, and ``part["evidence"]``/``part["verdict"]``
    merged into one ``step["assessment"]`` dict.
    """
    for step in plan.get("steps", []):
        rec = metrics_for(metrics_dir, step.get("agent_task_id"))
        tests = (rec or {}).get("tests") or {}
        files = ((step.get("return") or {}).get("files_touched")) or None
        git = git_evidence(repo, plan.get("created"), None, files) if repo else \
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
        # A step whose own return reported failure cannot assess clean,
        # whatever the surrounding evidence says.
        v = "dirty" if step.get("status") == "failed" else verdict(evidence)
        step["assessment"] = {"evidence": evidence, "verdict": v}
    return plan


def evidence_scale_for(v):
    """Map a clean/dirty/unknown verdict onto the SCALES.md evidence scale."""
    return EVIDENCE_SCALE[v]


def _worst_verdict(plan):
    """dirty > unknown > clean across every assessed step of a plan.

    A plan with no assessed steps rolls up to "unknown" — silence is not
    success, the same rule the per-step verdict() already applies.
    """
    verdicts = [(s.get("assessment") or {}).get("verdict")
                for s in plan.get("steps", [])]
    verdicts = [v for v in verdicts if v in _VERDICT_RANK]
    if not verdicts:
        return "unknown"
    return max(verdicts, key=lambda v: _VERDICT_RANK[v])


def _rework_flag(plan):
    """None / "minor" / "major" from every step's assessed evidence.

    A revert anywhere outranks a follow-up fix: "major" wins over "minor"
    when a plan shows both.
    """
    major = minor = False
    for step in plan.get("steps", []):
        ev = (step.get("assessment") or {}).get("evidence") or {}
        if (ev.get("reverts") or 0) > 0:
            major = True
        if (ev.get("followup_fixes") or 0) > 0:
            minor = True
    if major:
        return "major"
    if minor:
        return "minor"
    return None


def _auto(args):
    try:
        plan = pt.load(args.state_dir, args.auto)
    except pt.WorkOrderError as exc:
        sys.stderr.write("%s\n" % exc)
        return 2

    auto_assess(plan, args.metrics_dir, repo=args.repo,
                followup_hours=args.followup_hours)
    pt.save(args.state_dir, plan)

    worst = _worst_verdict(plan)
    scales = {"evidence": evidence_scale_for(worst)}
    rework = _rework_flag(plan)
    if rework:
        scales["rework"] = rework

    task_id, id_note = _normalize_task_id(args.auto)
    if id_note:
        print(id_note)

    note = dt.redact(args.note)[0] if args.note else ""
    record = {
        "schema": SCHEMA,
        "kind": "score",
        "task_id": task_id,
        "session_id": args.session_id,
        "project": args.project,
        # ts_end is the score's single timestamp; the shared _append_record
        # shard-router keys the monthly shard off ts_end.
        "ts_end": _now_iso(),
        "scales": scales,
        "note": note,
        "resources_deployed": _lookup_resources(args.metrics_dir, task_id),
    }
    if args.task_shape:
        record["task_shape"] = args.task_shape
    hm._append_record(args.metrics_dir, record)

    for step in plan.get("steps", []):
        a = step.get("assessment") or {}
        ev = a.get("evidence") or {}
        print("%s  %-9s %-14s tests %s/%s  errors %s  commits %s  %s" % (
            step.get("id"), a.get("verdict"), step.get("agent") or "-",
            ev.get("tests_passed", 0),
            ev.get("tests_passed", 0) + ev.get("tests_failed", 0),
            ev.get("tool_errors") if ev.get("tool_errors") is not None else "-",
            ev.get("commits", 0), step.get("goal", "")))
    print("score_task: recorded worst-verdict score for task %r: evidence=%s%s"
          % (task_id, scales["evidence"],
             (", rework=%s" % scales["rework"]) if "rework" in scales else ""))
    return 0


def _score(args):
    scales_def = ls.parse_scales(pathlib.Path(args.scales_file))
    chosen = {}
    for item in args.scale:
        if "=" not in item:
            print("score_task: bad --scale %r (expected name=level)" % item,
                  file=sys.stderr)
            return 2
        name, level = item.split("=", 1)
        name, level = name.strip(), level.strip()
        if name not in scales_def:
            print("score_task: unknown scale %r. Known scales: %s"
                  % (name, ", ".join(sorted(scales_def)) or "(none)"),
                  file=sys.stderr)
            return 2
        if level not in scales_def[name]:
            print("score_task: unknown level %r for scale %r. Valid levels: %s"
                  % (level, name, " > ".join(scales_def[name])),
                  file=sys.stderr)
            return 2
        chosen[name] = level

    task_id, id_note = _normalize_task_id(args.task_id)
    if id_note:
        print(id_note)

    note = dt.redact(args.note)[0] if args.note else ""
    record = {
        "schema": SCHEMA,
        "kind": "score",
        "task_id": task_id,
        "session_id": args.session_id,
        "project": args.project,
        # ts_end is the score's single timestamp; the shared _append_record
        # shard-router keys the monthly shard off ts_end.
        "ts_end": _now_iso(),
        "scales": chosen,
        "note": note,
        "resources_deployed": _lookup_resources(args.metrics_dir, task_id),
    }
    if args.task_shape:
        record["task_shape"] = args.task_shape
    hm._append_record(args.metrics_dir, record)
    print("score_task: recorded score for task %r: %s"
          % (task_id,
             ", ".join("%s=%s" % kv for kv in chosen.items())))
    return 0


def _insert_extended_row(text, row):
    """Return ``text`` with ``row`` appended to the Extended section, or None.

    The row is placed after the last non-blank line of the Extended section so
    it joins the existing group rather than trailing after blank lines.
    """
    lines = text.splitlines()
    hdr = None
    for idx, ln in enumerate(lines):
        if ln.strip() == EXTENDED_HEADER:
            hdr = idx
            break
    if hdr is None:
        return None
    section_end = len(lines)
    for j in range(hdr + 1, len(lines)):
        if lines[j].strip().startswith("## "):
            section_end = j
            break
    last = hdr
    for j in range(hdr + 1, section_end):
        if lines[j].strip():
            last = j
    lines.insert(last + 1, row)
    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + trailing


def _new_scale(args):
    # Every failure path here exits 2, not 1. Exit 2 is this tool's "the request
    # was refused / malformed" code (bad args, duplicate id, missing section, a
    # post-append lint failure that was reverted) — it means nothing was
    # committed. That is deliberately distinct from lint_scales.main's exit 1,
    # which reports "an existing file has lint errors." A caller can therefore
    # tell "score_task declined to act" (2) from "the scales file is dirty" (1).
    scales_path = pathlib.Path(args.scales_file)
    if not (args.levels and args.applies_to and args.desc):
        print("score_task: --new-scale requires --levels, --applies-to, "
              "and --desc", file=sys.stderr)
        return 2
    original = scales_path.read_text()
    if args.new_scale in ls.parse_scales(scales_path):
        print("score_task: scale id %r already exists — refusing"
              % args.new_scale, file=sys.stderr)
        return 2
    row = "| %s | %s | %s | %s |" % (
        args.new_scale, args.levels, args.applies_to, args.desc)
    new_text = _insert_extended_row(original, row)
    if new_text is None:
        print("score_task: no %r section in %s"
              % (EXTENDED_HEADER, scales_path), file=sys.stderr)
        return 2
    scales_path.write_text(new_text)
    errs = ls.lint(scales_path)
    if errs:
        scales_path.write_text(original)          # REVERT
        print("score_task: new scale %r failed lint — reverted:"
              % args.new_scale, file=sys.stderr)
        for e in errs:
            print("  %s" % e, file=sys.stderr)
        return 2
    print("score_task: appended scale %r under Extended. Committing the scales "
          "file is the loop's autocommit duty (P5); not committed here."
          % args.new_scale)
    return 0


def _build_parser():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Note: this tool only writes the record / edits the scales file. "
               "Committing the change is the loop's autocommit duty (P5).")
    ap.add_argument("--task-id", help="the task's join key (required to score): "
                    "session-<session-id> for main-thread work, agent-<id> for "
                    "a subagent's own score. A bare id is prefixed 'session-'.")
    ap.add_argument("--scale", action="append", default=None,
                    metavar="name=level",
                    help="a self-score, e.g. outcome=good (repeatable)")
    ap.add_argument("--note", help="a free-text note; redacted before storage")
    ap.add_argument("--auto", metavar="TASK_ID",
                    help="objectively assess every step of this plan and "
                         "append one rolled-up kind:\"score\" record, instead "
                         "of a subjective --scale self-score")
    ap.add_argument("--state-dir",
                    default=str(pathlib.Path.home() / ".claude" / "plans"),
                    help="plan storage dir for --auto (plan_task.py's own "
                         "default)")
    ap.add_argument("--repo", default=None,
                    help="repository to read git evidence from for --auto "
                         "(default: none)")
    ap.add_argument("--followup-hours", type=int, default=FOLLOWUP_HOURS,
                    dest="followup_hours",
                    help="follow-up-fix window recorded on each step's "
                         "evidence for --auto")
    ap.add_argument("--task-shape", dest="task_shape",
                    choices=["planning", "creation", "mechanical"],
                    help="how the work was classified when routed (H5 "
                         "route-cost evidence); omit when unclassified")
    ap.add_argument("--session-id", help="optional session id for the record")
    ap.add_argument("--project", help="optional project slug for the record")
    ap.add_argument("--metrics-dir",
                    default=str(pathlib.Path.home() / ".claude" / "metrics"))
    ap.add_argument("--scales-file",
                    default=str(pathlib.Path.home() / ".claude" / "learning"
                                / "SCALES.md"))
    ap.add_argument("--new-scale", metavar="ID",
                    help="mint a new Extended scale instead of scoring")
    ap.add_argument("--levels", metavar='"a>b>c"',
                    help="levels best>worst for --new-scale")
    ap.add_argument("--applies-to", dest="applies_to",
                    help="applies-to text for --new-scale")
    ap.add_argument("--desc", help="description text for --new-scale")
    return ap


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.new_scale:
        return _new_scale(args)
    if args.auto:
        return _auto(args)
    if not args.task_id:
        print("score_task: --task-id is required to score", file=sys.stderr)
        return 2
    if not args.scale:
        print("score_task: at least one --scale name=level is required",
              file=sys.stderr)
        return 2
    return _score(args)


if __name__ == "__main__":
    sys.exit(main())
