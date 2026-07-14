# Ponytail/Caveman Skill Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the useful structural ideas from `ponytail` (a code-minimalism decision ladder) and `caveman` (non-conversational text compression) into claude-agent-loop's own skill library as two new `SKILL.md` files plus a paired lint tool, with zero new runtime/hook/MCP surface.

**Architecture:** Two plain-markdown skills (`payload/skills/yagni-ladder/`, `payload/skills/compress-technical-prose/`) discovered through the existing `CATALOG.md` browse path, plus one soft-lint Python tool (`payload/tools/lint_description_bloat.py`) that checks `SKILL.md` frontmatter descriptions and `CATALOG.md` bullets against word budgets, structured identically to the existing `lint_registry.py`/`test_lint_registry.py` pair.

**Tech Stack:** Python 3 standard library only (`pathlib`, `re`, `unittest`), reusing `payload/tools/lint_roles.py`'s existing `parse_frontmatter()` for frontmatter parsing. No new dependencies.

## Global Constraints

- `MAX_DESCRIPTION_WORDS = 100` — soft budget for any `payload/skills/<name>/SKILL.md` frontmatter `description:` field.
- `MAX_CATALOG_BULLET_WORDS = 40` — soft budget for any `payload/skills/CATALOG.md` bullet line.
- No new runtime, hook, or MCP server of any kind.
- No changes to `payload/registry/REGISTRY.md` — discovery for both new skills goes entirely through `CATALOG.md`.
- No slash commands, no subagents.
- No change to how the agent generates conversational replies, commit messages, or any client-facing prose — the machine-global grammar mandate is unaffected and unmodified.
- Both new skills are added under the existing `## Core framework skills` category in `CATALOG.md`.
- The `CATALOG.md` header line changes from `**168 skills across 34 categories.**` to `**170 skills across 34 categories.**` — two new skills, no new category.
- `compress-technical-prose`'s `SKILL.md` body must state, near-verbatim, that it never compresses conversational replies, commit messages, PR bodies, or any human-facing prose into fragments — this is a hard boundary, not a suggestion.
- Full existing test suite: `python3 -m unittest discover -s payload/tools/tests -p "test_*.py"`, currently 269 tests, all passing. After this work it must show 270+ passing with zero regressions (this plan's new test file adds test methods to that count; folded into whichever task's commit runs last carries the "270+" verification).
- Commits use the three-section `(1) Task & Change / (2) Tests created or modified / (3) Test results — evidence` body. Stage explicitly (`git add <paths>`); never `git add -A`.
- Branch: `feat/ponytail-caveman-port` (already created, spec committed as `9595ea0`).

---

### Task 1: `lint_description_bloat.py` lint tool (TDD)

**Files:**
- Create: `payload/tools/tests/test_lint_description_bloat.py`
- Create: `payload/tools/lint_description_bloat.py`

**Interfaces:**
- Consumes: `payload/tools/lint_roles.py`'s existing `parse_frontmatter(text: str) -> tuple[dict, str | None]` (imported via `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` then `from lint_roles import parse_frontmatter`, exactly matching how sibling tools in `payload/tools/` import each other). `parse_frontmatter` returns `(data, None)` on success — where `data` is a dict whose `"description"` key is either a plain `str` or a `list[str]` (YAML-fold dash-continuation) — or `(data, "error message")` on an unparseable frontmatter line (e.g. `description: >` followed by non-dash-prefixed prose continuation lines).
- Produces: module-level constants `MAX_DESCRIPTION_WORDS = 100` and `MAX_CATALOG_BULLET_WORDS = 40` (used verbatim by later tasks' verification steps); function `lint(root: pathlib.Path) -> list[str]`; function `main() -> int`. CLI invocation: `python3 payload/tools/lint_description_bloat.py [root]` — `root` defaults to `pathlib.Path.home() / ".claude" / "skills"` when omitted, and accepts an explicit path (e.g. `payload/skills`) as `sys.argv[1]` for dogfooding against the repo checkout itself.

- [ ] **Step 1: Write the failing test file**

Create `payload/tools/tests/test_lint_description_bloat.py`:

```python
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import lint_description_bloat as ldb

SHORT_DESC = "Use when doing X — short and to the point."
LONG_DESC = " ".join(["word"] * 101)
LONG_BULLET_DESC = " ".join(["word"] * 41)
SHORT_BULLET_DESC = "short bullet description"


class TestLintDescriptionBloat(unittest.TestCase):
    def _ws(self, skills):
        """skills: dict of name -> SKILL.md text. Returns root dir."""
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = pathlib.Path(td.name)
        for name, text in skills.items():
            d = root / name
            d.mkdir()
            (d / "SKILL.md").write_text(text)
        return root

    def _skill(self, name, description):
        return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n"

    def test_short_description_passes(self):
        root = self._ws({"alpha": self._skill("alpha", SHORT_DESC)})
        self.assertEqual(ldb.lint(root), [])

    def test_long_description_flagged(self):
        root = self._ws({"alpha": self._skill("alpha", LONG_DESC)})
        errs = ldb.lint(root)
        self.assertTrue(any("alpha" in e and "101 words" in e for e in errs))

    def test_folded_list_description_counted(self):
        text = (
            "---\nname: alpha\ndescription:\n"
            + "\n".join(f"  - {w}" for w in ["word"] * 101)
            + "\n---\n\n# alpha\n"
        )
        root = self._ws({"alpha": text})
        errs = ldb.lint(root)
        self.assertTrue(any("alpha" in e and "101 words" in e for e in errs))

    def test_unparseable_frontmatter_skipped_not_crashed(self):
        text = (
            "---\nname: alpha\ndescription: >\n"
            "  This is prose that continues onto\n"
            "  a second indented line without dashes.\n"
            "---\n\n# alpha\n"
        )
        root = self._ws({"alpha": text})
        self.assertEqual(ldb.lint(root), [])

    def test_missing_description_skipped(self):
        text = "---\nname: alpha\n---\n\n# alpha\n"
        root = self._ws({"alpha": text})
        self.assertEqual(ldb.lint(root), [])

    def test_catalog_short_bullet_passes(self):
        root = self._ws({})
        (root / "CATALOG.md").write_text(
            f"## Core framework skills\n\n- **`alpha`** — {SHORT_BULLET_DESC}\n"
        )
        self.assertEqual(ldb.lint(root), [])

    def test_catalog_long_bullet_flagged(self):
        root = self._ws({})
        (root / "CATALOG.md").write_text(
            f"## Core framework skills\n\n- **`alpha`** — {LONG_BULLET_DESC}\n"
        )
        errs = ldb.lint(root)
        self.assertTrue(any("alpha" in e and "41 words" in e for e in errs))

    def test_catalog_star_prefixed_bullet_parsed(self):
        root = self._ws({})
        (root / "CATALOG.md").write_text(
            f"## PM\n\n- ★ **`write-a-prd`** — {LONG_BULLET_DESC}\n"
        )
        errs = ldb.lint(root)
        self.assertTrue(any("write-a-prd" in e and "41 words" in e for e in errs))

    def test_catalog_non_bullet_lines_ignored(self):
        root = self._ws({})
        (root / "CATALOG.md").write_text(
            "# Skill catalog\n\n**170 skills across 34 categories.**\n\n"
            "## Core framework skills\n\n"
        )
        self.assertEqual(ldb.lint(root), [])

    def test_missing_catalog_ignored(self):
        root = self._ws({"alpha": self._skill("alpha", SHORT_DESC)})
        self.assertEqual(ldb.lint(root), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest payload.tools.tests.test_lint_description_bloat -v` (from repo root)
Expected: `ModuleNotFoundError: No module named 'lint_description_bloat'` (the module does not exist yet).

- [ ] **Step 3: Write the implementation**

Create `payload/tools/lint_description_bloat.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest payload.tools.tests.test_lint_description_bloat -v` (from repo root)
Expected: `Ran 10 tests in <N>s` / `OK`.

- [ ] **Step 5: Commit**

```bash
git add payload/tools/lint_description_bloat.py payload/tools/tests/test_lint_description_bloat.py
git commit -m "$(cat <<'EOF'
feat(tools): add lint_description_bloat — soft word-budget check for skill/catalog text

(1) Task & Change
Adds payload/tools/lint_description_bloat.py, a soft-lint tool (structured
identically to lint_registry.py) that flags SKILL.md frontmatter
descriptions over 100 words and CATALOG.md bullets over 40 words, per
docs/superpowers/specs/2026-07-14-ponytail-caveman-skill-port-design.md §4.3.
Part of the ponytail/caveman skill port (Task 1 of 4).

(2) Tests created or modified
- payload/tools/tests/test_lint_description_bloat.py (new): 10 tests covering
  short/long plain descriptions, YAML-fold list descriptions, unparseable
  frontmatter (skipped, not crashed), missing descriptions, short/long/
  star-prefixed CATALOG.md bullets, non-bullet CATALOG.md lines, and a
  missing CATALOG.md file.

(3) Test results — evidence
Ran: python3 -m unittest payload.tools.tests.test_lint_description_bloat -v
Ran 10 tests in 0.0XXs — OK
EOF
)"
```

---

### Task 2: `yagni-ladder` skill

**Files:**
- Create: `payload/skills/yagni-ladder/SKILL.md`

**Interfaces:**
- Consumes: Task 1's `payload/tools/lint_description_bloat.py` (verification only — run against this skill's own frontmatter, not imported).
- Produces: a discoverable skill named `yagni-ladder`, referenced by name in Task 4's `CATALOG.md` bullet.

- [ ] **Step 1: Write the skill file**

Create `payload/skills/yagni-ladder/SKILL.md`:

```markdown
---
name: yagni-ladder
description: Use before writing new code — a function, a dependency, a config knob, a new file, an abstraction — or when reviewing a diff/PR for unnecessary complexity. Climb a seven-rung ladder from the top and stop at the first rung that resolves the need. Triggers - "do we need this," "is there a simpler way," "yagni," adding a dependency, scaffolding a new file or module, a design proposing a new abstraction.
---

# YAGNI Ladder

## Overview

Before new code gets written, climb this ladder from the top and stop at
the first rung that resolves the need. The same ladder works in reverse as a
review lens: when reading a diff or PR, walk it top-down and flag any code
that could have stopped at a higher rung than the one it landed on.

## The ladder

1. **Does this need to exist at all?** Is it solving a problem anyone
   actually has, or can the goal be reached by removing or simplifying
   something else instead?
2. **Is it already in the codebase?** An existing function, module, or
   pattern that does this, or is trivially extended to.
3. **Does the standard library already do this?**
4. **Is there a native platform or language feature** — built-in syntax, an
   OS or runtime capability — that does this without pulling in a library?
5. **Can an already-installed dependency do this?**
6. **Can this be one line instead of a new abstraction, file, or class?**
7. **What is the smallest thing that actually works** — no speculative
   generality, no unused parameters, no "just in case" flags?

Stop at the first rung that resolves the need. Reaching rung 7 is not a
failure — it means the first six rungs were checked and none applied.

## Never-skip carve-out

Validation, security, and accessibility logic must never be shortcut to a
lower rung just because it produces less code. Correctness and safety in
those areas outweigh minimalism; do not use this ladder to justify skipping
input validation, an authorization check, or an accessibility affordance.

## Relationship to existing guidance

This skill gives the "don't add features, refactor, or introduce
abstractions beyond what the task requires" instruction a concrete,
checkable procedure. It does not replace that instruction — it
operationalizes it into seven ordered questions an agent (or reviewer) can
actually run.

## When to use this

- Before adding a new dependency
- Before scaffolding a new file, module, or class
- Before introducing a new abstraction layer
- Reviewing a diff or PR for unnecessary complexity
- Any time the question "do we need this?" or "is there a simpler way?"
  comes up
```

- [ ] **Step 2: Verify the frontmatter description stays under budget**

Run: `python3 payload/tools/lint_description_bloat.py payload/skills` (from repo root)
Expected: output does not contain a `LINT: yagni-ladder:` line (the description is 71 words, under the 100-word budget; other pre-existing skills' descriptions are not this task's concern).

- [ ] **Step 3: Commit**

```bash
git add payload/skills/yagni-ladder/SKILL.md
git commit -m "$(cat <<'EOF'
feat(skills): add yagni-ladder skill

(1) Task & Change
Adds payload/skills/yagni-ladder/SKILL.md, an original-prose port of
ponytail's seven-rung code-minimalism decision ladder, per
docs/superpowers/specs/2026-07-14-ponytail-caveman-skill-port-design.md §4.1.
Part of the ponytail/caveman skill port (Task 2 of 4).

(2) Tests created or modified
No executable test — this is a documentation-only SKILL.md addition.
Verified via payload/tools/lint_description_bloat.py (Task 1), confirming
the frontmatter description stays under the 100-word soft budget.

(3) Test results — evidence
Ran: python3 payload/tools/lint_description_bloat.py payload/skills
Output contains no "LINT: yagni-ladder:" line.
EOF
)"
```

---

### Task 3: `compress-technical-prose` skill

**Files:**
- Create: `payload/skills/compress-technical-prose/SKILL.md`

**Interfaces:**
- Consumes: Task 1's `payload/tools/lint_description_bloat.py` (verification only, and referenced by name inside this skill's body as the tool to run before applying Technique A by hand).
- Produces: a discoverable skill named `compress-technical-prose`, referenced by name in Task 4's `CATALOG.md` bullet.

- [ ] **Step 1: Write the skill file**

Create `payload/skills/compress-technical-prose/SKILL.md`:

```markdown
---
name: compress-technical-prose
description: Use when a SKILL.md frontmatter description, a CATALOG.md bullet, or a tool docstring is too long, or when asked to trim, condense, or reduce the token cost of a specific technical document. Two techniques - compress tool/skill descriptions without losing meaning, and condense one named long file on request. Never compresses conversational replies or human-facing prose into fragments. Triggers - "this tool description is too long," "trim this doc," "condense this file," reviewing CATALOG.md or SKILL.md descriptions for bloat.
---

# Compress Technical Prose

## Overview

Reduce token bloat in two specific, non-conversational surfaces without ever
touching the grammatical completeness of prose written for a human reader.

## Technique A — tool/skill description compression

When authoring or reviewing a `SKILL.md` frontmatter `description:` field, a
`CATALOG.md` bullet, or a tool docstring — text that loads into context on
every session regardless of whether the skill fires — apply this checklist:

- Cut redundant qualifiers.
- Merge overlapping trigger phrases into one clause.
- Replace multi-clause run-on sentences with a single precise sentence.
- Drop examples that don't add disambiguating information.

The description must remain grammatically complete and unambiguous. This is
an authoring aid applied deliberately when writing or reviewing a
description — never a middleware that rewrites text automatically at
runtime.

Run `payload/tools/lint_description_bloat.py` to find descriptions and
CATALOG.md bullets over budget before applying this technique by hand.

## Technique B — on-request file compression

An explicit, user-invoked pass over one long technical file (a verbose
README, a design doc) that condenses it: preserve every fact and every full
sentence, cut only redundancy and restatement. Always invoked on request for
a named file — never applied automatically to conversational output.

## Hard boundary

This skill never compresses conversational replies, commit messages, PR
bodies, or any prose generated for a human reader into fragments or
shorthand. That behavior is excluded because it conflicts with the
machine-global grammar mandate: every reply, commit message, and PR body
stays in complete, grammatically correct sentences.

## When to use this

- "This tool description is too long"
- "Trim this doc"
- "Reduce the token cost of this skill description"
- "Condense this file"
- Reviewing `CATALOG.md` or `SKILL.md` descriptions for bloat
```

- [ ] **Step 2: Verify the frontmatter description stays under budget**

Run: `python3 payload/tools/lint_description_bloat.py payload/skills` (from repo root)
Expected: output does not contain a `LINT: compress-technical-prose:` line (the description is 79 words, under the 100-word budget).

- [ ] **Step 3: Commit**

```bash
git add payload/skills/compress-technical-prose/SKILL.md
git commit -m "$(cat <<'EOF'
feat(skills): add compress-technical-prose skill

(1) Task & Change
Adds payload/skills/compress-technical-prose/SKILL.md, an original-prose
port of caveman's two non-conversational compression techniques (tool/skill
description compression, on-request file compression), with an explicit
hard boundary against compressing conversational or client-facing prose,
per docs/superpowers/specs/2026-07-14-ponytail-caveman-skill-port-design.md
§4.2. Part of the ponytail/caveman skill port (Task 3 of 4).

(2) Tests created or modified
No executable test — this is a documentation-only SKILL.md addition.
Verified via payload/tools/lint_description_bloat.py (Task 1), confirming
the frontmatter description stays under the 100-word soft budget.

(3) Test results — evidence
Ran: python3 payload/tools/lint_description_bloat.py payload/skills
Output contains no "LINT: compress-technical-prose:" line.
EOF
)"
```

---

### Task 4: `CATALOG.md` update, dogfood lint, full suite run

**Files:**
- Modify: `payload/skills/CATALOG.md` (header line and the "Core framework skills" section)

**Interfaces:**
- Consumes: Task 1's `lint_description_bloat.py` (final dogfood run against the whole `payload/skills` tree); the exact skill names `yagni-ladder` and `compress-technical-prose` from Tasks 2 and 3.
- Produces: nothing consumed by a later task — this is the plan's terminal task.

- [ ] **Step 1: Update the header line**

In `payload/skills/CATALOG.md`, change:

```
**168 skills across 34 categories.**
```

to:

```
**170 skills across 34 categories.**
```

- [ ] **Step 2: Add the two new bullets under "Core framework skills"**

In `payload/skills/CATALOG.md`, in the `## Core framework skills` section, immediately after the existing `aws-local-emulation` bullet, add these two lines:

```
- **`yagni-ladder`** — Use before writing new code — a function, dependency, config knob, file, or abstraction — or when reviewing a diff for unnecessary complexity. Climb the seven-rung ladder and stop at the first rung that resolves the need.
- **`compress-technical-prose`** — Use when a SKILL.md description, a CATALOG.md bullet, or a tool docstring is too long, or when asked to trim, condense, or reduce the token cost of a specific technical document.
```

- [ ] **Step 3: Dogfood the lint tool against the whole updated skills tree**

Run: `python3 payload/tools/lint_description_bloat.py payload/skills` (from repo root)
Expected: exit code 0; no `LINT: yagni-ladder:` or `LINT: compress-technical-prose:` line in the output (both the two new `SKILL.md` frontmatter descriptions and the two new `CATALOG.md` bullets stay under budget — 71/79 words for the descriptions, 37/31 words for the bullets, all under their respective 100/40-word budgets). Pre-existing skills tripping the lint (if any) are out of scope for this task — record them as an observation only, do not fix them here.

- [ ] **Step 4: Run the full existing test suite**

Run: `python3 -m unittest discover -s payload/tools/tests -p "test_*.py" -v` (from repo root)
Expected: `Ran 279 tests` (269 pre-existing + 10 new from Task 1) / `OK`, zero regressions. (Stderr noise from tests that intentionally exercise secret-scrub/redaction paths is expected, not a failure — matches the pre-existing baseline behavior.)

- [ ] **Step 5: Commit**

```bash
git add payload/skills/CATALOG.md
git commit -m "$(cat <<'EOF'
docs(catalog): list yagni-ladder and compress-technical-prose, bump 168->170

(1) Task & Change
Updates payload/skills/CATALOG.md: adds bullets for the two new skills
under "Core framework skills" and bumps the header count from 168 to 170,
per docs/superpowers/specs/2026-07-14-ponytail-caveman-skill-port-design.md
§5. Completes the ponytail/caveman skill port (Task 4 of 4).

(2) Tests created or modified
No new test file — this task verifies via the Task 1 lint tool and the
full existing suite, not a new test.

(3) Test results — evidence
Ran: python3 payload/tools/lint_description_bloat.py payload/skills
Exit code 0, no LINT line for yagni-ladder or compress-technical-prose.

Ran: python3 -m unittest discover -s payload/tools/tests -p "test_*.py" -v
Ran 279 tests — OK (269 pre-existing + 10 new, zero regressions).
EOF
)"
```

---

## After all tasks: push and PR

Not a numbered task — handled by `superpowers:subagent-driven-development`'s
own terminal step (dispatch the final whole-branch code reviewer, then
invoke `superpowers:finishing-a-development-branch`, which pushes
`feat/ponytail-caveman-port` and opens a PR against `main` summarizing the
whole branch), per spec §6 steps 7–8.
