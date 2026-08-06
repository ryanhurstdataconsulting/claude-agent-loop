# payload/observability/

Out-of-tree observability tooling. Everything here runs OUTSIDE a Claude Code
hook — it is scheduled via launchd (`obs_ship.py`) or invoked manually
(`metrics_to_otlp.py`, Phase 3), never imported from `payload/hooks/`.

## `obs_ship.py`

Reads `~/.claude/metrics/events/*.ndjson` (Phase 1's obs.v1 log), folds
events into spans, and exports via OTLP to `localhost:4318`. Requires a real
`opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-http` dependency —
this is the one place in the framework where that's true, because this is a
sidecar process, not a hook (hooks stay stdlib-only).

**Setup (one-time):**

```bash
python3 -m venv ~/.claude-agent-loop/obs-venv
~/.claude-agent-loop/obs-venv/bin/pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
```

**Run manually:** `~/.claude-agent-loop/obs-venv/bin/python3 ~/.claude/observability/obs_ship.py`

**Scheduled:** via `com.hdc.claude-agent-loop.obs-ship.plist` (see Phase 3 of
the observability-layer build for the launchd bootstrap step) — `StartInterval`
60s.

**Tests:** `~/.claude-agent-loop/obs-venv/bin/python3 -m unittest discover -s tests` from this directory.
