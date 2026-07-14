# Design: port ponytail and caveman into claude-agent-loop's skill library

**Date:** 2026-07-14
**Status:** Approved (conversational), pending written-spec review
**Branch:** `feat/ponytail-caveman-port`

## 1. Problem and intent

Two external repos contain disciplines worth having in claude-agent-loop's own
skill library:

- [`DietrichGebert/ponytail`](https://github.com/DietrichGebert/ponytail) (MIT)
  — a seven-rung code-minimalism decision ladder for deciding whether new code
  needs to exist at all before it gets written.
- [`JuliusBrussee/caveman`](https://github.com/juliusbrussee/caveman) (MIT) —
  a suite centered on compressing the agent's own output; most of it compresses
  conversational chat replies into terse fragments, but two ideas inside it are
  about compressing non-conversational text (MCP tool descriptions, and
  on-request file compression).

Neither repo is being installed, run, or pulled in as a plugin. The intent is
narrower: read both for their underlying ideas, then author original
claude-agent-loop skills — in claude-agent-loop's own prose and file
conventions — that carry the useful parts of each discipline forward.

## 2. Scope decision: caveman is ported for structural parts only

Ponytail is a decision-making discipline with no output-format opinion — it is
ported in full (as one new skill).

Caveman's centerpiece is a "reply-compression" mode: it rewrites the agent's
own conversational output into caveman-speak sentence fragments to save
tokens. That directly conflicts with a machine-global, standing instruction in
`~/.claude/CLAUDE.md` ("Output Quality — Grammar") that the user is a
self-described grammar stickler and that this standard applies to
**everything the agent emits**, chat replies included — complete sentences,
correct subject-verb agreement, no dropped articles. This is not a stylistic
preference call an agent should resolve unilaterally in either direction, so
it was surfaced to the user directly rather than silently ported or silently
dropped.

**Decision (user-confirmed): structural parts only.** From caveman, port:

- The idea of compressing **MCP/skill tool descriptions** — text that is
  loaded into every session's context regardless of whether the skill fires —
  for token efficiency, as an authoring checklist rather than a middleware
  that rewrites descriptions at runtime.
- The idea of an **on-request file-compression pass** for a specific long
  technical document, preserving every fact and full sentences, cutting only
  redundancy.

Explicitly **not** ported: the always-on reply-compression behavior, the
`cavecrew-*` subagents, the `curl | bash` installer that rewrites every agent
CLI's config on the machine, and the MCP middleware server. None of these fit
claude-agent-loop's plain-file, no-new-runtime conventions, and the reply
compression piece is excluded on the grammar-mandate grounds above.

## 3. Architecture decision: two skills + one lint tool

**Decision (user-confirmed):** no new runtime, no hook changes, no MCP
server. Everything is expressed as plain-markdown `SKILL.md` files plus one
Python lint tool, matching claude-agent-loop's existing idioms exactly (see
`payload/skills/*/SKILL.md` and `payload/tools/lint_*.py`).

Two alternatives were considered and rejected:

- **Always-on hook injection** (a new SessionStart/PreToolUse hook that
  auto-applies the ladder or auto-compresses descriptions) — higher blast
  radius (ships to every machine on auto-update) and changes per-session
  token cost, for a discipline that is better applied deliberately when
  authoring or reviewing, not silently on every turn.
- **Sibling plugin** (a separate installable package alongside
  claude-agent-loop) — would not achieve genuine integration into the loop's
  own skill library; the whole point of this request is for the ideas to live
  where every other claude-agent-loop skill lives and be discoverable the
  same way.

## 4. Components

### 4.1 `payload/skills/yagni-ladder/SKILL.md` (new)

Ports ponytail's ladder, rewritten in original prose (no verbatim copying).

**Purpose:** before writing new code — a function, a dependency, a config
knob, a new file, an abstraction — climb the ladder from the top and stop at
the first rung that resolves the need. Also usable in reverse, as a diff/PR
review lens for spotting unnecessary complexity that was already written.

**The ladder (top to bottom):**

1. Does this need to exist at all? (Is it solving a problem anyone actually
   has, or can the goal be reached by removing or simplifying something
   else instead?)
2. Is it already in the codebase? (An existing function, module, or pattern
   that does this, or is trivially extended to.)
3. Does the standard library already do this?
4. Is there a native platform or language feature — built-in syntax, an
   OS or runtime capability — that does this without pulling in a library?
5. Can an already-installed dependency do this?
6. Can this be one line instead of a new abstraction, file, or class?
7. What is the smallest thing that actually works — no speculative
   generality, no unused parameters, no "just in case" flags?

**Never-skip carve-out:** validation, security, and accessibility logic must
never be shortcut to a lower rung just because it produces less code.
Correctness and safety there outweigh minimalism — this carve-out is
inherited directly from ponytail and stated explicitly in the skill body so
it cannot be missed.

**Relationship to existing guidance:** this skill gives the "Don't add
features, refactor, or introduce abstractions beyond what the task requires"
line already in the base agent instructions a concrete, checkable procedure
instead of a general exhortation. It does not replace that line; it operationalizes it.

**Trigger phrases (frontmatter `description:`):** "do we need this," "is
there a simpler way," reviewing a diff or PR for unnecessary complexity,
before adding a new dependency, before scaffolding a new file or module,
"yagni," a design proposing a new abstraction.

### 4.2 `payload/skills/compress-technical-prose/SKILL.md` (new)

Ports caveman's two non-prose ideas, rewritten in original prose.

**Purpose:** reduce token bloat in two specific, non-conversational surfaces
without ever touching the grammatical completeness of prose written for a
human reader.

**Technique A — tool/skill description compression.** When authoring or
reviewing a `SKILL.md` frontmatter `description:` field, a `CATALOG.md`
bullet, or a tool docstring — text that loads into context on every session
regardless of whether it fires — apply this checklist: cut redundant
qualifiers, merge overlapping trigger phrases into one clause, replace
multi-clause run-on sentences with a single precise sentence, drop examples
that don't add disambiguating information. The description must remain
grammatically complete and unambiguous; this is an authoring aid applied
deliberately, not a middleware that rewrites text automatically at runtime.

**Technique B — on-request file compression.** An explicit, user-invoked
pass over one long technical file (a verbose README, a design doc) that
condenses it: preserve every fact and every full sentence, cut only
redundancy and restatement. Modeled on caveman's `/caveman-compress` idea,
reframed as a reviewer checklist rather than a slash command tied to
caveman's own tooling. Always invoked on request for a named file — never
applied automatically to conversational output.

**Hard boundary (must appear near-verbatim in the skill body):** this skill
never compresses conversational replies, commit messages, PR bodies, or any
prose generated for a human reader into fragments or shorthand. That
behavior is caveman's core mode and is deliberately excluded because it
conflicts with the machine-global grammar mandate (§2 above).

**Trigger phrases:** "this tool description is too long," "trim this doc,"
"reduce the token cost of this skill description," "condense this file,"
reviewing `CATALOG.md` or `SKILL.md` descriptions for bloat.

### 4.3 `payload/tools/lint_description_bloat.py` (new) + `payload/tools/tests/test_lint_description_bloat.py` (new)

A soft-lint tool structured identically to `payload/tools/lint_registry.py`:
a `lint(root)` function that returns a list of warning strings, a `main()`
that prints one `LINT: <message>` line per finding followed by a
`lint_description_bloat: FAIL/OK (N warning(s))` summary line, exiting 1 if
any findings exist and 0 otherwise — the same CLI convention every existing
`lint_*.py` tool in this repo follows.

**What it checks:**

- Every `payload/skills/<name>/SKILL.md` frontmatter `description:` field.
  Word count over `MAX_DESCRIPTION_WORDS = 100` (default, defined as a module
  constant exactly like `lint_registry.py`'s `BUDGET = 150`) is flagged as
  `"<skill>: description is N words (budget 100) — consider
  compress-technical-prose"`.
- Every `payload/skills/CATALOG.md` bullet line matching the existing
  `- **`name`** — description` format. Word count over
  `MAX_CATALOG_BULLET_WORDS = 40` is flagged the same way. (Observed current
  bullets run roughly 10–55 words with the renderer already truncating long
  ones at display time with `…`; 40 catches the ones still worth trimming at
  the source.)

Both thresholds are soft — the tool never fails CI by itself unless something
invokes it as a gate; it is a discoverable check an agent or the user runs
deliberately, the same way `lint_registry.py` is run "after ANY edit" per its
own docstring, not wired into a pre-commit hook.

**Test file** follows the pairing convention of every other `lint_*.py` /
`test_lint_*.py` pair: constructs a temporary `skills/` tree (a couple of
`SKILL.md` fixtures, one under budget and one over) plus a temporary
`CATALOG.md` fixture, and asserts `lint()` returns the expected warning
strings and `main()` returns the expected exit code.

## 5. `CATALOG.md` placement

Both new skills are added as bullets under the existing `## Core framework
skills` category (home of `resource-loop`, `token-efficiency`,
`environment-bootstrap`, etc.) — they are cross-cutting authoring/review
disciplines usable by any role, not tied to a specific domain, matching the
existing skills in that category.

The header line `**168 skills across 34 categories.**` is updated to
`**170 skills across 34 categories.**` (two new skills, no new category).

## 6. Testing and rollout plan

1. TDD for the lint tool: write `test_lint_description_bloat.py` first
   (failing, since neither the test fixtures nor `lint_description_bloat.py`
   exist yet), modeled on `test_lint_registry.py`'s fixture-directory
   pattern.
2. Implement `payload/tools/lint_description_bloat.py` until the new test
   passes.
3. Write `payload/skills/yagni-ladder/SKILL.md` and
   `payload/skills/compress-technical-prose/SKILL.md` per §4.1/§4.2.
4. Update `payload/skills/CATALOG.md`: add the two bullets under "Core
   framework skills" (§5) and bump the skill count header.
5. Run `lint_description_bloat.py` against the repo once both new skills
   exist, to confirm their own descriptions stay under budget (dogfooding).
6. Run the full existing suite (`python3 -m unittest discover -s
   payload/tools/tests -p "test_*.py"`, currently 269 tests) before and
   after, confirming the new test file brings the total to 270+ passing with
   zero regressions.
7. Commit on `feat/ponytail-caveman-port` (already created) using the
   three-section `(1) Task & Change / (2) Tests created or modified /
   (3) Test results — evidence` commit body, explicit `git add <paths>` (no
   `git add -A`).
8. Push and open a PR against `main` summarizing the whole branch.

## 7. Out of scope (explicit, to prevent scope creep on review)

- No changes to `payload/registry/REGISTRY.md` (the budget-constrained seed
  file) — discovery for these two skills goes entirely through `CATALOG.md`,
  matching how the other 168 skills in that category are discovered.
- No hook, MCP server, or new runtime dependency of any kind.
- No slash commands, no subagents.
- No change to how the agent generates conversational replies, commit
  messages, or any client-facing prose — the grammar mandate is unaffected
  and unmodified by this work.
