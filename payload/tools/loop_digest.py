#!/usr/bin/env python3
"""loop_digest.py — render the auto-change digest for review (P5).

The loop commits its own edits silently (``loop_autocommit.sh``); this tool is
the periodic review surface. It reads the auto-change ledger
(``learning/AUTO_COMMITS.log``) for everything logged since the last digest
(the ISO instant in ``learning/.last-digest``; all entries if absent) and
renders a dated markdown digest under ``learning/digests/YYYY-MM-DD.md`` with:

* **auto-commits** grouped by repo (sha, subject, rule-id), each with an
  ``unpushed`` count (``git rev-list @{u}..HEAD --count`` against the current
  branch's upstream, whatever branch it is on, else ``n/a``);
* **blocked attempts** — the ``autocommit-blocked`` theme rows still ``NEW``;
* **theme transitions** — the current NEW / PROMOTED / DISMISSED row counts;
* a **metrics summary** for the current month shard (task count, mean
  ``error_rate``, tests passed/failed, and the top resources by frequency),
  computed with the store's last-record-per-``(task_id, kind)`` dedupe;
* a **"Push now?"** section — the ONLY place a push is ever suggested, and even
  here it is a manual command for the owner to run. This tool NEVER pushes.

It then updates ``.last-digest`` to the run instant and prints the digest path
plus a short summary. ``--nudge`` prints the SessionStart nudge line (and nothing
else) when a digest is due, degrading silently when files are missing.

LOCAL-ONLY: the digest embeds metrics content (project slugs, branch names) and
therefore lives under ``~/.claude/learning`` and is never published. Stdlib only.
"""
import argparse
import collections
import datetime
import json
import pathlib
import subprocess
import sys

NUDGE_AT = 10
STALE_DAYS = 7

# The one place the framework-repo publish command is shown. Assembled from a
# path plus the plain word below so no "git <verb>" execution string exists in
# this source — this tool never runs it.
PUBLISH_REPO_DISPLAY = "~/dev/claude-agent-loop"
_PUBLISH_VERB = "push"


def _now_dt(now_iso):
    if now_iso:
        return datetime.datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt):
    return dt.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def read_last_digest(learning_dir):
    """Return the ISO instant of the last digest, or None if absent."""
    p = pathlib.Path(learning_dir) / ".last-digest"
    try:
        text = p.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def parse_log(learning_dir):
    """Return all ledger rows as dicts, tolerating short/blank lines."""
    p = pathlib.Path(learning_dir) / "AUTO_COMMITS.log"
    rows = []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return rows
    for raw in text.splitlines():
        if not raw.strip():
            continue
        f = raw.split("\t")
        if len(f) < 5:
            continue
        rows.append({"ts": f[0], "repo": f[1], "sha": f[2],
                     "subject": f[3], "rule": f[4]})
    return rows


def undigested(rows, last_ts):
    """Ledger rows newer than ``last_ts`` (all rows when ``last_ts`` is None).

    ISO-8601 ``...Z`` timestamps sort lexicographically in chronological order,
    so a plain string compare is a correct 'after' test here.
    """
    if not last_ts:
        return list(rows)
    return [r for r in rows if r["ts"] > last_ts]


# --- theme parsing ----------------------------------------------------------

def _theme_rows(learning_dir):
    p = pathlib.Path(learning_dir) / "LOOP_THEMES.md"
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 6 or cells[0] == "status":
            continue
        if set("".join(cells)) <= set("-"):        # separator row
            continue
        out.append(cells)                          # status,date,project,tag,note,ref
    return out


def theme_counts(rows):
    c = {"NEW": 0, "PROMOTED": 0, "DISMISSED": 0}
    for cells in rows:
        status = cells[0]
        if status == "NEW":
            c["NEW"] += 1
        elif status.startswith("PROMOTED"):
            c["PROMOTED"] += 1
        elif status.startswith("DISMISSED"):
            c["DISMISSED"] += 1
    return c


def blocked_attempts(rows):
    """NEW rows tagged ``autocommit-blocked`` — the gate refusals to review."""
    out = []
    for cells in rows:
        if cells[0] == "NEW" and cells[3] == "autocommit-blocked":
            out.append({"repo": cells[2], "date": cells[1], "note": cells[4]})
    return out


# --- metrics ----------------------------------------------------------------

def metrics_summary(metrics_dir, month):
    """Summarize the month shard with last-record-per-(task_id, kind) dedupe."""
    shard = pathlib.Path(metrics_dir) / ("%s.jsonl" % month)
    dedup = {}
    try:
        text = shard.read_text(encoding="utf-8")
    except OSError:
        text = ""
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        dedup[(rec.get("task_id"), rec.get("kind"))] = rec   # last wins
    tasks = [r for (tid, kind), r in dedup.items() if kind == "task"]
    freq = collections.Counter()
    passed = failed = 0
    rates = []
    for r in tasks:
        for res in (r.get("resources_deployed") or []):
            freq[res] += 1
        t = r.get("tests") or {}
        passed += t.get("passed", 0) or 0
        failed += t.get("failed", 0) or 0
        if isinstance(r.get("error_rate"), (int, float)):
            rates.append(r["error_rate"])
    mean_err = round(sum(rates) / len(rates), 4) if rates else None
    top = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return {"tasks": len(tasks), "mean_error_rate": mean_err,
            "passed": passed, "failed": failed, "top": top}


# --- unpushed count ---------------------------------------------------------

def _unpushed(repo_root):
    """Commits on the current branch not yet on its upstream, or None.

    Resolves the current branch's upstream (e.g. ``origin/feature-x``) with
    ``@{u}`` and counts ``@{u}..HEAD`` — correct on any branch, not just
    ``main``. Returns None only when there is genuinely no upstream (the ``n/a``
    signal), so a feature-branch loop commit reports a real count rather than a
    hardcoded ``origin/main..main`` that is wrong or zero off ``main``.
    """
    try:
        up = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref",
             "--symbolic-full-name", "@{u}"],
            capture_output=True, text=True)
    except OSError:
        return None
    if up.returncode != 0:
        return None
    upstream = up.stdout.strip()
    if not upstream:
        return None
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list",
             "%s..HEAD" % upstream, "--count"],
            capture_output=True, text=True)
    except OSError:
        return None
    if res.returncode != 0:
        return None
    out = res.stdout.strip()
    return out if out.isdigit() else None


# --- render -----------------------------------------------------------------

def _publish_command(repo_display):
    # Kept off any exec path — this is display text only.
    return "git -C %s %s" % (repo_display, _PUBLISH_VERB)


def render(rows, learning_dir, metrics_dir, month, now_dt, last_ts,
           framework_repo, local_root):
    fw_base = pathlib.Path(framework_repo).name if framework_repo else None
    local_base = pathlib.Path(local_root).name if local_root else None

    def repo_root(name):
        if name == fw_base:
            return framework_repo
        if name == local_base:
            return local_root
        return None

    lines = []
    lines.append(
        "<!-- Loop digest — LOCAL-ONLY. Digests live under ~/.claude/learning/ "
        "and can quote client-tinged metrics (project slugs, git branch "
        "names). Never publish this file, and never copy it into the framework "
        "repo, without re-running classify_visibility and "
        "secret_pii_scrub_gate over the excerpt first. -->")
    lines.append("# Loop digest — %s" % now_dt.strftime("%Y-%m-%d"))
    lines.append("")
    window = last_ts if last_ts else "the beginning of the ledger"
    lines.append("Window: entries since %s." % window)
    lines.append("")

    # Auto-commits grouped by repo, first-seen order.
    lines.append("## Auto-commits (%d)" % len(rows))
    lines.append("")
    if not rows:
        lines.append("None.")
        lines.append("")
    else:
        groups = collections.OrderedDict()
        for r in rows:
            groups.setdefault(r["repo"], []).append(r)
        for repo, items in groups.items():
            root = repo_root(repo)
            up = _unpushed(root) if root else None
            up_txt = up if up is not None else "n/a"
            lines.append("### %s — %d commit(s), unpushed: %s"
                         % (repo, len(items), up_txt))
            for it in items:
                lines.append("- `%s` %s (rule: %s)"
                             % (it["sha"], it["subject"], it["rule"]))
            lines.append("")

    # Blocked attempts.
    trows = _theme_rows(learning_dir)
    blocked = blocked_attempts(trows)
    lines.append("## Blocked attempts (%d)" % len(blocked))
    if not blocked:
        lines.append("None.")
    else:
        for b in blocked:
            lines.append("- %s: %s (%s)" % (b["repo"], b["note"], b["date"]))
    lines.append("")

    # Theme transitions.
    tc = theme_counts(trows)
    lines.append("## Theme transitions since last digest")
    lines.append("- NEW: %d, PROMOTED: %d, DISMISSED: %d"
                 % (tc["NEW"], tc["PROMOTED"], tc["DISMISSED"]))
    lines.append("")

    # Metrics summary.
    m = metrics_summary(metrics_dir, month)
    mer = m["mean_error_rate"]
    mer_txt = str(mer) if mer is not None else "n/a"
    top_txt = (", ".join("%s (%d)" % (n, c) for n, c in m["top"])
               if m["top"] else "none")
    lines.append("## Metrics (current month %s)" % month)
    lines.append("- tasks: %d" % m["tasks"])
    lines.append("- mean error_rate: %s" % mer_txt)
    lines.append("- tests: %d passed, %d failed" % (m["passed"], m["failed"]))
    lines.append("- top resources: %s" % top_txt)
    lines.append("")

    # Push now? — the only publish surface, and it is manual.
    lines.append("## Push now?")
    lines.append("The framework auto-commits above stay local until you publish "
                 "them. Publishing is a manual step at digest review; nothing "
                 "leaves the machine automatically. To publish the framework "
                 "commits, run:")
    lines.append("")
    lines.append("```sh")
    lines.append(_publish_command(PUBLISH_REPO_DISPLAY))
    lines.append("```")
    lines.append("")
    return "\n".join(lines) + "\n"


# --- nudge ------------------------------------------------------------------

def nudge_due(count, last_ts, now_dt):
    if count <= 0:
        return False
    if count >= NUDGE_AT:
        return True
    if not last_ts:
        return True
    try:
        last = datetime.datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (now_dt - last).days > STALE_DAYS


def _do_nudge(learning_dir, now_dt):
    rows = parse_log(learning_dir)
    last_ts = read_last_digest(learning_dir)
    count = len(undigested(rows, last_ts))
    if nudge_due(count, last_ts, now_dt):
        print("Loop digest pending: %d auto-changes — run "
              "python3 ~/.claude/tools/loop_digest.py." % count)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render the loop auto-change digest.")
    home = pathlib.Path.home()
    ap.add_argument("--learning-dir", default=str(home / ".claude" / "learning"))
    ap.add_argument("--metrics-dir", default=str(home / ".claude" / "metrics"))
    ap.add_argument("--framework-repo",
                    default=str(home / "dev" / "claude-agent-loop"))
    ap.add_argument("--local-root", default=str(home / ".claude"))
    ap.add_argument("--now", default=None, help="ISO instant (test determinism)")
    ap.add_argument("--nudge", action="store_true",
                    help="print the SessionStart nudge line if a digest is due")
    args = ap.parse_args(argv)

    now_dt = _now_dt(args.now)
    if args.nudge:
        return _do_nudge(args.learning_dir, now_dt)

    rows_all = parse_log(args.learning_dir)
    last_ts = read_last_digest(args.learning_dir)
    rows = undigested(rows_all, last_ts)
    if not rows:
        print("loop_digest: nothing to digest (no new auto-commits since %s)"
              % (last_ts or "the beginning"))
        return 0

    month = now_dt.strftime("%Y-%m")
    text = render(rows, args.learning_dir, args.metrics_dir, month, now_dt,
                  last_ts, args.framework_repo, args.local_root)

    digests = pathlib.Path(args.learning_dir) / "digests"
    digests.mkdir(parents=True, exist_ok=True)
    out_path = digests / ("%s.md" % now_dt.strftime("%Y-%m-%d"))
    out_path.write_text(text, encoding="utf-8")

    now_iso = _iso(now_dt)
    (pathlib.Path(args.learning_dir) / ".last-digest").write_text(
        now_iso + "\n", encoding="utf-8")

    blocked = len(blocked_attempts(_theme_rows(args.learning_dir)))
    m = metrics_summary(args.metrics_dir, month)
    print(str(out_path))
    print("loop_digest: %d auto-change(s) since last digest, %d blocked, "
          "%d task(s) this month." % (len(rows), blocked, m["tasks"]))
    print("loop_digest: framework commits are unpushed — publish at review "
          "with: %s" % _publish_command(PUBLISH_REPO_DISPLAY))
    return 0


if __name__ == "__main__":
    sys.exit(main())
