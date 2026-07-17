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
import argparse
import json
import os
import pathlib
import re
import sys
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


_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")
_PCT_RE = re.compile(r"(\d{1,3})\s*%")


def parse_usage_text(text):
    """Extract the session- and weekly-limit percentages and their reset
    timestamps from the usage page's accessible text.

    The spec leaves the exact selectors to the implementation (it specifies only
    a DOM/accessibility-tree read, not CSS selectors). Strategy: anchor on the
    'session' and 'weekly' section labels, split the text into the two regions,
    then within each region take the first NN% figure and the first ISO-8601 UTC
    timestamp. Raise ValueError if a section, percentage, or timestamp is absent
    or a percentage is out of the 0-100 range — the caller treats any ValueError
    as a login redirect / DOM drift and leaves the cache untouched.
    """
    lowered = text.lower()
    i_session = lowered.find("session")
    i_weekly = lowered.find("weekly")
    if i_weekly == -1:
        i_weekly = lowered.find("week")
    if i_session == -1 or i_weekly == -1:
        raise ValueError("usage page missing session/weekly section labels")

    if i_session < i_weekly:
        session_region, weekly_region = text[i_session:i_weekly], text[i_weekly:]
    else:
        weekly_region, session_region = text[i_weekly:i_session], text[i_session:]

    def _first_pct(region, label):
        m = _PCT_RE.search(region)
        if not m:
            raise ValueError(f"no percentage found in {label} section")
        pct = int(m.group(1))
        if not 0 <= pct <= 100:
            raise ValueError(f"{label} percentage out of range: {pct}")
        return pct

    def _first_iso(region, label):
        m = _ISO_RE.search(region)
        if not m:
            raise ValueError(f"no reset timestamp found in {label} section")
        return m.group(0)

    return {
        "session_pct": _first_pct(session_region, "session"),
        "weekly_pct": _first_pct(weekly_region, "weekly"),
        "session_resets_at": _first_iso(session_region, "session"),
        "weekly_resets_at": _first_iso(weekly_region, "weekly"),
    }


def _fetch_page_text(storage_state_path):
    """Headless Playwright read: load the persisted storageState, navigate to the
    usage page, return (final_url, body_text). Playwright is imported lazily so
    unit tests (which inject a fake fetch into poll()) need no browser installed.
    """
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=str(storage_state_path))
            page = context.new_page()
            page.goto(USAGE_URL, wait_until="networkidle")
            return page.url, page.inner_text("body")
        finally:
            browser.close()


def build_status(parsed, now=None):
    """Add polled_at and return the full status.json object in the spec's exact
    field order: polled_at, session_pct, weekly_pct, session_resets_at,
    weekly_resets_at."""
    now = now or datetime.now(timezone.utc)
    return {
        "polled_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session_pct": parsed["session_pct"],
        "weekly_pct": parsed["weekly_pct"],
        "session_resets_at": parsed["session_resets_at"],
        "weekly_resets_at": parsed["weekly_resets_at"],
    }


def atomic_write_json(path, obj):
    """Write `obj` as JSON to `path` atomically: serialize to a .tmp sibling, then
    os.rename over the destination so a reader never sees a partial file."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")
    os.rename(tmp, path)


def poll(cache_path, log_path, storage_state_path=STORAGE_STATE_PATH,
         now=None, fetch=None):
    """Headless poll orchestration. On success, atomically write the cache. On a
    login redirect, a parse failure (DOM drift), a browser/network error, or an
    unwritable cache: log one line and leave the existing cache untouched. Never
    raises."""
    fetch = fetch or _fetch_page_text
    try:
        url, text = fetch(storage_state_path)
    except Exception as e:
        log_line(log_path,
                 f"poll aborted: browser/fetch error, cache left untouched ({e!r})")
        return
    if "/login" in url:
        log_line(log_path,
                 "poll aborted: claude.ai redirected to login; session expired, "
                 "cache left untouched — re-run 'usage_poll.py --login'")
        return
    try:
        parsed = parse_usage_text(text)
    except Exception as e:
        log_line(log_path,
                 f"poll aborted: could not parse usage page (DOM drift?), "
                 f"cache left untouched ({e!r})")
        return
    try:
        atomic_write_json(cache_path, build_status(parsed, now))
    except Exception as e:
        log_line(log_path, f"poll aborted: could not write cache ({e!r})")


def build_arg_parser():
    ap = argparse.ArgumentParser(
        prog="usage_poll.py",
        description="Poll claude.ai's usage page and cache the session/weekly "
                    "limit percentages for the usage-budget hook.",
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--login", action="store_true",
                      help="Open a visible browser once to authenticate to "
                           "claude.ai; persist the session.")
    mode.add_argument("--poll", action="store_true",
                      help="(default) Headless poll: refresh the cached usage "
                           "status.")
    return ap


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    cache_path, log_path = resolve_paths()
    try:
        if args.login:
            path = login()
            print(f"Saved claude.ai session to {path}")
        else:
            poll(cache_path, log_path)
    except Exception as e:  # fail-open: a failed run must never break launchd.
        try:
            log_line(log_path, f"unexpected top-level error, exiting 0 ({e!r})")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
