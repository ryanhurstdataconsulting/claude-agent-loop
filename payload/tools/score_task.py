#!/usr/bin/env python3
"""score_task.py — append a subjective self-score to the metrics store (P3).

At task close, after the objective evidence is in, the Resource Loop's SCORE
step records an ordinal self-assessment against the scales in
``learning/SCALES.md``. This CLI writes one ``kind:"score"`` record, joined to
its task by ``task_id``.

Two modes:

* **score** (default): ``--task-id <id>`` plus one or more
  ``--scale name=level`` pairs. Each pair is validated against SCALES.md — an
  unknown scale or an unknown level for a known scale exits 2 (the valid levels
  are printed). An optional ``--note`` is scrubbed through
  ``distill_transcripts.redact()`` before storage. ``resources_deployed`` is
  copied from the LAST task record for that ``task_id`` in the current and
  previous month shards (the store's last-wins join), else an empty list.

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
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import harvest_metrics as hm  # noqa: E402
import distill_transcripts as dt  # noqa: E402
import lint_scales as ls  # noqa: E402

SCHEMA = 1
EXTENDED_HEADER = "## Extended (learned on this machine)"


def _now_iso():
    """Current UTC instant as an ISO-8601 string with a trailing Z."""
    return (datetime.datetime.now(datetime.timezone.utc)
            .isoformat().replace("+00:00", "Z"))


def _month_keys_now():
    """[previous-month, current-month] as YYYY-MM keys, oldest first."""
    now = datetime.datetime.now(datetime.timezone.utc)
    prev = (now.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
    return [prev, now.strftime("%Y-%m")]


def _lookup_resources(metrics_dir, task_id):
    """resources_deployed from the LAST task record for task_id (else []).

    Scans the previous then current month shard, so a later record supersedes
    an earlier one — the store's last-wins-per-(task_id, kind) contract.
    """
    import json
    found = []
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
            if rec.get("kind") == "task" and rec.get("task_id") == task_id:
                found = rec.get("resources_deployed") or []
    return list(found)


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

    note = dt.redact(args.note)[0] if args.note else ""
    ts = _now_iso()
    record = {
        "schema": SCHEMA,
        "kind": "score",
        "task_id": args.task_id,
        "session_id": args.session_id,
        "project": args.project,
        "ts": ts,
        # ts_end mirrors ts solely so the shared _append_record shard-router
        # (which keys the monthly shard off ts_end) files this score correctly.
        "ts_end": ts,
        "scales": chosen,
        "note": note,
        "resources_deployed": _lookup_resources(args.metrics_dir, args.task_id),
    }
    hm._append_record(args.metrics_dir, record)
    print("score_task: recorded score for task %r: %s"
          % (args.task_id,
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
    ap.add_argument("--task-id", help="the task's join key (required to score); "
                    "use the session id for main-thread work")
    ap.add_argument("--scale", action="append", default=None,
                    metavar="name=level",
                    help="a self-score, e.g. outcome=good (repeatable)")
    ap.add_argument("--note", help="a free-text note; redacted before storage")
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
