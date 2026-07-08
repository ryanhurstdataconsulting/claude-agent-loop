#!/usr/bin/env python3
"""Contribute gate-cleared local resources upstream — the package's feedback loop.

Think of the install like a fleet vehicle: sessions build local resources and
record local metrics; when the machine "plugs in" (SessionStart, or this tool
run by hand), improvements that pass every publication gate are packaged and
pushed to a ``contrib/<date>-<slug>`` branch of the framework repo, with a
summary of what changed, how it improved the local environment, the measured
agent-performance delta, and how to fold it into the main project.

The safety contract (non-negotiable):
  * DEFAULT-DENY — a candidate ships only if ``classify_visibility`` says
    GENERIC, the secret/PII scrub gate passes, and (for markdown) the grammar
    gate passes. CLIENT or UNSURE content NEVER leaves the machine.
  * Pushes go to ``contrib/*`` branches only — never ``main``. Merging is a
    human decision on the pull request.
  * Kill switch: ``AGENT_LOOP_CONTRIBUTE=0``. ``--nudge`` never pushes.
  * The framework checkout is never disturbed: packaging happens in a
    temporary ``git worktree`` and the state file dedups re-contribution.

Usage:
  python3 loop_contribute.py                # detect, gate, push, print the link
  python3 loop_contribute.py --nudge        # one-line SessionStart nudge, no push
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

TOOLS_DIR = pathlib.Path(__file__).resolve().parent
GIT_TIMEOUT = 60


def sh(args, cwd=None, timeout=GIT_TIMEOUT):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)


def detect_candidates(claude_dir, state):
    """Local (non-symlink) resources not yet contributed: skills, tools, agents."""
    out = []
    skills = claude_dir / "skills"
    if skills.is_dir():
        for d in sorted(skills.iterdir()):
            if d.is_symlink() or not d.is_dir():
                continue
            if not (d / "SKILL.md").is_file():
                continue
            if ("skills/" + d.name) in state:
                continue
            files = [p for p in sorted(d.rglob("*")) if p.is_file()]
            out.append({"key": "skills/" + d.name, "kind": "skills",
                        "name": d.name, "root": d, "files": files,
                        "manifest": "link-dir skills/" + d.name})
    tools = claude_dir / "tools"
    if tools.is_dir():
        for f in sorted(tools.iterdir()):
            if f.is_symlink() or not f.is_file():
                continue
            if f.suffix not in (".py", ".sh"):
                continue
            if ("tools/" + f.name) in state:
                continue
            out.append({"key": "tools/" + f.name, "kind": "tools",
                        "name": f.name, "root": f, "files": [f],
                        "manifest": "link-file tools/" + f.name})
    agents = claude_dir / "agents"
    if agents.is_dir():
        for f in sorted(agents.iterdir()):
            if f.is_symlink() or not f.is_file() or f.suffix != ".md":
                continue
            if ("agents/" + f.name) in state:
                continue
            out.append({"key": "agents/" + f.name, "kind": "agents",
                        "name": f.name, "root": f, "files": [f],
                        "manifest": "link-file agents/" + f.name})
    return out


def gate(candidate, markers_file):
    """Run the publication gates over a candidate. Returns (ok, reason)."""
    files = [str(p) for p in candidate["files"]]
    if not files:
        return False, "empty candidate"
    vis = sh([sys.executable, str(TOOLS_DIR / "classify_visibility.py"),
              "--markers", str(markers_file)] + files, timeout=30)
    for line in vis.stdout.splitlines():
        verdict = line.split("\t", 1)[0].strip()
        if verdict and verdict != "GENERIC":
            return False, "visibility gate: %s" % (line.strip() or verdict)
    if vis.returncode not in (0,) and not vis.stdout.strip():
        return False, "visibility gate could not run"
    scrub = sh([sys.executable, str(TOOLS_DIR / "secret_pii_scrub_gate.py")] + files,
               timeout=30)
    if scrub.returncode != 0:
        return False, "secret/PII scrub gate failed"
    mds = [f for f in files if f.endswith(".md")]
    if mds:
        gram = sh([sys.executable, str(TOOLS_DIR / "prose_grammar_gate.py")] + mds,
                  timeout=30)
        if gram.returncode != 0:
            return False, "grammar gate failed"
    return True, "GENERIC; scrub OK" + ("; grammar OK" if mds else "")


def measure(candidate, metrics_dir):
    """Aggregate metric records that name this resource. Returns a prose line."""
    name = candidate["name"].rsplit(".", 1)[0]
    n = 0
    err_sum = 0.0
    err_n = 0
    passed = failed = 0
    task_ids = set()
    scales = []
    try:
        shards = sorted(pathlib.Path(metrics_dir).glob("*.jsonl"))
        for shard in shards:
            for line in shard.read_text().splitlines():
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("kind") == "task" and name in (rec.get("resources_deployed") or []):
                    n += 1
                    task_ids.add(rec.get("task_id"))
                    if isinstance(rec.get("error_rate"), (int, float)):
                        err_sum += rec["error_rate"]
                        err_n += 1
                    t = rec.get("tests") or {}
                    passed += int(t.get("passed") or 0)
                    failed += int(t.get("failed") or 0)
        for shard in shards:
            for line in shard.read_text().splitlines():
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("kind") == "score" and rec.get("task_id") in task_ids:
                    for k, v in (rec.get("scales") or {}).items():
                        scales.append("%s=%s" % (k, v))
    except Exception:
        pass
    if n == 0:
        return "no recorded deployments yet — impact to be measured after adoption"
    bits = ["deployed on %d task(s)" % n]
    if err_n:
        bits.append("mean tool-error rate %.3f" % (err_sum / err_n))
    bits.append("tests: %d passed, %d failed" % (passed, failed))
    if scales:
        bits.append("self-scores: " + ", ".join(sorted(set(scales))))
    return " · ".join(bits)


def summary_md(ok, withheld, date):
    lines = ["# Contribution — %s" % date, ""]
    lines.append("Automated, gate-cleared contribution from a fleet install. Every included "
                 "resource classified GENERIC and passed the secret/PII scrub"
                 " (and, for markdown, the grammar gate) before leaving the machine.")
    lines.append("")
    lines.append("## What changed")
    for c in ok:
        lines.append("- **`%s`** (%s) — %d file(s), staged into `payload/%s/`."
                     % (c["name"], c["kind"].rstrip("s"), len(c["files"]), c["key"]))
    lines.append("")
    lines.append("## How it improved the local environment")
    for c in ok:
        lines.append("- `%s`: filled a recurring local need; installed and exercised via the "
                     "resource loop on the contributing machine." % c["name"])
    lines.append("")
    lines.append("## Agent-performance delta")
    for c in ok:
        lines.append("- `%s`: %s." % (c["name"], c["evidence"]))
    lines.append("")
    lines.append("## How to implement it into the main project")
    lines.append("1. Review this branch's diff (each resource lands under `payload/` with its "
                 "MANIFEST line already added).")
    lines.append("2. Run the framework gates locally: `bash payload/tools/tests/run_all.sh` and "
                 "`python3 payload/tools/lint_registry.py payload/registry`.")
    lines.append("3. Merge the pull request; installs pick it up on their next auto-update.")
    if withheld:
        lines.append("")
        lines.append("## Withheld locally (never pushed)")
        for c, reason in withheld:
            lines.append("- `%s` — %s." % (c["name"], reason))
    lines.append("")
    return "\n".join(lines)


def branch_link(repo, branch):
    try:
        url = sh(["git", "-C", str(repo), "config", "--get", "remote.origin.url"]).stdout.strip()
    except Exception:
        url = ""
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
    if m:
        return "https://github.com/%s/%s/tree/%s" % (m.group(1), m.group(2), branch)
    return "%s (branch %s)" % (url or "origin", branch)


def main(argv=None):
    if os.environ.get("AGENT_LOOP_CONTRIBUTE", "1") == "0":
        return 0
    home = pathlib.Path.home() / ".claude"
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--claude-dir", default=str(home))
    p.add_argument("--repo", default=str(pathlib.Path.home() / "dev" / "claude-agent-loop"))
    p.add_argument("--markers-file", default=None)
    p.add_argument("--metrics-dir", default=None)
    p.add_argument("--state-file", default=None)
    p.add_argument("--nudge", action="store_true",
                   help="print a one-line pending count; never pushes")
    a = p.parse_args(argv)
    claude_dir = pathlib.Path(a.claude_dir)
    repo = pathlib.Path(a.repo)
    markers = pathlib.Path(a.markers_file or claude_dir / "learning" / "CLIENT_MARKERS.txt")
    metrics_dir = pathlib.Path(a.metrics_dir or claude_dir / "metrics")
    state_file = pathlib.Path(a.state_file or claude_dir / "learning" / "contributed.json")

    try:
        state = json.loads(state_file.read_text())
        if not isinstance(state, dict):
            state = {}
    except Exception:
        state = {}

    candidates = detect_candidates(claude_dir, state)
    ok, withheld = [], []
    for c in candidates:
        good, reason = gate(c, markers)
        if good:
            c["evidence"] = measure(c, metrics_dir)
            ok.append(c)
        else:
            withheld.append((c, reason))

    if a.nudge:
        if ok:
            print("Loop contribute: %d gate-cleared contribution(s) ready to auto-push — "
                  "run python3 ~/.claude/tools/loop_contribute.py." % len(ok))
        return 0

    if not ok:
        if withheld:
            print("loop_contribute: %d candidate(s) withheld locally (never pushed):" % len(withheld))
            for c, reason in withheld:
                print("  - %s — %s" % (c["key"], reason))
        else:
            print("loop_contribute: nothing new to contribute.")
        return 0

    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9-]", "-", ok[0]["name"].rsplit(".", 1)[0].lower())
    if len(ok) > 1:
        slug += "-and-%d-more" % (len(ok) - 1)
    branch = "contrib/%s-%s" % (date, slug)
    n = 2
    while sh(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
              "refs/heads/" + branch]).returncode == 0:
        branch = "contrib/%s-%s-%d" % (date, slug, n)
        n += 1

    sh(["git", "-C", str(repo), "fetch", "--quiet", "origin"])
    base = "origin/main"
    if sh(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", base]).returncode != 0:
        base = "main"

    wt = pathlib.Path(tempfile.mkdtemp(prefix="agent-loop-contrib-"))
    try:
        add = sh(["git", "-C", str(repo), "worktree", "add", str(wt), "-b", branch, base])
        if add.returncode != 0:
            print("loop_contribute: could not stage a worktree (%s)" % add.stderr.strip())
            return 1
        for c in ok:
            dest_root = wt / "payload" / c["key"]
            if c["kind"] == "skills":
                shutil.copytree(c["root"], dest_root)
            else:
                dest_root.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(c["root"], dest_root)
        mani = wt / "payload" / "MANIFEST"
        text = mani.read_text() if mani.is_file() else "# MANIFEST\n"
        if "# --- contributed (auto) ---" not in text:
            text = text.rstrip("\n") + "\n\n# --- contributed (auto) ---\n"
        for c in ok:
            if c["manifest"] not in text:
                text += c["manifest"] + "\n"
        mani.parent.mkdir(parents=True, exist_ok=True)
        mani.write_text(text)
        contrib_dir = wt / "contributions"
        contrib_dir.mkdir(exist_ok=True)
        (contrib_dir / ("%s-%s.md" % (date, slug))).write_text(
            summary_md(ok, withheld, date))
        sh(["git", "-C", str(wt), "add", "-A"])
        names = ", ".join(c["name"] for c in ok)
        cm = sh(["git", "-C", str(wt), "commit", "-m",
                 "loop: contribute %s (gated GENERIC, auto-pushed to contrib branch)" % names,
                 "-m", "Automated fleet contribution. Gates: classify_visibility=GENERIC, "
                 "secret/PII scrub OK, grammar OK on markdown. See contributions/%s-%s.md "
                 "for the impact summary. Never targets main." % (date, slug)])
        if cm.returncode != 0:
            print("loop_contribute: commit failed (%s)" % cm.stderr.strip())
            return 1
        push = sh(["git", "-C", str(wt), "push", "-u", "origin", branch], timeout=120)
        if push.returncode != 0:
            print("loop_contribute: push failed (offline?) — branch %s kept locally. %s"
                  % (branch, push.stderr.strip().splitlines()[-1] if push.stderr.strip() else ""))
            return 0
    finally:
        sh(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)])
        shutil.rmtree(wt, ignore_errors=True)

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for c in ok:
        state[c["key"]] = {"branch": branch, "ts": now}
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    except Exception as exc:
        print("loop_contribute: state write failed: %s" % exc, file=sys.stderr)

    print("loop_contribute: pushed %d contribution(s) to %s" % (len(ok), branch))
    print("Link: %s" % branch_link(repo, branch))
    if withheld:
        print("Withheld locally (never pushed): %d — %s"
              % (len(withheld), "; ".join("%s (%s)" % (c["key"], r) for c, r in withheld)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
