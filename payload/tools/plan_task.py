#!/usr/bin/env python3
"""Plan lifecycle — DECOMPOSE, ASSIGN, and BRIEF folded into one pass.

A plan is one JSON file per task that every loop stage reads and writes:

  ~/.claude/plans/<YYYY-MM-DD>/<task_id>.json

date-partitioned by the date embedded in ``task_id``, so a lookup by id needs
no directory scan.

Stages this tool owns:

  DECOMPOSE + ASSIGN + BRIEF
             --new "<task>"       one step, for a well-specified task
             --from-plan <doc>    one step per "### Task N:" heading
             --assign <task_id>   re-route every open (not done/failed) step
             --show <task_id>     print a plan

``create()`` (``--new`` / ``--from-plan``) returns a plan whose every step is
already routed to a role (``route_role.route()``), tiered to a model
(``model_for()``), and rendered into a full dispatchable subagent prompt
(``render_brief()``, folded in from the former ``make_brief.py``) — a caller
never waits through a separate "assigned" stage before dispatching. There is
no creativity gate: every task decomposes, nothing is refused.

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
import obs_emit  # noqa: E402  (same-dir tool import)
import route_role  # noqa: E402  (same-dir tool import, as score_task.py does)

SCHEMA = 2

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
TASK_ID_DATE = re.compile(r"wo-(\d{8})-")


class WorkOrderError(Exception):
    """A plan could not be read, parsed, or trusted."""


class PlanParseError(Exception):
    """A plan document carried no '### Task N:' headings."""


class BriefError(Exception):
    """A step is not in a state that can be briefed."""


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


# --- DECOMPOSE -----------------------------------------------------------
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


def parse_plan_doc(text):
    """Every '### Task N: <title>' heading becomes one step, in document order."""
    titles = [m.strip() for m in TASK_HEADING.findall(text or "")]
    if not titles:
        raise PlanParseError(
            "no '### Task N: <title>' headings found — a plan document must "
            "name its tasks with that heading shape")
    return titles


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create(task, source, plan_doc, project, branch, roles_dir, goals=None,
           created=None, reasoning="", budget_tokens=None, worktree=False):
    """Build a fully assigned, fully briefed plan in memory.

    DECOMPOSE, ASSIGN, and BRIEF happen synchronously in one pass: every step
    this returns already carries a routed agent, a model tier, and a
    ready-to-dispatch brief. There is no "assigned" status a caller waits
    through and no creativity gate that can refuse the task.
    """
    created = created or _now_iso()
    goals = list(goals or [task])
    plan = {
        "schema": SCHEMA,
        "task_id": plan_id(task, created),
        "task": task,
        "supervisor_reasoning": reasoning or "",
        "source": source,
        "plan_doc": plan_doc,
        "created": created,
        "project": project,
        "git_branch": branch,
        "steps": [],
    }
    roles = route_role.load_roles(roles_dir)
    for i, g in enumerate(goals):
        r = route_role.route(g, roles)
        step = {
            "id": "p%d" % (i + 1),
            "goal": g,
            "status": "pending",
            "agent": r["role"],
            "agent_score": r["score"],
            "skills": list(r["skills"]),
            "model": model_for(g),
            "agent_task_id": None,
            "depends_on": [],
            "budget_tokens": budget_tokens,
            "worktree": bool(worktree),
            "brief": None,
            "return": None,
            "assessment": None,
        }
        step["brief"] = render_brief(plan, step)
        plan["steps"].append(step)
    return plan


# --- BRIEF -----------------------------------------------------------------
RETURN_SCHEMA = {
    "task_id": "<echo the plan's task_id exactly>",
    "step_id": "<echo the step id exactly>",
    "ok": "true only if the step's goal was met and verified; false otherwise",
    "summary": "<one or two sentences on what you did>",
    "skills_used": ["<registry id of each skill you actually invoked>"],
    "files_touched": ["<repo-relative path>"],
    "evidence": "<the command you ran and its real output, or why none applies>",
}


def render_brief(plan, step):
    """Return the full subagent prompt for one assigned step."""
    if not step.get("agent"):
        raise BriefError(
            "step %s is not assigned yet — run plan_task.py --assign %s first"
            % (step.get("id"), plan.get("task_id")))

    if step.get("skills"):
        skills_block = "\n".join("  - %s" % s for s in step["skills"])
        skills_note = (
            "Start from this shortlist — it is your role's declared set, not a\n"
            "limit. Any library skill remains invocable. Record what you actually\n"
            "invoked in `skills_used`; an empty list is a valid answer if you\n"
            "genuinely used none.")
    else:
        skills_block = "  (no role skills declared — this step routed to generalist)"
        skills_note = (
            "No shortlist applies. Match a skill yourself if one fits, and record\n"
            "it in `skills_used`.")

    task_id = plan.get("task_id", "") or "unknown"
    trace_id = obs_emit.trace_id_for(task_id)
    span_id = obs_emit.span_id_for(task_id, "brief|" + step["id"])

    return BRIEF_TEMPLATE % {
        "task_id": plan.get("task_id", ""),
        "step_id": step["id"],
        "task": plan.get("task", ""),
        "goal": step.get("goal", ""),
        "role": step["agent"],
        "model": step.get("model") or "session",
        "skills_block": skills_block,
        "skills_note": skills_note,
        "schema": json.dumps(RETURN_SCHEMA, indent=2),
        "traceparent": "00-%s-%s-01" % (trace_id, span_id),
        "run_id": plan.get("task_id", ""),
    }


BRIEF_TEMPLATE = """You are working one step of a decomposed task, as the **%(role)s** role.

  task_id : %(task_id)s
  step_id : %(step_id)s

  # traceparent/run_id are a best-effort, dispatch-time correlation
  # identifier (deterministic from task_id, per the observability layer's
  # sha256 ID scheme) for external tools (tickets, logs) — they are not a
  # guarantee that this trace_id will match every event this dispatch's
  # hooks later emit, since those emit with session_id once one becomes
  # available, and session_id outranks task_id in the trace_id derivation.
  traceparent : %(traceparent)s
  run_id      : %(run_id)s

PARENT TASK (context only — do not do all of it)
%(task)s

YOUR STEP — this, and only this
%(goal)s

SKILLS DECLARED FOR YOUR ROLE
%(skills_block)s

%(skills_note)s

HOW YOU WILL BE ASSESSED
Your work is judged on objective evidence, not on your own description of it:
tests passed and failed, tool errors, commits landed, reverts, and follow-up fix
commits within 24 hours. Run the tests. Capture the real output. Never summarize
a result you did not observe, and never report a command's outcome as an exit
code alone.

RULES THAT APPLY TO EVERY STEP
- Grammar is a correctness requirement, not a nit. Proofread everything you
  emit, and especially any prose the software generates for an end user. Watch
  a/an against the spoken sound of the next word, including numbers ("an 8.1",
  "a 32.2"); subject-verb agreement; its/it's; consistent tense; no double
  spaces.
- Evidence before assertions. If you claim something passes, show the output.
- Stay inside your step. If you find work that belongs to another step, report
  it in `summary` rather than doing it.

YOUR RETURN VALUE
Your final message must be exactly this JSON object and nothing else — no
prose before or after it. It is read by a tool, not by a person.

```json
%(schema)s
```

Set `ok` to true only if the goal was met and you verified it. A return without
an explicit `ok: true` is recorded as a failure, so do not omit the field to
signal uncertainty — set it to false and explain in `summary`.
"""


# --- ASSIGN ------------------------------------------------------------------
def assign(plan, roles_dir):
    """Re-route every open step independently and re-render its brief.

    Closed steps (``done``/``failed``) are left untouched — the same
    idempotency contract the original ``assign()`` had.
    """
    roles = route_role.load_roles(roles_dir)
    for step in plan.get("steps", []):
        if step.get("status") in ("done", "failed"):
            continue
        r = route_role.route(step.get("goal", ""), roles)
        step["agent"] = r["role"]
        step["agent_score"] = r["score"]
        step["skills"] = list(r["skills"])
        step["model"] = model_for(step.get("goal", ""))
        step["brief"] = render_brief(plan, step)
    return plan


# --- persistence -------------------------------------------------------------
def _path(base_dir, task_id):
    m = TASK_ID_DATE.match(task_id or "")
    if not m:
        raise WorkOrderError(
            "task_id %r does not carry an embedded wo-YYYYMMDD- date" % task_id)
    d = m.group(1)
    day = "%s-%s-%s" % (d[0:4], d[4:6], d[6:8])
    return pathlib.Path(base_dir) / day / (task_id + ".json")


def save(base_dir, plan):
    p = _path(base_dir, plan["task_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(plan, indent=1, sort_keys=True) + "\n")
    tmp.replace(p)


def load(base_dir, task_id):
    p = _path(base_dir, task_id)
    if not p.is_file():
        raise WorkOrderError("no plan at %s" % p)
    try:
        plan = json.loads(p.read_text())
    except Exception as exc:
        raise WorkOrderError("plan %s is not valid JSON: %s" % (p, exc))
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise WorkOrderError(
            "plan %s has schema %r, expected %d — this tool does not "
            "migrate plans" % (p, (plan or {}).get("schema"), SCHEMA))
    return plan


# --- CLI ---------------------------------------------------------------------
def _default_state_dir():
    return str(pathlib.Path.home() / ".claude" / "plans")


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
    m.add_argument("--new", metavar="TASK", help="create a plan from a task")
    m.add_argument("--from-plan", metavar="DOC", help="create one step per '### Task N:' heading")
    m.add_argument("--assign", metavar="TASK_ID", help="re-route every open step")
    m.add_argument("--show", metavar="TASK_ID", help="print a plan")
    p.add_argument("--task", help="the task text (required with --from-plan)")
    p.add_argument("--reasoning", default="",
                   help="supervisor's routing rationale, recorded verbatim on the plan")
    p.add_argument("--budget-tokens", type=int, default=None, dest="budget_tokens",
                   help="token budget applied to every step created by this call")
    p.add_argument("--worktree", action="store_true",
                   help="mark every step created by this call as needing an isolated worktree")
    p.add_argument("--state-dir", default=_default_state_dir())
    p.add_argument("--roles-dir", default=str(home / "agents" / "roles"))
    return p


def main(argv=None):
    a = _build_parser().parse_args(argv)
    state, roles_dir = a.state_dir, a.roles_dir

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
            plan = create(a.task, "plan", a.from_plan, project, branch, roles_dir,
                          goals=goals, reasoning=a.reasoning,
                          budget_tokens=a.budget_tokens, worktree=a.worktree)
        else:
            plan = create(a.new, "direct", None, project, branch, roles_dir,
                          reasoning=a.reasoning, budget_tokens=a.budget_tokens,
                          worktree=a.worktree)
        save(state, plan)
        print("created plan %s" % plan["task_id"])
        for step in plan["steps"]:
            print("  %s  %-14s %-8s %s" % (step["id"], step["agent"],
                                           step["model"], step["goal"]))
        return 0

    try:
        if a.assign:
            plan = load(state, a.assign)
            assign(plan, roles_dir)
            save(state, plan)
            print("assigned %d step(s) in %s" % (len(plan["steps"]), plan["task_id"]))
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
