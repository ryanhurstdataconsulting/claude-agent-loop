# Guide — audit-digest

**Category:** tool
**Scope:** machine-global
**Status:** active

## Why this exists (evidence)
Audits run across many packages nightly, and almost every finding is
routine — zero counts, or a Low/Informational note nobody needs to see at 2
a.m. If every run notified, the human would learn to ignore notifications,
and the one Critical that matters would get ignored right along with them.
`audit_digest` is the severity split: Critical and High interrupt
immediately (the same rule `audit_run.sh` already applies for its own OS
notification); everything else — Medium, Low, Informational, and every clean
run — waits here, batched into a digest reviewed on the human's own
schedule. A `blocked`, `failed`, or `quarantined` verdict alerts too, even at
zero findings, so a gate abort, a crashed audit, or a findings document held
back from a client repo is never mistaken for a quiet clean run.

**A run whose findings could not be parsed alerts as well, and this is the
whole point of the layer's no-fabrication contract.** `audit_run.sh` writes
`"findings": null` rather than inventing zero counts when it cannot read a
severity object out of the CLI's output. `null` means "nobody knows", which
is emphatically not the claim "zero" makes — so the digest renders it as
`findings unparsed` and `severity_alert()` surfaces it, in the same class as
`blocked`/`failed`. Rendering it as `0/0` would turn the one place that
distinction mattered into a fabricated all-clear.

## When to deploy (triggers)
- Nightly, at the end of the sweep. `audit_dispatch.py` calls
  `write_digest()` once, after the last package has run.
- Manually, to render and persist a digest out of band: `audit_digest.py`.
- At SessionStart, to surface an unread digest once: `audit_digest.py
  --nudge`.

## Interface (how to invoke)
```
audit_digest.py [--root DIR]            # render + persist today's digest, advance the window, print its path
audit_digest.py [--root DIR] --nudge    # print the one-line SessionStart nudge if unread, else nothing
```
`nudge()` is self-consuming, the same shape as the loop-close hook's digest
section: the newest digest is reported at most once, then goes quiet until
the next one lands.

## Composition (pairs with / hands off to)
- Called once per sweep by `audit_dispatch.py`, after the last package's
  `audit_run.sh` invocation returns.
- Reads the run-log JSON `audit_run.sh` writes, under the store
  `audit_store.py` owns. The walk is recursive, because a package key is a
  workspace-relative path and its run logs sit two levels under `runs/`.
- Commits each digest and its window marker to the store's own local git
  history through `audit_store.commit_paths()` — no remote, no push.
- `severity_alert()` applies the same rule `audit_run.sh` already uses for
  its own immediate OS notification — this module's `render()` repeats
  those runs in the digest's Alerts section, so the digest is a complete
  record of the window rather than only whatever never got surfaced.
- Its digest is LOCAL-ONLY and carries a header comment saying so: never
  publish it, or copy an excerpt out of the store, without re-running
  `classify_visibility.py` and `secret_pii_scrub_gate.py` over it first —
  the same rule the rest of the metrics store follows.

## Build & maintenance notes
Lives at `payload/tools/audit_digest.py`. Tests:
`payload/tools/tests/test_audit_digest.py`. Stdlib only.
`digests/.last-digest` tracks the render window (an ISO instant);
`digests/.last-read` tracks what the nudge has already shown a human. Both
advance only on a successful call, so a crash mid-render never silently
marks a digest as read.
