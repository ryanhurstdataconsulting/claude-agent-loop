# Guide — repo-audit-action

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
The nightly scheduler (`audit-dispatch` -> `audit-run`) audits a package on a
rotating cadence, on one machine, against a working copy. That cadence is the
right economics for a full audit and the wrong latency for a change: a defect
introduced on Monday morning waits until the package's interval elapses before
anything looks at it. This workflow template is the per-change half of the
same design. It runs on every push and every pull request, and it says out
loud what it cannot see.

Four of the audit's six categories survive a CI checkout: dependency CVEs,
application-layer SAST, secrets in tracked code, and CI/CD readiness. Two do
not, and the reason matters more than the fact:

- **untracked-PII and gitignore compliance** is unanswerable by construction.
  A checkout contains only tracked files, so the very files the category
  exists to find are the ones CI can never be shown.
- **secrets.env symlink integrity** checks a property of a developer's
  machine. That state does not exist on a runner at all.

So the workflow never attempts them, and every run carries one fixed sentence
saying so, in the job summary and in the pull-request comment:

> This is a REDUCED audit. Two categories cannot run in CI:
> untracked-PII/gitignore compliance and secrets.env symlink integrity. A
> passing check here is not a full audit.

A green check that is silently partial is worse than no check: it retires the
question. That is why the sentence is pinned by a fixed-string test rather
than left to reviewer diligence.

## When to deploy (triggers)
- Adopting per-change security feedback in a repository that already has, or
  will have, nightly audits. The two layers compose; neither replaces the other.
- A pull request that touches dependencies, authentication, request handling,
  or the workflow files themselves — the four categories this layer covers.
- Do NOT reach for it to answer "is this repository clean". Only the full
  audit answers that.

## Interface (how to invoke)
Copy the template into the target repository, then add the secret:

```
cp ~/.claude/templates/repo-security-audit.yml \
   <repo>/.github/workflows/repo-security-audit.yml
```

Then, as the repository owner, add an `ANTHROPIC_API_KEY` repository secret
under Settings -> Secrets and variables -> Actions. **The workflow cannot do
this for itself, and no agent should try.** Distributing an API key across
repositories is an owner decision with a real cost and a real blast radius; it
sits outside the workflow's authority on purpose. Without the secret the job
does not go red — it reports the reduced audit as skipped and exits green,
which is also what happens on a pull request from a fork, where GitHub
withholds secrets.

The template needs no editing. It names no client, no person, and no path
outside the checkout.

Contracts the template holds to:
- `permissions: contents: read`. It cannot write to the repository it audits.
- No file-writing tool is in the agent's allowlist, so the run cannot alter
  the checkout even if its prompt were ignored. It creates no commit, no
  branch, and no findings document.
- Findings are informational and never turn the check red. Failing a build on
  them is a decision to take once signal quality is proven over real runs, not
  a default to ship with.
- The audit step is `continue-on-error`, so a CLI failure reports "the audit
  did not complete" rather than blocking a merge on an infrastructure problem.

## Composition (pairs with / hands off to)
- Complements `audit-dispatch` and `audit-run`, which own the full, six-category
  audit on a schedule. This layer is faster and narrower; that one is complete.
- Shares the read-only-scanner allowlist shape with `audit-run`: named
  scanners one at a time, never a blanket `Bash(git:*)`.
- Produces nothing for `audit-store`. Store artifacts are local-only by
  invariant, and a CI runner is not this machine — the workflow's output lives
  in the run's job summary and its pull-request comment, and nowhere else.

## Build & maintenance notes
Lives at `payload/templates/repo-security-audit.yml`. Test:
`payload/tools/tests/test_actions_template.sh`, which asserts the limitations
sentence as a fixed string, in both its source and its echoed form, so a later
edit cannot quietly soften or drop the disclosure. The same suite pins the
read-only permission, the absence of a file-writing tool, both triggers, all
six category names, and that the template carries no client identifier and no
machine-specific path.

Known limitations: the four covered categories are only as good as what a
checkout exposes, so a CVE in a dependency resolved at deploy time rather than
locked in the repository is invisible here. The workflow installs the CLI with
`npm install -g` on each run, which is a minute of runner time and an
unpinned version — pin it if a supply-chain review calls for reproducibility.
