# Guide — secret-pii-scrub-gate

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The commit protocol forbids `git add -A`, but nothing actually scans staged
content, so leaks stayed one slip away. Multiple sessions rebuilt the same ad
hoc grep battery from scratch, and the record includes a live-token paste, a
"one `git add .` away from leaking" near-miss, and the risk of credentials
being staged into a client-facing distributable. This pattern recurred across
multiple projects. It scans file content, which is what makes it complementary
to an egress-safety audit (a resource that scans repo egress paths, not
content).

## When to deploy (triggers)
- Before any commit (ideally as a git pre-commit hook).
- Before assembling any handoff bundle or client desktop deliverable.
- Before a `git format-patch` handoff to a third-party vendor.
- Symptoms it prevents: a JWT, password, or SSH private-key header in a diff;
  a customer's name or contact detail in tracked output; a `/Users/<name>`
  absolute path baked into a shipped artifact.

## Interface (how to invoke)
Tool. Exact command line:
`python3 ~/.claude/tools/secret_pii_scrub_gate.py` (scans the git staging area
by default; accepts an explicit path or bundle directory). Installable as a
git pre-commit hook. It reports file + line + matched class (with the secret
itself redacted) and exits non-zero on any hit.

## Composition (pairs with / hands off to)
Pairs with an egress-safety audit resource (content vs. egress paths) and runs
in the same pre-ship lane as `machine-prose-grammar-gate`. Enforces the
workspace-root safety rules (secrets and PII never land in git). Surfaced by
`resource-loop` before any commit or handoff step.

## Build & maintenance notes
Build sketch: one script with a tuned pattern set (JWT shape, common password
keys, `BEGIN ... PRIVATE KEY` headers, email regex, `/Users/<name>` paths,
customer-PII heuristics) plus an allowlist file for known-safe matches;
runnable standalone and as a pre-commit hook; redacts every match in its
output so the scanner itself never echoes a secret. Lives at
`~/.claude/tools/secret_pii_scrub_gate.py`; test with a fixture containing one
planted instance of each class.
