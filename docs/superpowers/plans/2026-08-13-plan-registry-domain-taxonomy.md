# REGISTRY Domain Taxonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Give every `REGISTRY.md` row a `domain` column (one of 10
VoltAgent-matching values) so the MATCH step can filter to a candidate set
before it semantically reads triggers, and teach `lint_registry.py` to
enforce it.

**Architecture:** `REGISTRY.md` gains a new third column between `category`
and `trigger`. `lint_registry.py`'s row regex and validation logic are
extended to parse and check it. `resource-loop/SKILL.md`'s MATCH step gains
one sentence of guidance to use the new column as a pre-filter. No skill,
tool, or agent file moves on disk — the taxonomy is metadata on the existing
flat index only.

**Tech Stack:** Python 3 stdlib (`re`, `pathlib`), `unittest`. Same toolchain
`lint_registry.py` already uses — no new dependency.

**Spec:** `docs/superpowers/specs/2026-08-06-agent-loop-v2-design.md`
(Phase 2 — "REGISTRY domain taxonomy")

## Grounding correction (read before Task 3)

The spec's Phase 2 paragraph says *"`route_role.py` gains a two-stage match:
domain filter first, then in-domain semantic match against the (now much
smaller) candidate set."* That doesn't fit the actual code:
`payload/tools/route_role.py` scores task text against `agents/roles/*.md`
frontmatter (a fixed set of 17 role files) — it never reads `REGISTRY.md` at
all. The registry is instead consulted by MATCH step 1 in
`payload/skills/resource-loop/SKILL.md`, which is **agent judgment carried
out in prose**, not a scored Python match (unlike the separate "Role hop"
that *does* call `route_role.py`). Domain-filtering the registry is
therefore a **documentation change to the MATCH step's instructions**, not a
`route_role.py` code change — `route_role.py` is correctly left untouched by
this plan. This mirrors the spec's own methodology (a grounding pass caught
a similar mismatch for the original Phase 1 proposal).

**Row-count note.** The spec's "populated across all 63 rows" figure was a
2026-08-06 count of the machine-tailored `~/.claude/registry/REGISTRY.md`
(which has since grown further, to 79 rows, as of this plan's writing). The
version-controlled template this plan edits —
`payload/registry/REGISTRY.md`, what a fresh machine starts from before
`environment-bootstrap` tailors it — has always had a different, smaller row
count (36 as of this plan). This plan populates domain across all 36
template rows; the machine-tailored copy's additional rows get their domain
values at the same deploy step that already tailors that file, not here.

## Global Constraints

- Domain values: exactly these 10, kebab-case, no others —
  `core-dev`, `language`, `infra`, `quality-security`, `data-ai`,
  `dev-experience`, `specialized-domains`, `business-product`,
  `meta-orchestration`, `research-analysis`.
- No row moves, no file moves — `payload/skills/` stays flat (explicit
  non-goal in the spec).
- Index row budget stays 150 (`lint_registry.py`'s `BUDGET`), unchanged by
  this phase.
- `lint_registry.py` must exit 0 against `payload/registry/` after every
  task in this plan.
- Only `payload/registry/REGISTRY.md` (the generic template) is edited — not
  the machine-tailored `~/.claude/registry/REGISTRY.md`, which is a separate,
  deliberately out-of-scope deploy-time artifact (see spec's Phase 1 note on
  deploy being "owned by the controller directly").

---

### Task 1: `lint_registry.py` — parse and validate the `domain` column

**Files:**
- Modify: `payload/tools/lint_registry.py`
- Test: `payload/tools/tests/test_lint_registry.py`

**Interfaces:**
- Consumes: nothing new — same `lint(root: pathlib.Path) -> list[str]` entry
  point, same `root / "REGISTRY.md"` / `root / "guides"` layout.
- Produces: `lint()` still returns `list[str]`; the 4-column row shape
  (`name | category | domain | trigger`) becomes what `lint()` expects. Any
  caller reading 3-column rows will now get a "malformed row" error — this is
  the deliberate breaking change Task 2 (REGISTRY.md content) exists to fix.

- [ ] **Step 1: Rewrite the test fixtures and add domain-column tests (failing)**

Replace the whole content of
`payload/tools/tests/test_lint_registry.py` with:

```python
import pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import lint_registry as lr

GOOD = ("# Registry\n"
        "| alpha | skill | dev-experience | Use for X |\n"
        "| beta | tool | meta-orchestration | Use for Y |\n")


class TestLint(unittest.TestCase):
    def _ws(self, registry_text, guide_names):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = pathlib.Path(td.name)
        (root / "guides").mkdir()
        (root / "REGISTRY.md").write_text(registry_text)
        (root / "guides" / "_TEMPLATE.md").write_text("# template")
        for n in guide_names:
            (root / "guides" / f"{n}.md").write_text(f"# Guide — {n}")
        return root

    def test_clean_registry_passes(self):
        self.assertEqual(lr.lint(self._ws(GOOD, ["alpha", "beta"])), [])

    def test_separator_and_header_rows_ignored(self):
        text = ("| name | category | domain | trigger |\n"
                 "|---|---|---|---|\n"
                 "| alpha | skill | dev-experience | X |\n")
        self.assertEqual(lr.lint(self._ws(text, ["alpha"])), [])

    def test_bad_category_flagged(self):
        errs = lr.lint(self._ws("| alpha | wizard | dev-experience | X |\n", ["alpha"]))
        self.assertTrue(any("category" in e for e in errs))

    def test_bad_domain_flagged(self):
        errs = lr.lint(self._ws("| alpha | skill | wizardry | X |\n", ["alpha"]))
        self.assertTrue(any("domain" in e and "wizardry" in e for e in errs))

    def test_empty_domain_flagged(self):
        errs = lr.lint(self._ws("| alpha | skill |  | X |\n", ["alpha"]))
        self.assertTrue(any("domain" in e for e in errs))

    def test_missing_guide_flagged(self):
        errs = lr.lint(self._ws(GOOD, ["alpha"]))
        self.assertTrue(any("beta" in e and "guide" in e for e in errs))

    def test_orphan_guide_flagged(self):
        errs = lr.lint(self._ws(GOOD, ["alpha", "beta", "gamma"]))
        self.assertTrue(any("gamma" in e for e in errs))

    def test_duplicate_names_flagged(self):
        errs = lr.lint(self._ws(
            "| alpha | skill | dev-experience | X |\n"
            "| alpha | tool | quality-security | Y |\n", ["alpha"]))
        self.assertTrue(any("duplicate" in e.lower() for e in errs))

    def test_budget_enforced(self):
        rows = "\n".join(f"| r{i} | tool | dev-experience | t |" for i in range(151))
        errs = lr.lint(self._ws(rows, [f"r{i}" for i in range(151)]))
        self.assertTrue(any("150" in e for e in errs))

    def test_missing_registry_flagged(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = pathlib.Path(td.name)
        (root / "guides").mkdir()
        errs = lr.lint(root)
        self.assertTrue(any("missing" in e for e in errs))

    def test_malformed_row_flagged(self):
        errs = lr.lint(self._ws("| only-two | cols |\n", []))
        self.assertTrue(any("malformed" in e for e in errs))

    def test_three_column_row_flagged_as_malformed(self):
        # Pre-domain-column row shape must not silently pass post-migration.
        errs = lr.lint(self._ws("| alpha | skill | X |\n", ["alpha"]))
        self.assertTrue(any("malformed" in e for e in errs))

    def test_empty_trigger_flagged(self):
        errs = lr.lint(self._ws("| alpha | skill | dev-experience |  |\n", ["alpha"]))
        self.assertTrue(any("trigger" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the suite and confirm it fails**

Run: `python3 -m pytest payload/tools/tests/test_lint_registry.py -v`
Expected: multiple FAILs — `lint_registry.py` still expects 3 columns, so
every 4-column fixture in the new tests either mismatches the row regex
(→ "malformed row", not the specific error each test asserts) or the
`domain` group doesn't exist yet (`AttributeError`/`IndexError` is not
possible here since `m.groups()` still only unpacks 3 names — this will
raise `ValueError: not enough values to unpack` in `lint()` itself). Confirm
the failure reason is exactly this mismatch, not a typo in the test file.

- [ ] **Step 3: Implement domain-column support in `lint_registry.py`**

Replace the full content of `payload/tools/lint_registry.py` with:

```python
#!/usr/bin/env python3
"""Lint the resource registry: row format, categories, domains, guide bijection, budget."""
import pathlib
import re
import sys

CATEGORIES = {"superpower", "skill", "mcp", "tool", "agent"}
DOMAINS = {
    "core-dev", "language", "infra", "quality-security", "data-ai",
    "dev-experience", "specialized-domains", "business-product",
    "meta-orchestration", "research-analysis",
}
ROW = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$"
)
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
        name, cat, domain, trigger = m.groups()
        if name == "name" and cat == "category":
            continue  # header row
        if cat not in CATEGORIES:
            errs.append(f"line {i}: bad category {cat!r} for {name!r}")
        if domain not in DOMAINS:
            errs.append(f"line {i}: bad domain {domain!r} for {name!r}")
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
```

Note the empty-domain case: with the row `| alpha | skill |  | X |`, the
regex's third group captures a single space (`[^|]+?` needs ≥1 non-pipe
char; whitespace qualifies), which is not stripped before the `domain not in
DOMAINS` check — `" " not in DOMAINS` is `True`, so it's flagged with message
`bad domain ' '`. That satisfies `test_empty_domain_flagged`'s substring
check (`"domain" in e`) without needing a separate strip/empty-check branch —
consistent with how the pre-existing category check already handles an
empty category.

- [ ] **Step 4: Run the suite and confirm it passes**

Run: `python3 -m pytest payload/tools/tests/test_lint_registry.py -v`
Expected: PASS, 13 passed.

- [ ] **Step 5: Commit**

```bash
git add payload/tools/lint_registry.py payload/tools/tests/test_lint_registry.py
git commit -m "feat(registry): lint_registry.py enforces the new domain column"
```

---

### Task 2: Add the `domain` column to `REGISTRY.md`

**Files:**
- Modify: `payload/registry/REGISTRY.md`
- Modify: `ARCHITECTURE.md:292-293` (one-line note)

**Interfaces:**
- Consumes: `DOMAINS` set from Task 1 (the 10 values below are exactly that
  set — copy verbatim, no new value gets invented here).
- Produces: a `payload/registry/REGISTRY.md` that `python3
  payload/tools/lint_registry.py payload/registry` exits 0 against.

- [ ] **Step 1: Replace `payload/registry/REGISTRY.md` in full**

```markdown
# Agent Resource Registry — compact index
<!-- Format: | name | category | domain | trigger | · one resource per line · budget 150 rows -->
<!-- domain ∈ core-dev, language, infra, quality-security, data-ai, dev-experience,
     specialized-domains, business-product, meta-orchestration, research-analysis -->
<!-- Lint after ANY edit: python3 ~/.claude/tools/lint_registry.py -->
<!-- Full guides: registry/guides/<name>.md · Proposals: registry/candidates/ -->
<!-- Plugin-provided skills (superpowers, VoltAgent catalog, …) are surfaced
     natively by the harness and are NOT re-indexed here. Run the
     environment-bootstrap skill once to tailor this registry to your machine. -->

## Superpowers (process)
| resource-loop | superpower | meta-orchestration | Start of every session: MATCH → ANNOUNCE → ROUTE → EXECUTE → SCORE → LEARN |
| token-efficiency | superpower | meta-orchestration | Long/high-volume/multi-file task or a subagent fleet — targeted reads, file-handoff, model/effort routing; never at the cost of evidence |

## Skills (domain)
| environment-bootstrap | skill | dev-experience | First run / reconfigure — inspect the machine, interview the user, and tailor this whole config |
| data-visualization | skill | data-ai | Chart selection, dashboard design, data storytelling |
| visual-hierarchy-layered-charts | skill | data-ai | Multi-series charts with importance tiers; focus/dim and "make it pop" decisions |
| explain-code | skill | dev-experience | Explaining how code works, with diagrams and analogies |
| excalidraw-diagram | skill | dev-experience | Architecture, data-flow, and onboarding diagrams as Excalidraw JSON |
| document-render | skill | dev-experience | Rendering any markdown deliverable to PDF, or a generated .pptx/.docx deck to PDF/images for QA (pandoc+weasyprint + headless-LibreOffice) |
| tauri-desktop-dev | skill | core-dev | Building/debugging a Tauri 2 desktop app or packaging a Python/FastAPI backend as a Tauri sidecar |
| skill-library | skill | meta-orchestration | Role-based skill library — 157 generic skills across 33 tech-org families (product → DB → ML/AI → UI). Browse skills/CATALOG.md, then invoke a specific skill by name |

## Agents
| sql-safety-reviewer | agent | quality-security | Dispatch before every production-database query — SAFE / NOT SAFE verdict (read-only wrapper present, no DDL/DML) |
| cloud-architect | agent | infra | AWS/Terraform/IAM provisioning or cloud-architecture assessment (Well-Architected review) |
| role-agents | agent | meta-orchestration | Serve as a company role — the router (route_role.py) picks the role agent (data-scientist, data-engineer, dba, cloud-architect, product-manager, …) whose skills/MCPs fit the task |

## MCPs
| postgres-readonly | mcp | data-ai | Live read-only SQL to a Postgres/MySQL database (localhost tunnel or direct) — fill in your host |
| playwright | mcp | quality-security | Browser automation, testing, and screenshots |
| google_workspace | mcp | business-product | Drive, Sheets, Docs, and Forms operations |

## Tools
| distill-transcripts | tool | dev-experience | Extract redacted user/assistant text from session JSONLs (~/.claude/tools/) |
| lint-registry | tool | meta-orchestration | Validate registry index ↔ guides after any registry edit |
| lint-roles | tool | meta-orchestration | Validate role-agent files after any agents/roles edit — frontmatter shape, skill existence, MCP bijection |
| route-role | tool | meta-orchestration | The deterministic task → role hop at MATCH — prints the Role — line with the role's skills and MCPs |
| plan-task | tool | meta-orchestration | DECOMPOSE/ASSIGN/BRIEF/RECORD — build a plan, route and brief each step, record each subagent's structured return |
| loop-contribute | tool | meta-orchestration | The feedback loop — gate-cleared (GENERIC-only) local resources auto-push to a contrib/* branch with an impact summary; --nudge at SessionStart |
| run-canaries | tool | quality-security | Full-coverage probe: does each project's session announce the loop? |
| check-coverage | tool | quality-security | Static check: CLAUDE.md stub + SUBAGENTS.md present across your projects |
| git-safety-preflight | tool | dev-experience | Session start / before non-trivial git ops — detect file-sync `.git` eviction, clobbered venv symlink, missing remote, unpushed commits, not-a-repo |
| machine-prose-grammar-gate | tool | quality-security | Before shipping ANY machine-generated user-facing prose — number-aware a/an, pluralization, subject-verb, its/it's |
| secret-pii-scrub-gate | tool | quality-security | Before any commit, handoff bundle, or deliverable — scan staged files for JWTs, passwords, SSH-key headers, emails, /Users/<name> paths, PII |
| env-tooling-preflight | tool | dev-experience | Session start on a Python/build project — interpreter/venv version, required-tool presence, macOS bash-3.2 portability |
| background-build-watch | tool | dev-experience | Any long-running build the agent must poll — tail a log for success/fail, notify once, no manual re-arm |
| ssh-tunnel-keepalive | tool | infra | Any remote-DB or SSH-tunnel session spanning multiple turns or >30 min — keepalive + auto-reconnect on idle drop |
| dev-server-orchestration | tool | dev-experience | "Spin it up" / "let me test" — one command brings the project's dev stack up/down with a health gate |
| audit-store | tool | quality-security | Ensure/verify/commit the repo-audit output store — a nested git repo under `~/.claude/metrics/audit`, no remote, ever |
| audit-dispatch | tool | quality-security | Nightly repo-security sweep: pick the due packages (interval elapsed AND HEAD moved), run each one, close with a digest |
| audit-run | tool | quality-security | Run one unattended repo-security audit — throwaway worktree, safety gates, commit to `audit/security-<date>`, never pushes |
| audit-digest | tool | quality-security | Severity-gated repo-audit alerts (Critical/High interrupt now) plus the batched digest and its SessionStart nudge |
| repo-audit-action | tool | quality-security | Per-change security audit in GitHub Actions — the four categories a checkout can answer, with the two it cannot stated on every run |
```

- [ ] **Step 2: Run `lint_registry.py` against the real template and confirm it's clean**

Run: `python3 payload/tools/lint_registry.py payload/registry`
Expected: `lint_registry: OK (0 error(s))`

- [ ] **Step 3: Run the full existing test suite once to catch any other reader of the 3-column shape**

Run: `python3 -m pytest payload/tools/tests/ -v -k "registry or route_role"`
Expected: all PASS. (`route_role.py` reads `agents/roles/*.md`, not
`REGISTRY.md` — this run is a confirmation of the grounding correction
above, not an expected source of failures.)

- [ ] **Step 4: Add the one-line ARCHITECTURE.md note**

In `ARCHITECTURE.md`, change:

```
- **`REGISTRY.md`** — a compact one-line-per-resource index (the hook injects
  this). Grouped into superpowers, skills, agents, MCPs, and tools.
```

to:

```
- **`REGISTRY.md`** — a compact one-line-per-resource index (the hook injects
  this). Grouped into superpowers, skills, agents, MCPs, and tools; each row
  also carries a `domain` column (one of 10 VoltAgent-matching values) that
  the MATCH step uses to narrow its candidate set before it reads triggers.
```

- [ ] **Step 5: Commit**

```bash
git add payload/registry/REGISTRY.md ARCHITECTURE.md
git commit -m "feat(registry): populate the domain column across all 36 template rows"
```

---

### Task 3: Document domain-first MATCH filtering in `resource-loop/SKILL.md`

**Files:**
- Modify: `payload/skills/resource-loop/SKILL.md:75-80`

**Interfaces:**
- Consumes: nothing code-level — this is documentation only, read by the
  agent executing MATCH, not by any tool.
- Produces: nothing another task depends on — this is the terminal task of
  this plan.

- [ ] **Step 1: Update MATCH step 1's paragraph**

Change:

```
1. **MATCH** — semantically match the task against the index. Think in task
   shapes, not keywords: "make the chart pop" matches
   visual-hierarchy-layered-charts. Consult `~/.claude/registry/TRIGGERS.md` as a
   keyword and file-glob shortcut alongside the semantic match — it is an
   accelerator, not a replacement for reading the task. Read the full guide
   (`~/.claude/registry/guides/<name>.md`) for anything you will deploy.
```

to:

```
1. **MATCH** — semantically match the task against the index. Think in task
   shapes, not keywords: "make the chart pop" matches
   visual-hierarchy-layered-charts. Each row also carries a `domain` column
   (`core-dev` · `language` · `infra` · `quality-security` · `data-ai` ·
   `dev-experience` · `specialized-domains` · `business-product` ·
   `meta-orchestration` · `research-analysis`) — narrow to the task's domain
   first, then semantically match within that smaller set. This is a
   candidate-set filter, not a hard gate: when a task genuinely spans two
   domains, both stay reachable. Consult `~/.claude/registry/TRIGGERS.md` as a
   keyword and file-glob shortcut alongside the semantic match — it is an
   accelerator, not a replacement for reading the task. Read the full guide
   (`~/.claude/registry/guides/<name>.md`) for anything you will deploy.
```

Leave the separate "Role hop" paragraph immediately below (the
`route_role.py` call) untouched — per the grounding correction above, it
matches against `agents/roles/*.md`, not `REGISTRY.md`, and is out of scope
for this phase.

- [ ] **Step 2: Confirm no other doc references the 3-column format**

Run: `grep -rn "name | category | trigger" payload/ ARCHITECTURE.md`
Expected: no matches (the only literal occurrence was in
`test_lint_registry.py`, already rewritten in Task 1).

- [ ] **Step 3: Commit**

```bash
git add payload/skills/resource-loop/SKILL.md
git commit -m "docs(registry): document domain-first MATCH filtering in resource-loop"
```

---

## Testing & rollback

Each task's commit is independently revertable via `git revert` — Task 1
(lint code), Task 2 (data), and Task 3 (docs) touch disjoint files, so a
revert of any one leaves the other two intact and correct on their own
(Task 2's content still parses fine without Task 3's doc change; reverting
Task 2 alone would break lint against the real registry, which is why Task 1
is ordered first and is independently green against its own synthetic
fixtures regardless of Task 2's content).

Final check for the whole phase:

```bash
python3 -m pytest payload/tools/tests/test_lint_registry.py -v
python3 payload/tools/lint_registry.py payload/registry
```

Expected: 13 tests passed; `lint_registry: OK (0 error(s))`.
