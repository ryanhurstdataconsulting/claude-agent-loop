#!/usr/bin/env python3
"""Render a dispatchable subagent brief for one part of a work order.

This is what replaces the ANNOUNCE string contract. The brief carries the
identifiers the agent must echo back and the return schema it must satisfy, so
the agent cannot produce a valid result without also producing its own
attribution. Nothing depends on the agent remembering a protocol.

  make_brief.py <plan-id> <part-id>          # brief to stdout, ready to dispatch

Exits non-zero with a stated reason on any failure — this tool is invoked
deliberately, not from a hook, so it does not fail open. Stdlib only.
"""
import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_task  # noqa: E402

RETURN_SCHEMA = {
    "plan_id": "<echo the plan id exactly>",
    "part_id": "<echo the part id exactly>",
    "ok": "true only if the part's goal was met and verified; false otherwise",
    "summary": "<one or two sentences on what you did>",
    "skills_used": ["<registry id of each skill you actually invoked>"],
    "files_touched": ["<repo-relative path>"],
    "evidence": "<the command you ran and its real output, or why none applies>",
}


class BriefError(Exception):
    """The part is not in a state that can be briefed."""


def _part(wo, part_id):
    for p in wo.get("parts", []):
        if p.get("part_id") == part_id:
            return p
    raise KeyError("no part %r in work order %s" % (part_id, wo.get("plan_id")))


def render(wo, part_id):
    """Return the full subagent prompt for one assigned part."""
    part = _part(wo, part_id)
    if not part.get("role"):
        raise BriefError(
            "part %s is not assigned yet — run plan_task.py --assign %s first"
            % (part_id, wo.get("plan_id")))

    if part.get("skills"):
        skills_block = "\n".join("  - %s" % s for s in part["skills"])
        skills_note = (
            "Start from this shortlist — it is your role's declared set, not a\n"
            "limit. Any library skill remains invocable. Record what you actually\n"
            "invoked in `skills_used`; an empty list is a valid answer if you\n"
            "genuinely used none.")
    else:
        skills_block = "  (no role skills declared — this part routed to generalist)"
        skills_note = (
            "No shortlist applies. Match a skill yourself if one fits, and record\n"
            "it in `skills_used`.")

    return BRIEF_TEMPLATE % {
        "plan_id": wo.get("plan_id", ""),
        "part_id": part["part_id"],
        "task": wo.get("task", ""),
        "goal": part.get("goal", ""),
        "role": part["role"],
        "model": part.get("model") or "session",
        "skills_block": skills_block,
        "skills_note": skills_note,
        "schema": json.dumps(RETURN_SCHEMA, indent=2),
    }


BRIEF_TEMPLATE = """You are working one part of a decomposed task, as the **%(role)s** role.

  plan_id : %(plan_id)s
  part_id : %(part_id)s

PARENT TASK (context only — do not do all of it)
%(task)s

YOUR PART — this, and only this
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

RULES THAT APPLY TO EVERY PART
- Grammar is a correctness requirement, not a nit. Proofread everything you
  emit, and especially any prose the software generates for an end user. Watch
  a/an against the spoken sound of the next word, including numbers ("an 8.1",
  "a 32.2"); subject-verb agreement; its/it's; consistent tense; no double
  spaces.
- Evidence before assertions. If you claim something passes, show the output.
- Stay inside your part. If you find work that belongs to another part, report
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


def main(argv=None):
    home = pathlib.Path.home() / ".claude"
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("plan_id")
    p.add_argument("part_id")
    p.add_argument("--state-dir",
                   default=str(home / "metrics" / "state" / "workorders"))
    a = p.parse_args(argv)
    try:
        print(render(plan_task.load(a.state_dir, a.plan_id), a.part_id))
    except (plan_task.WorkOrderError, BriefError, KeyError) as exc:
        sys.stderr.write("%s\n" % exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
