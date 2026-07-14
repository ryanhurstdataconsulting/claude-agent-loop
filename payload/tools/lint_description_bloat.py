#!/usr/bin/env python3
"""Lint SKILL.md and CATALOG.md descriptions for token bloat (soft, non-blocking)."""
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lint_roles import parse_frontmatter  # noqa: E402

MAX_DESCRIPTION_WORDS = 100
MAX_CATALOG_BULLET_WORDS = 40
CATALOG_BULLET = re.compile(r"^-\s+(?:★\s+)?\*\*`([^`]+)`\*\*\s+—\s+(.*\S)\s*$")


def _description_text(data):
    val = data.get("description")
    if isinstance(val, list):
        return " ".join(val)
    if isinstance(val, str):
        return val
    return ""


def lint(root):
    errs = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        name = skill_md.parent.name
        data, err = parse_frontmatter(skill_md.read_text())
        if err:
            continue
        desc = _description_text(data).strip()
        if not desc:
            continue
        n = len(desc.split())
        if n > MAX_DESCRIPTION_WORDS:
            errs.append(
                f"{name}: description is {n} words (budget {MAX_DESCRIPTION_WORDS}) "
                f"— consider compress-technical-prose"
            )
    catalog = root / "CATALOG.md"
    if catalog.is_file():
        for line in catalog.read_text().splitlines():
            m = CATALOG_BULLET.match(line)
            if not m:
                continue
            name, desc = m.groups()
            n = len(desc.split())
            if n > MAX_CATALOG_BULLET_WORDS:
                errs.append(
                    f"{name}: CATALOG.md bullet is {n} words "
                    f"(budget {MAX_CATALOG_BULLET_WORDS}) — consider compress-technical-prose"
                )
    return errs


def main():
    root = (
        pathlib.Path(sys.argv[1])
        if len(sys.argv) > 1
        else pathlib.Path.home() / ".claude" / "skills"
    )
    errs = lint(root)
    for e in errs:
        print(f"LINT: {e}")
    print(f"lint_description_bloat: {'FAIL' if errs else 'OK'} ({len(errs)} warning(s))")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
