#!/usr/bin/env python3
"""Lint the resource registry: row format, categories, guide bijection, budget."""
import pathlib
import re
import sys

CATEGORIES = {"superpower", "skill", "mcp", "tool", "agent"}
ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$")
SEPARATOR = re.compile(r"^\|[\s\-|]+\|$")
BUDGET = 150


def lint(root):
    errs, names = [], []
    reg = root / "REGISTRY.md"
    if not reg.is_file():
        return [f"missing {reg}"]
    for i, line in enumerate(reg.read_text().splitlines(), 1):
        if not line.startswith("|") or SEPARATOR.match(line):
            continue
        m = ROW.match(line)
        if not m:
            errs.append(f"line {i}: malformed row: {line!r}")
            continue
        name, cat, trigger = m.groups()
        if name == "name" and cat == "category":
            continue  # header row
        if cat not in CATEGORIES:
            errs.append(f"line {i}: bad category {cat!r} for {name!r}")
        if not trigger.strip():
            errs.append(f"line {i}: empty trigger for {name!r}")
        names.append(name)
    for n in sorted({n for n in names if names.count(n) > 1}):
        errs.append(f"duplicate index entry: {n!r}")
    if len(names) > BUDGET:
        errs.append(f"index has {len(names)} resource lines; budget is {BUDGET}")
    guides = {p.stem for p in (root / "guides").glob("*.md")} - {"_TEMPLATE", "README"}
    for n in sorted(set(names) - guides):
        errs.append(f"{n!r}: index row has no guide (guides/{n}.md)")
    for g in sorted(guides - set(names)):
        errs.append(f"{g!r}: orphan guide with no index row")
    return errs


def main():
    root = (pathlib.Path(sys.argv[1]) if len(sys.argv) > 1
            else pathlib.Path.home() / ".claude" / "registry")
    errs = lint(root)
    for e in errs:
        print(f"LINT: {e}")
    print(f"lint_registry: {'FAIL' if errs else 'OK'} ({len(errs)} error(s))")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
