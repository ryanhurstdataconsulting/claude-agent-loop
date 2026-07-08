#!/usr/bin/env python3
"""Lint role-agent files: frontmatter shape, skill existence, MCP bijection.

Role agents live one per file in agents/roles/<role>.md with YAML-style
frontmatter carrying BOTH the harness agent keys (name, description) and the
router keys (role, routes, skills, mcps). This linter enforces the deterministic
HOOK -> AGENT -> SKILL -> TOOL contract at its AGENT layer:

  * frontmatter parses, and name == role == filename stem
  * description is non-empty (the harness matches on it)
  * routes: has at least one entry (the router scores on them)
  * every skills: entry exists as <skills-dir>/<name>/SKILL.md (no dead edges)
  * every mcps: entry appears in REGISTRY.md as an mcp-category row
  * no duplicate skills within a role

Usage:
  python3 lint_roles.py [roles_dir] [--skills-dir DIR] [--registry FILE]

Defaults target a live install (~/.claude/...); CI passes the payload paths.
Exit 0 clean, 1 with lint errors — same contract as lint_registry.py.
"""
import argparse
import pathlib
import re
import sys

ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$")
LIST_ITEM = re.compile(r"^\s*-\s+(.*\S)\s*$")
KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$")


def parse_frontmatter(text):
    """Parse the controlled key/list frontmatter. Returns (dict, error|None)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "missing frontmatter opening '---'"
    data, i, cur = {}, 1, None
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            return data, None
        m = KEY.match(line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val in ("", "|", ">"):
                data[key] = []
                cur = key
            elif val == "[]":
                data[key] = []
                cur = None
            else:
                data[key] = val
                cur = None
        else:
            li = LIST_ITEM.match(line)
            if li and cur is not None and isinstance(data.get(cur), list):
                data[cur].append(li.group(1))
            elif line.strip():
                return data, "unparseable frontmatter line: %r" % line.strip()
        i += 1
    return data, "missing frontmatter closing '---'"


def registry_mcps(registry_path):
    """Names of mcp-category rows in a registry index (empty set if unreadable)."""
    names = set()
    try:
        for line in registry_path.read_text().splitlines():
            m = ROW.match(line)
            if m and m.group(2).strip() == "mcp":
                names.add(m.group(1).strip())
    except Exception:
        pass
    return names


def lint(roles_dir, skills_dir, registry_path):
    errs = []
    role_files = sorted(roles_dir.glob("*.md"))
    if not role_files:
        return ["no role files found in %s" % roles_dir]
    known_mcps = registry_mcps(registry_path)
    for f in role_files:
        data, perr = parse_frontmatter(f.read_text())
        tag = f.name
        if perr:
            errs.append("%s: %s" % (tag, perr))
            continue
        stem = f.stem
        for key in ("name", "role"):
            if data.get(key) != stem:
                errs.append("%s: %s %r does not match filename stem %r"
                            % (tag, key, data.get(key), stem))
        if not str(data.get("description", "")).strip():
            errs.append("%s: empty description" % tag)
        routes = data.get("routes")
        if not isinstance(routes, list) or not routes:
            errs.append("%s: routes must list at least one trigger phrase" % tag)
        skills = data.get("skills")
        if not isinstance(skills, list) or not skills:
            errs.append("%s: skills must list at least one library skill" % tag)
        else:
            seen = set()
            for s in skills:
                if s in seen:
                    errs.append("%s: duplicate skill %r" % (tag, s))
                seen.add(s)
                if not (skills_dir / s / "SKILL.md").is_file():
                    errs.append("%s: skill %r not found at %s/%s/SKILL.md"
                                % (tag, s, skills_dir, s))
        mcps = data.get("mcps", [])
        if isinstance(mcps, list):
            for m in mcps:
                if m not in known_mcps:
                    errs.append("%s: mcp %r has no mcp row in %s"
                                % (tag, m, registry_path))
        else:
            errs.append("%s: mcps must be a list (use [] for none)" % tag)
    return errs


def main(argv=None):
    home = pathlib.Path.home() / ".claude"
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("roles_dir", nargs="?", default=str(home / "agents" / "roles"))
    p.add_argument("--skills-dir", default=str(home / "skills"))
    p.add_argument("--registry", default=str(home / "registry" / "REGISTRY.md"))
    a = p.parse_args(argv)
    errs = lint(pathlib.Path(a.roles_dir), pathlib.Path(a.skills_dir),
                pathlib.Path(a.registry))
    for e in errs:
        print("LINT: %s" % e)
    print("lint_roles: %s (%d error(s))" % ("FAIL" if errs else "OK", len(errs)))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
