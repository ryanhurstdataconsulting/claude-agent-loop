# Guide — machine-prose-grammar-gate

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The user is a self-described grammar stickler, and the standing directive to
proofread everything the software generates was, until now, a manual review
habit rather than an executable check. That habit failed in live client-facing
output: article errors such as "with an 32.2" (should be "with a 32.2") and
"an 8.1" mishandling, a "Warriors's" possessive, "1 officers" / "one officers"
pluralization drift, and its/their agreement slips all shipped to production
across multiple projects. The same bug shipped twice in one file, and in one
case a subagent explicitly left a known grammar bug untouched. It is distinct
from the catalog `ai-writing-auditor` (which strips AI-isms, not grammar
defects) and from the standing grammar rule (a rule, not a runnable gate).

## When to deploy (triggers)
- Before shipping ANY machine-generated, client-facing natural-language
  string: report narratives, dashboard headlines, coaching cues, deck copy,
  legal clauses.
- Whenever code assembles prose from data — especially where a number
  precedes an article ("a 5.0", "an 8.1", "an 11", "an 80", "a 32.2") or
  where a count drives pluralization ("1 officer", "2 officers").
- After any edit to a template or f-string that emits end-user text.

## Interface (how to invoke)
Tool. Two surfaces: (1) a shared helper module exposing a number-aware
`indefinite_article()` and a `pluralize()` that project code imports so the
text is correct at generation time; (2) a standalone linter,
`python3 ~/.claude/tools/machine_prose_grammar_gate.py <path-or-glob>`, that
scans emitted strings and exits non-zero on a regression. Wire the linter into
the project's test suite so machine-generated text that regresses fails a test.

## Composition (pairs with / hands off to)
Runs in the pre-ship lane next to `secret-pii-scrub-gate` (that one scans for
leaks; this one scans for grammar). Pairs with `sports-analyst` and
`data-visualization` output paths, since dashboard and report copy is the
highest-volume source of generated prose. Surfaced by `resource-loop`.

## Build & maintenance notes
Build sketch: a shared, number-aware `indefinite_article()` (keyed on the
spoken sound of the following token, including numerals) and a `pluralize()`
helper, plus a lightweight linter for double spaces, common homophones
(its/it's, their/there/they're), possessive misuse, and subject-verb
heuristics. Every fix must land with a regression test on the machine-generated
text, per the standing grammar rule. Lives at
`~/.claude/tools/machine_prose_grammar_gate.py` with an importable helper
module.
