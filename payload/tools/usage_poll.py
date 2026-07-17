#!/usr/bin/env python3
"""usage_poll.py — poll claude.ai's usage page for the account's session- and
weekly-limit percentages and cache them for the usage-budget hook.

Two modes:
  --login: open a visible browser once so you can authenticate to claude.ai,
    then persist the Playwright storageState to a gitignored path.
  --poll (default): headless — reuse the persisted storageState, read the
    two usage percentages plus their reset timestamps, and atomically write
    $METRICS_DIR/state/usage/status.json.

The poller never talks to a running Claude Code session; the hook reads only the
cache file this writes. Any poll failure is logged and leaves the existing cache
untouched, and the process always exits 0 so a failed poll never breaks the
launchd job.
"""
import os
import pathlib
from datetime import datetime, timezone

# The current claude.ai usage page. If claude.ai moves this page, update here.
USAGE_URL = "https://claude.ai/settings/usage"

# Persisted Playwright storageState (cookies + localStorage). Gitignored,
# treated exactly like secrets.env: never committed, never printed in full.
STORAGE_STATE_PATH = pathlib.Path.home() / ".claude-agent-loop" / "usage-session.json"


def resolve_paths():
    """Resolve (cache_path, log_path) from the shared METRICS_DIR convention.

    Mirrors context-budget.sh: METRICS_DIR defaults to $CLAUDE_DIR/metrics, and
    CLAUDE_DIR defaults to ~/.claude.
    """
    claude_dir = os.environ.get("CLAUDE_DIR") or str(pathlib.Path.home() / ".claude")
    metrics_dir = os.environ.get("METRICS_DIR") or os.path.join(claude_dir, "metrics")
    cache_path = pathlib.Path(metrics_dir) / "state" / "usage" / "status.json"
    log_path = pathlib.Path(metrics_dir) / "logs" / "usage_poll.log"
    return cache_path, log_path


def log_line(log_path, msg):
    """Append a single timestamped diagnostic line to the poller's log file."""
    log_path = pathlib.Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{stamp} {msg}\n")


def login(storage_state_path=STORAGE_STATE_PATH, launcher=None, prompt=input):
    """Open a visible browser for a one-time manual claude.ai login, then persist
    the Playwright storageState to `storage_state_path` (parent dir forced 0700).

    `launcher` and `prompt` are injectable for testing; in production `launcher`
    defaults to the real Playwright Chromium driver below.
    """
    storage_state_path = pathlib.Path(storage_state_path)
    storage_state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(storage_state_path.parent, 0o700)  # mkdir mode is umask-masked; force it.
    launcher = launcher or _playwright_login_launcher
    launcher(USAGE_URL, str(storage_state_path), prompt)
    return storage_state_path


def _playwright_login_launcher(url, storage_state_path, prompt):
    """Real Playwright driver for --login. Imported lazily so the module (and its
    unit tests) load without the `playwright` package installed."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(url)
            prompt("Log in to claude.ai in the browser window, open the usage "
                   "page, then press Enter here to save the session... ")
            context.storage_state(path=storage_state_path)
        finally:
            browser.close()
