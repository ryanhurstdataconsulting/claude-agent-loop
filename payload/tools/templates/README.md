# dev-server-orchestration — templates and convention

**Guide:** [`registry/guides/dev-server-orchestration.md`](../../registry/guides/dev-server-orchestration.md)

This directory holds the two per-project templates for the
`dev-server-orchestration` convention. It is not itself a runnable tool —
copy the templates into a project, fill in the `# CONFIGURE:` placeholders,
and commit them there.

## The convention

Every project that has a dev stack (an API + frontend, a plain
`http.server`, a Tauri dev window, a docker-compose stack — anything an
agent would otherwise "spin up" by hand) exposes the same entry point at its
repo root:

- `dev_up.sh` — starts the stack, then blocks until it is actually ready.
- `dev_down.sh` — stops everything the stack started, cleanly.

A project MAY instead expose `make serve` / `make stop` targets that satisfy
the same contract below — the filename convention exists so an agent (or a
human) never has to ask "how do I start this project" twice; either shape is
fine as long as it is documented once, in this way.

## The health-gate contract (the part that matters)

`dev_up.sh` must not return / exit 0 the moment the process is launched. It
must poll a real health-check URL and only report ready once that endpoint
answers HTTP 200. "The process exists" is not the same thing as "the stack is
ready to serve traffic" — a server that started but crashed on its first
request, or is still booting, must not be reported as up.

This is the property that kills the failure mode the guide exists to
prevent: an agent restarting a server, seeing no error, and then mistaking a
still-not-actually-ready stack for a code bug in the feature under test.
Keep the gate strict — hit a route that exercises the thing you actually
care about (a DB-backed health check, not a static 200), and give it a
sensible timeout so a genuinely broken start still fails loudly instead of
polling forever.

`dev_down.sh` must be idempotent. Running it twice, or running it when
nothing is up, must not error — it should report "nothing was running" and
exit 0. Track what you started (a pidfile is the simplest mechanism) and
fall back to a port-based kill only when the pidfile is missing or stale.

## Where these live

- **Templates (this directory):** `dev_up.sh`, `dev_down.sh` — inert
  scaffolds with `# CONFIGURE:` markers at every project-specific decision
  (start command, health URL, pidfile path, fallback port). They are not
  meant to run a real server as-is; copy first, configure second.
- **Per-project copies:** `<project-root>/dev_up.sh` and
  `<project-root>/dev_down.sh`, committed alongside the project's own code so
  the convention travels with the repo instead of depending on this
  machine-global copy staying in sync.

## Composition

Pairs with `background-build-watch` — once `dev_up.sh` returns ready, watch
its `$LOGFILE` for a subsequent build/rebuild with
`bash ~/.claude/tools/build_watch.sh <logfile> <success-regex> <fail-regex>`
instead of hand-polling. For a stack that needs an SSH tunnel first (e.g. the
remote Postgres tunnel), bring the tunnel up before calling `dev_up.sh`
— that dependency is a `# CONFIGURE:` start-command line, not a separate
convention. Surfaced by the `resource-loop` on any "spin it up" / "let me
test" trigger.
