#!/usr/bin/env python3
"""Route a task to a role agent — the deterministic HOOK -> AGENT hop.

Scores the task text against every role's ``routes:`` phrases (agents/roles/
*.md frontmatter) and prints the winning role with its declared skills and
MCPs. Scoring is plain keyword arithmetic, not model judgment, so the same
task always routes the same way:

  * each route line splits on "·" into phrases
  * a multi-word phrase found in the task scores 2 (more specific)
  * a single word found on a word boundary scores 1
  * highest total wins; below MIN_SCORE (2) the router returns ``generalist``
    and says so — a low-confidence match is not silently guessed

Usage:
  python3 route_role.py [--roles-dir DIR] [--json] "<task text>"

Human output (default) is the ANNOUNCE line the loop prints; --json returns
{role, score, matched, skills, mcps, reason} for programmatic use. Exit 0.
"""
import argparse
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lint_roles import parse_frontmatter  # noqa: E402  (same-dir tool import)

MIN_SCORE = 2


def normalize(text):
    """Lowercase and treat hyphen/underscore/slash as spaces, so "threat-model",
    "threat model", and "threat_model" all match the same route phrase."""
    return re.sub(r"\s+", " ", re.sub(r"[-_/]", " ", (text or "").lower())).strip()


def load_roles(roles_dir):
    roles = []
    for f in sorted(pathlib.Path(roles_dir).glob("*.md")):
        try:
            data, err = parse_frontmatter(f.read_text())
        except Exception:
            continue
        if err or not data.get("role"):
            continue  # tolerate malformed files — the linter reports them
        roles.append(data)
    return roles


def phrase_hits(task_lc, phrase):
    """Return the score contribution of one route phrase against the task."""
    p = normalize(phrase)
    if not p:
        return 0
    # Optional trailing "s" tolerates simple plurals ("flaky test" ~ "flaky tests").
    if re.search(r"(?<![a-z0-9])%ss?(?![a-z0-9])" % re.escape(p), task_lc):
        return 2 if " " in p else 1
    return 0


def route(task, roles):
    task_lc = normalize(task)
    best = {"role": "generalist", "score": 0, "matched": [], "skills": [],
            "mcps": [], "reason": "no route phrase reached the confidence floor"}
    if not task_lc.strip():
        return best
    for r in roles:
        score, matched = 0, []
        for line in r.get("routes", []) or []:
            for phrase in line.split("·"):
                h = phrase_hits(task_lc, phrase)
                if h:
                    score += h
                    matched.append(phrase.strip())
        if score > best["score"]:
            best = {"role": r["role"], "score": score, "matched": matched,
                    "skills": list(r.get("skills", []) or []),
                    "mcps": list(r.get("mcps", []) or []),
                    "reason": "matched: " + ", ".join(matched)}
    if best["score"] < MIN_SCORE:
        return {"role": "generalist", "score": best["score"], "matched": [],
                "skills": [], "mcps": [],
                "reason": "no route phrase reached the confidence floor"}
    return best


def main(argv=None):
    home = pathlib.Path.home() / ".claude"
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("task", nargs="*", help="the task text to route")
    p.add_argument("--roles-dir", default=str(home / "agents" / "roles"))
    p.add_argument("--json", action="store_true", dest="as_json")
    a = p.parse_args(argv)
    result = route(" ".join(a.task), load_roles(a.roles_dir))
    if a.as_json:
        print(json.dumps(result, sort_keys=True))
    elif result["role"] == "generalist":
        print("Role — generalist (%s)" % result["reason"])
    else:
        print("Role — %s (score %d: %s) · skills: %s · mcps: %s"
              % (result["role"], result["score"], ", ".join(result["matched"]),
                 ", ".join(result["skills"]) or "-",
                 ", ".join(result["mcps"]) or "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
