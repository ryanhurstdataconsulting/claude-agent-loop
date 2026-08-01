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
schedule. A `blocked` or `failed` verdict alerts too, even at zero findings,
so a gate abort or a crashed audit is never mistaken for a quiet clean run.

## When to deploy (triggers)
- Nightly, after the run sweep, to render and persist the day's digest:
  `audit_digest.py`.
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
- Reads the run-log JSON `audit_run.sh` writes, under the store
  `audit_store.py` owns.
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
