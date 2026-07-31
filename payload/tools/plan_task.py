#!/usr/bin/env python3
"""Work-order lifecycle — the DECOMPOSE, ASSIGN, and LOG stages of the loop.

A work order is one JSON file per task that every loop stage reads and writes.
It replaces the ANNOUNCE prose contract: attribution becomes a write performed
by a tool rather than a formatted line scraped back out of a transcript.

  ~/.claude/metrics/state/workorders/<plan-id>.json

Stages this tool owns:

  DECOMPOSE  --new "<task>"          one part, for a well-specified task
             --from-plan <doc>       one part per "### Task N:" heading
  ASSIGN     --assign <plan-id>      route_role.route() per PART, not per task
  LOG        --log <plan-id> --part <id> --json <file>

The superpowers gate. A task that scores as creative cannot be decomposed
straight into a work order: --new refuses it with exit 3 and names the two
skills to run first (superpowers:brainstorming, then superpowers:writing-plans),
whose plan document then feeds --from-plan. --force overrides the refusal and
records ``"forced": true`` on the work order, so an override is visible in the
data instead of silent.

Creativity detection and model-tier selection are plain keyword arithmetic, the
same method route_role.py uses, so the same task always classifies the same way.

Unlike the loop's hooks, this tool is invoked deliberately and does NOT fail
open: every error exits non-zero with a stated reason. Stdlib only.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_role  # noqa: E402  (same-dir tool import, as score_task.py does)

SCHEMA = 1

# --- creativity gate ---------------------------------------------------------
# Strong signals score 2 (a creation verb alone is enough to trip the gate);
# supporting words score 1. At or above MIN_CREATIVE the task must go through
# brainstorming and writing-plans before it becomes a work order.
MIN_CREATIVE = 2
CREATIVE_STRONG = (
    "build", "design", "redesign", "implement", "create", "architect",
    "author", "refactor", "scaffold", "feature", "skill", "architecture",
    "rearchitect", "prototype",
)
CREATIVE_WEAK = ("new", "add", "change", "update", "improve", "extend")

# --- model tier (the ROUTE table, as keyword arithmetic) ---------------------
MODEL_BUCKETS = (
    ("opus", ("write", "build", "implement", "author", "design", "draft",
              "create", "scaffold", "refactor", "compose")),
    ("session", ("plan", "architecture", "review", "synthesize", "evaluate",
                 "assess", "decide", "compare", "strategy")),
    ("sonnet", ("extract", "sweep", "lint", "rename", "probe", "list",
                "count", "verify", "check", "grep", "collect")),
)
# Tie-break order, most capable first.
MODEL_PRECEDENCE = ("opus", "session", "sonnet")
DEFAULT_MODEL = "session"

TASK_HEADING = re.compile(r"^###\s+Task\s+\d+\s*:\s*(.+?)\s*$", re.MULTILINE)


class WorkOrderError(Exception):
    """A work order could not be read, parsed, or trusted."""


class PlanParseError(Exception):
    """A plan document carried no '### Task N:' headings."""


class CreativeTaskRefused(Exception):
    """A creative task was handed straight to --new without a plan."""


def _normalize(text):
    """Lowercase, and treat hyphen/underscore/slash as spaces — so "re-design",
    "re design", and "re_design" all match one phrase. Mirrors route_role."""
    return re.sub(r"\s+", " ", re.sub(r"[-_/]", " ", (text or "").lower())).strip()


def _hits(text_lc, phrase):
    """Score one phrase against normalized text. Tolerates a simple plural."""
    p = _normalize(phrase)
    if not p:
        return 0
    if re.search(r"(?<![a-z0-9])%ss?(?![a-z0-9])" % re.escape(p), text_lc):
        return 2 if " " in p else 1
    return 0


# --- DECOMPOSE ---------------------------------------------------------------
def plan_id(task, created):
    """Deterministic id: wo-<YYYYMMDD>-<slug>-<6 hex>.

    The hex is a SHA-256 prefix over task + created, so two different tasks
    minted in the same second never collide and the same inputs always
    reproduce the same id.
    """
    day = re.sub(r"[^0-9]", "", (created or "")[:10]) or "00000000"
    words = re.findall(r"[a-z0-9]+", (task or "").lower())[:6]
    slug = "-".join(words) or "task"
    digest = hashlib.sha256(("%s\n%s" % (task or "", created or "")).encode("utf-8")).hexdigest()[:6]
    return "wo-%s-%s-%s" % (day, slug[:48], digest)


def creative_score(task):
    lc = _normalize(task)
    total = 0
    for w in CREATIVE_STRONG:
        total += _hits(lc, w) * 2
    for w in CREATIVE_WEAK:
        total += _hits(lc, w)
    return total


def is_creative(task):
    return creative_score(task) >= MIN_CREATIVE


def _refusal_message(task):
    return (
        "creative task refused: %r scores %d on the creativity gate.\n"
        "Decompose it through the superpowers first, then feed the plan back:\n"
        "  1. Skill(superpowers:brainstorming)  — settle the design\n"
        "  2. Skill(superpowers:writing-plans)  — produce the task breakdown\n"
        "  3. plan_task.py --from-plan <plan-doc> --task %r\n"
        "Override with --force only when you accept an undesigned decomposition."
        % (task, creative_score(task), task)
    )


def parse_plan_doc(text):
    """Every '### Task N: <title>' heading becomes one part, in document order."""
    titles = [m.strip() for m in TASK_HEADING.findall(text or "")]
    if not titles:
        raise PlanParseError(
            "no '### Task N: <title>' headings found — a plan document must "
            "name its tasks with that heading shape")
    return titles


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create(task, source, plan_doc, force, project, branch, goals=None, created=None):
    """Build a work order in memory. Raises CreativeTaskRefused per the gate."""
    if source == "direct" and is_creative(task) and not force:
        raise CreativeTaskRefused(_refusal_message(task))
    created = created or _now_iso()
    goals = list(goals or [task])
    return {
        "schema": SCHEMA,
        "plan_id": plan_id(task, created),
        "task": task,
        "source": source,
        "plan_doc": plan_doc,
        "forced": bool(force and source == "direct" and is_creative(task)),
        "created": created,
        "project": project,
        "git_branch": branch,
        "parts": [
            {"part_id": "p%d" % (i + 1), "goal": g, "status": "pending",
             "role": None, "role_score": 0, "skills": [], "model": None,
             "agent_task_id": None, "log": None, "evidence": None,
             "verdict": None, "score": None}
            for i, g in enumerate(goals)
        ],
    }


# --- persistence -------------------------------------------------------------
def _path(state_dir, pid):
    return pathlib.Path(state_dir) / ("%s.json" % pid)


def save(state_dir, wo):
    p = _path(state_dir, wo["plan_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(wo, indent=1, sort_keys=True) + "\n")
    tmp.replace(p)


def load(state_dir, pid):
    p = _path(state_dir, pid)
    if not p.is_file():
        raise WorkOrderError("no work order at %s" % p)
    try:
        wo = json.loads(p.read_text())
    except Exception as exc:
        raise WorkOrderError("work order %s is not valid JSON: %s" % (p, exc))
    if not isinstance(wo, dict) or wo.get("schema") != SCHEMA:
        raise WorkOrderError(
            "work order %s has schema %r, expected %d — this tool does not "
            "migrate work orders" % (p, (wo or {}).get("schema"), SCHEMA))
    return wo


# --- ASSIGN ------------------------------------------------------------------
def model_for(goal):
    """Pick a model tier by keyword arithmetic; ties go to the more capable."""
    lc = _normalize(goal)
    scores = {}
    for tier, words in MODEL_BUCKETS:
        scores[tier] = sum(_hits(lc, w) for w in words)
    best = max(scores.values())
    if best == 0:
        return DEFAULT_MODEL
    for tier in MODEL_PRECEDENCE:
        if scores.get(tier) == best:
            return tier
    return DEFAULT_MODEL


def assign(wo, roles_dir):
    """Route every open part independently. Closed parts are left alone."""
    roles = route_role.load_roles(roles_dir)
    for part in wo.get("parts", []):
        if part.get("status") in ("done", "failed"):
            continue
        r = route_role.route(part.get("goal", ""), roles)
        part["role"] = r["role"]
        part["role_score"] = r["score"]
        part["skills"] = list(r["skills"])
        part["model"] = model_for(part.get("goal", ""))
        part["status"] = "assigned"
    return wo


# --- LOG ---------------------------------------------------------------------
def log_part(wo, part_id, payload):
    """Record a subagent's structured return on its part.

    Success must be asserted: a payload without an explicit ``ok: true`` is
    recorded as failed, never as done. An ambiguous log is not a success.
    """
    for part in wo.get("parts", []):
        if part.get("part_id") == part_id:
            part["log"] = payload
            part["status"] = "done" if payload.get("ok") is True else "failed"
            if payload.get("agent_task_id"):
                part["agent_task_id"] = payload["agent_task_id"]
            return part
    raise KeyError("no part %r in work order %s" % (part_id, wo.get("plan_id")))


# --- CLI ---------------------------------------------------------------------
def _default_state_dir():
    return str(pathlib.Path.home() / ".claude" / "metrics" / "state" / "workorders")


def _git(args, cwd=None):
    import subprocess
    try:
        out = subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                             text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _build_parser():
    home = pathlib.Path.home() / ".claude"
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    m = p.add_mutually_exclusive_group(required=True)
    m.add_argument("--new", metavar="TASK", help="create a work order from a task")
    m.add_argument("--from-plan", metavar="DOC", help="create one part per '### Task N:' heading")
    m.add_argument("--assign", metavar="PLAN_ID", help="route every open part")
    m.add_argument("--log", metavar="PLAN_ID", help="record a part's structured return")
    m.add_argument("--show", metavar="PLAN_ID", help="print a work order")
    m.add_argument("--classify", metavar="TEXT",
                   help="score text on the creativity gate; print JSON and exit 0")
    p.add_argument("--task", help="the task text (required with --from-plan)")
    p.add_argument("--part", help="part id (required with --log)")
    p.add_argument("--json", dest="json_file", help="file holding the part's return object")
    p.add_argument("--force", action="store_true", help="override the creativity gate")
    p.add_argument("--state-dir", default=_default_state_dir())
    p.add_argument("--roles-dir", default=str(home / "agents" / "roles"))
    return p


def main(argv=None):
    a = _build_parser().parse_args(argv)
    state, roles_dir = a.state_dir, a.roles_dir

    # --classify is the read-only surface the UserPromptSubmit gate calls on
    # every prompt. It touches no state and always exits 0.
    if a.classify is not None:
        score = creative_score(a.classify)
        print(json.dumps({"score": score, "creative": score >= MIN_CREATIVE,
                          "threshold": MIN_CREATIVE,
                          "model": model_for(a.classify)}, sort_keys=True))
        return 0

    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    project = re.sub(r"[^A-Za-z0-9]+", "-", os.getcwd())

    if a.new is not None or a.from_plan is not None:
        if a.from_plan is not None:
            if not a.task:
                sys.stderr.write("--from-plan requires --task\n")
                return 2
            try:
                text = pathlib.Path(a.from_plan).read_text()
            except Exception as exc:
                sys.stderr.write("cannot read plan doc: %s\n" % exc)
                return 2
            try:
                goals = parse_plan_doc(text)
            except PlanParseError as exc:
                sys.stderr.write("%s\n" % exc)
                return 2
            wo = create(a.task, "plan", a.from_plan, False, project, branch, goals=goals)
        else:
            try:
                wo = create(a.new, "direct", None, a.force, project, branch)
            except CreativeTaskRefused as exc:
                sys.stderr.write("%s\n" % exc)
                return 3
        assign(wo, roles_dir)
        save(state, wo)
        print("created work order %s" % wo["plan_id"])
        for part in wo["parts"]:
            print("  %s  %-14s %-8s %s" % (part["part_id"], part["role"],
                                           part["model"], part["goal"]))
        return 0

    try:
        if a.assign:
            wo = load(state, a.assign)
            assign(wo, roles_dir)
            save(state, wo)
            print("assigned %d part(s) in %s" % (len(wo["parts"]), wo["plan_id"]))
            return 0
        if a.log:
            if not a.part or not a.json_file:
                sys.stderr.write("--log requires --part and --json\n")
                return 2
            wo = load(state, a.log)
            payload = json.loads(pathlib.Path(a.json_file).read_text())
            part = log_part(wo, a.part, payload)
            save(state, wo)
            print("logged %s -> %s" % (part["part_id"], part["status"]))
            return 0
        if a.show:
            print(json.dumps(load(state, a.show), indent=1, sort_keys=True))
            return 0
    except (WorkOrderError, KeyError) as exc:
        sys.stderr.write("%s\n" % exc)
        return 2
    except Exception as exc:
        sys.stderr.write("unexpected failure: %s\n" % exc)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
