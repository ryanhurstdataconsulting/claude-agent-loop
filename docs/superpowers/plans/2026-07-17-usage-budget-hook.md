# Usage-Budget Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a decoupled poller + PostToolUse hook that reads Claude subscription session/weekly usage limits from a locally cached snapshot and steers active sessions toward a safe, resumable pause point before usage runs out.

**Architecture:** A standalone Playwright-based poller (`payload/tools/usage_poll.py`), run every ~10 minutes by a launchd user-agent job, headlessly reads claude.ai's usage page using a persisted, gitignored session and writes an atomic JSON cache to `$METRICS_DIR/state/usage/status.json`. A PostToolUse hook (`payload/hooks/usage-budget.sh`), built in the same bash-wrapper/Python-heredoc house style as `context-budget.sh`, reads only that cache (no network calls of its own) and fires a WARN once at 70% and a repeating CRIT at 85% of `max(session_pct, weekly_pct)`, re-arming when usage drops back below the warn threshold.

**Tech Stack:** Python 3 (poller + hook heredoc), Playwright (headless Chromium, persisted `storageState`), bash (hook wrapper, launchd plist), a pytest/bash test harness matching `test_context_budget.sh`'s house style.

## Global Constraints

- **`status.json` schema** (written atomically by the poller at `$METRICS_DIR/state/usage/status.json`, `.tmp` + `os.rename`), fields in this exact key order:
  ```json
  {
    "polled_at":         "2026-07-17T14:32:00Z",
    "session_pct":       42,
    "weekly_pct":        68,
    "session_resets_at": "2026-07-17T19:00:00Z",
    "weekly_resets_at":  "2026-07-21T00:00:00Z"
  }
  ```
  `polled_at`/`*_resets_at` are ISO-8601 UTC with a trailing `Z`; `session_pct`/`weekly_pct` are integers 0-100. On any poll failure, the poller logs one line and leaves `status.json` untouched; the poller always exits 0.
- **Effective metric (hook-side):** `max(session_pct, weekly_pct)`, with the binding reset timestamp taken from whichever of `session_resets_at`/`weekly_resets_at` corresponds to the larger value.
- **Hook env vars/defaults:** `USAGE_BUDGET_DISABLE` (kill switch), `USAGE_BUDGET_WARN_PCT`=70, `USAGE_BUDGET_CRIT_PCT`=85, `USAGE_BUDGET_CHECK_SECS`=30 (throttle), `USAGE_BUDGET_STALE_SECS`=1800 (cache staleness ceiling — a stale cache is treated as silent/no-fire, even above CRIT).
- **Per-session fire-state JSON** (4 fields, mirroring `context-budget.sh`): `{"last_check_ts": 0.0, "warn_fired": false, "crit_since": null, "checkpoint_ack": false}`. WARN fires once; CRIT fires on every call with no throttle until a checkpoint file's mtime is `>= int(crit_since)`; a drop back below `USAGE_BUDGET_WARN_PCT` resets state via `reset_state()`.
- **Session-id sanitization:** `re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id))[:128]`.
- **Fail-open, absolute:** every hook exit path funnels through a `bail()` helper (`os._exit(0)` after flushing stdout); the bash wrapper closes with a bare `exit 0`. The hook never blocks a tool call.
- **Emitted directive strings (exact, grammar-gate-locked — Task 8 asserts these character-for-character and Task 9 case 17 re-locks them):**
  - WARN `systemMessage`: `Usage budget: account usage at 70% of the weekly/session limit. Steering toward a pause point.`
  - WARN `additionalContext`: `Usage-budget warning: this account's usage is at 70% of its weekly/session limit. Consider steering toward a safe pause point in the next hour.`
  - CRIT `systemMessage`: `Usage budget CRITICAL: account usage at 86%. Checkpoint required.`
  - CRIT `additionalContext`: `Usage-budget CRITICAL: usage is at 86%, close to the account limit (resets <weekly_resets_at or session_resets_at>). Stop new work, commit and push what's in progress, and write a checkpoint file at <checkpoint path> — this message will repeat until you do.`
  - Emitted JSON shape: `{"systemMessage": <str>, "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": <str>}}`.
- **Implementation phasing:** the poller group (Tasks 1-5) must land before the hook group (Tasks 6-10) — the hook is a pure consumer of the poller's cache contract and has nothing to read until the poller exists.
- **Auth approach (Ryan-approved):** the poller uses a persisted, gitignored Playwright `storageState` session file (bootstrapped once via an interactive `--login` run), never credentials in code or environment.

## File Structure

**Poller group:**
- Create: `payload/tools/usage_poll.py` — standalone Playwright poller; `--login` bootstrap mode and default `--poll` mode; writes the atomic `status.json` cache.
- Create: `payload/launchd/com.hdc.claude-agent-loop.usage-poll.plist` — launchd user-agent job running the poller every ~10 minutes.
- Create: `payload/tools/tests/test_usage_poll.py` — poller test suite (schema-lock, hygiene, launchd/manifest checks).
- Modify: `payload/MANIFEST` — link-file lines for the poller module, plist, and test file.
- Modify: `CHANGELOG.md` — "Added" bullet for the poller.
- Modify: `INSTALL.md` — new "Usage-budget poller (one-time)" section documenting the two Ryan-gated manual steps.

**Hook group:**
- Create: `payload/hooks/usage-budget.sh` — PostToolUse hook (bash wrapper + Python heredoc), cache-read-only, fail-open.
- Create: `payload/tools/tests/test_usage_budget.sh` — 17-case hook test suite.
- Modify: `payload/MANIFEST` — link-file line for the hook and its test.
- Modify: `payload/fragments/settings.fragment.json` — PostToolUse hook registration.
- Modify: `README.md` — hooks table entry.
- Modify: `ARCHITECTURE.md` — one-paragraph description of the poller/hook split.
- Modify: `CHANGELOG.md` — "Added" bullet for the hook.

---

## Poller group — shared interface contract (Task 6 depends on this VERBATIM)

**Cache file the poller produces (single source of truth for the hook):**

```
$METRICS_DIR/state/usage/status.json
```

where `METRICS_DIR` follows the existing repo convention exactly as
`context-budget.sh` resolves it (`payload/hooks/context-budget.sh:20-21`):
`METRICS_DIR` defaults to `$CLAUDE_DIR/metrics`, and `CLAUDE_DIR` defaults to
`$HOME/.claude`. So the default absolute path is:

```
~/.claude/metrics/state/usage/status.json
```

**Exact `status.json` schema (field names, order, and types — verbatim from
spec lines 129–137):**

```json
{
  "polled_at":         "2026-07-17T14:32:00Z",
  "session_pct":       42,
  "weekly_pct":        68,
  "session_resets_at": "2026-07-17T19:00:00Z",
  "weekly_resets_at":  "2026-07-21T00:00:00Z"
}
```

| Field | Type | Notes |
|---|---|---|
| `polled_at` | `str` | ISO-8601 UTC, `Z` suffix (`YYYY-MM-DDTHH:MM:SSZ`). Set by the poller at write time. This is the field the hook's staleness check reads. |
| `session_pct` | `int` | 0–100. Session-limit percentage. |
| `weekly_pct` | `int` | 0–100. Weekly-limit percentage. |
| `session_resets_at` | `str` | ISO-8601 UTC, `Z` suffix. |
| `weekly_resets_at` | `str` | ISO-8601 UTC, `Z` suffix. |

**Hook-side contract guarantees the poller upholds (so Task 6 can rely on them):**

- The file is written **atomically** (`.tmp` sibling + `os.rename`), so the hook
  never observes a partial file.
- On **any** poll failure (login-redirect / session expiry, DOM-shape drift,
  network or Playwright error, unwritable cache), the poller logs one line to
  `$METRICS_DIR/logs/usage_poll.log` and **leaves the existing `status.json`
  untouched** — it never writes a zeroed or partial reading. A stale-but-real
  cache is the failure mode; the hook's own `USAGE_BUDGET_STALE_SECS` staleness
  check (Task 6) is what converts staleness into silence.
- The poller **always exits 0**, so a failed poll never breaks the launchd job.
- The poller emits **no in-session end-user narrative prose** — the WARN/CRIT
  directive strings are the hook's (Task 6). The poller's only human-facing
  output is diagnostic log lines (to the log file) and one `--login`
  confirmation line on stdout; both are proofread and Task 4 asserts basic
  hygiene (no double spaces) on a log line.

The metric the hook derives from this file is `max(session_pct, weekly_pct)`
(spec line 170) — computed hook-side, not stored in the cache.

---


---

## Poller Group (Tasks 1–5)

Built first — the hook group (below) is a pure consumer of the `status.json` contract above and has nothing to read until this group exists.

### Task 1: Poller module skeleton + Playwright `--login` auth bootstrap

**Files:**
- Create: `payload/tools/usage_poll.py`
- Test: `payload/tools/tests/test_usage_poll.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (first task).
- Produces:
  - Constant `USAGE_URL: str` — the claude.ai usage page URL.
  - Constant `STORAGE_STATE_PATH: pathlib.Path` = `~/.claude-agent-loop/usage-session.json`
    (gitignored persisted Playwright `storageState`; treated like `secrets.env`).
  - `resolve_paths() -> tuple[pathlib.Path, pathlib.Path]` → `(cache_path, log_path)`
    following the `METRICS_DIR`/`CLAUDE_DIR` convention above.
  - `log_line(log_path, msg: str) -> None` — append one timestamped diagnostic line.
  - `login(storage_state_path=STORAGE_STATE_PATH, launcher=None, prompt=input) -> pathlib.Path`
    — opens a visible browser once, persists `storageState` to the gitignored
    path (parent dir forced to `0700`). `launcher`/`prompt` are injectable for testing.

- [ ] **Step 1: Write the failing test**

Create `payload/tools/tests/test_usage_poll.py`:

```python
import json, os, pathlib, sys, tempfile, unittest
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import usage_poll as up


class TestPathResolution(unittest.TestCase):
    def test_cache_and_log_paths_follow_metrics_dir(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["METRICS_DIR"] = d
            try:
                cache_path, log_path = up.resolve_paths()
            finally:
                del os.environ["METRICS_DIR"]
            self.assertEqual(cache_path,
                             pathlib.Path(d) / "state" / "usage" / "status.json")
            self.assertEqual(log_path,
                             pathlib.Path(d) / "logs" / "usage_poll.log")

    def test_storage_state_path_is_gitignored_home_file(self):
        self.assertEqual(
            up.STORAGE_STATE_PATH,
            pathlib.Path.home() / ".claude-agent-loop" / "usage-session.json",
        )


class TestLoginBootstrap(unittest.TestCase):
    def test_login_persists_storage_state_to_gitignored_path(self):
        with tempfile.TemporaryDirectory() as d:
            target = pathlib.Path(d) / ".claude-agent-loop" / "usage-session.json"
            saved = {}

            def fake_launcher(url, storage_state_path, prompt):
                # emulate Playwright writing the storageState file, then the
                # interactive "press Enter when logged in" prompt.
                pathlib.Path(storage_state_path).write_text('{"cookies": []}')
                saved["url"] = url
                saved["path"] = storage_state_path
                prompt("go")

            prompts = []
            returned = up.login(storage_state_path=target,
                                launcher=fake_launcher,
                                prompt=lambda msg: prompts.append(msg))

            self.assertEqual(saved["url"], up.USAGE_URL)
            self.assertEqual(saved["path"], str(target))
            self.assertTrue(target.exists())
            self.assertEqual(returned, target)
            # secrets-handling convention: parent dir locked to 0700.
            self.assertEqual(oct(target.parent.stat().st_mode & 0o777), "0o700")
            self.assertEqual(len(prompts), 1)

    def test_log_line_appends_timestamped_line(self):
        with tempfile.TemporaryDirectory() as d:
            log_path = pathlib.Path(d) / "logs" / "usage_poll.log"
            up.log_line(log_path, "hello world")
            body = log_path.read_text()
            self.assertTrue(body.endswith("hello world\n"))
            self.assertRegex(body, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z ")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```
cd payload/tools/tests && python3 -m unittest test_usage_poll -v
```
Expected failure: `ModuleNotFoundError: No module named 'usage_poll'` (the
module does not exist yet), reported as an ERROR on collection.

- [ ] **Step 3: Write minimal implementation**

Create `payload/tools/usage_poll.py`:

```python
#!/usr/bin/env python3
"""usage_poll.py — poll claude.ai's usage page for the account's session- and
weekly-limit percentages and cache them for the usage-budget hook.

Two modes:
  --login   Open a visible browser once so you can authenticate to claude.ai;
            persist the Playwright storageState to a gitignored path.
  --poll    (default) Headless: reuse the persisted storageState, read the two
            usage percentages plus their reset timestamps, and atomically write
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
```

Grammar note: this task emits no in-session end-user narrative prose. Its only
human-facing string is the `--login` browser prompt above ("Log in to
claude.ai... press Enter here to save the session"), which is proofread —
correct subject-verb agreement, no double spaces, no number-adjacent a/an.

- [ ] **Step 4: Run test to verify it passes**

```
cd payload/tools/tests && python3 -m unittest test_usage_poll -v
```
Expected: `Ran 4 tests ... OK` (TestPathResolution ×2, TestLoginBootstrap ×2).

- [ ] **Step 5: Commit**

```
git add payload/tools/usage_poll.py payload/tools/tests/test_usage_poll.py
git commit -m "feat(usage-poll): module skeleton + Playwright --login auth bootstrap

(1) Task & Change
First slice of the usage-budget poller (spec 2026-07-17-usage-budget-hook-design.md,
poller group Task 1). Adds payload/tools/usage_poll.py with the METRICS_DIR path
resolver, the gitignored STORAGE_STATE_PATH constant, a diagnostic log_line helper,
and login() — a one-time visible-browser claude.ai auth that persists Playwright
storageState to ~/.claude-agent-loop/usage-session.json with the parent dir forced
to 0700. Playwright is imported lazily so the module loads for unit tests without a
browser installed.

(2) Tests created or modified
- payload/tools/tests/test_usage_poll.py — new: TestPathResolution (cache/log paths
  follow METRICS_DIR; storageState path is the gitignored home file) and
  TestLoginBootstrap (login persists storageState to the right path via an injected
  launcher, forces 0700 on the parent dir, calls the interactive prompt once; log_line
  appends a timestamped line).

(3) Test results — evidence
$ cd payload/tools/tests && python3 -m unittest test_usage_poll -v
Ran 4 tests in 0.0XXs
OK

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Headless usage-page read — percentage + reset-timestamp extraction

**Files:**
- Modify: `payload/tools/usage_poll.py` (append extraction + fetch adapter)
- Test: `payload/tools/tests/test_usage_poll.py` (append `TestParseUsageText`)

**Interfaces:**
- Consumes: `USAGE_URL` (Task 1).
- Produces:
  - `parse_usage_text(text: str) -> dict` returning the four parsed fields
    `{"session_pct": int, "weekly_pct": int, "session_resets_at": str,
    "weekly_resets_at": str}`. Raises `ValueError` when a section, percentage,
    or timestamp is missing/out-of-range (the caller treats this as
    login-redirect / DOM drift).
  - `_fetch_page_text(storage_state_path) -> tuple[str, str]` → `(final_url,
    body_text)` — the headless Playwright adapter (lazy import). Task 3's
    `poll()` calls this by default and injects a fake in tests.

- [ ] **Step 1: Write the failing test**

Append to `payload/tools/tests/test_usage_poll.py` (above the
`if __name__ == "__main__":` block):

```python
SAMPLE_USAGE_HTML = """
<main aria-label="Usage">
  <section aria-label="Session limit">
    <h2>Current session</h2>
    <div role="meter" aria-valuenow="42">42%</div>
    <p>Resets <time datetime="2026-07-17T19:00:00Z">7:00 PM</time></p>
  </section>
  <section aria-label="Weekly limit">
    <h2>Weekly usage</h2>
    <div role="meter" aria-valuenow="68">68%</div>
    <p>Resets <time datetime="2026-07-21T00:00:00Z">Mon 12:00 AM</time></p>
  </section>
</main>
"""

LOGIN_PAGE_HTML = """
<main><h1>Sign in to Claude</h1><button>Continue with Google</button></main>
"""


class TestParseUsageText(unittest.TestCase):
    def test_extracts_both_percentages_and_reset_timestamps(self):
        self.assertEqual(
            up.parse_usage_text(SAMPLE_USAGE_HTML),
            {
                "session_pct": 42,
                "weekly_pct": 68,
                "session_resets_at": "2026-07-17T19:00:00Z",
                "weekly_resets_at": "2026-07-21T00:00:00Z",
            },
        )

    def test_login_page_raises_valueerror(self):
        with self.assertRaises(ValueError):
            up.parse_usage_text(LOGIN_PAGE_HTML)

    def test_out_of_range_percentage_raises(self):
        bad = SAMPLE_USAGE_HTML.replace("42%", "142%")
        with self.assertRaises(ValueError):
            up.parse_usage_text(bad)

    def test_missing_timestamp_raises(self):
        bad = SAMPLE_USAGE_HTML.replace('datetime="2026-07-17T19:00:00Z"', 'datetime=""')
        with self.assertRaises(ValueError):
            up.parse_usage_text(bad)
```

- [ ] **Step 2: Run test to verify it fails**

```
cd payload/tools/tests && python3 -m unittest test_usage_poll -v
```
Expected failure: `AttributeError: module 'usage_poll' has no attribute
'parse_usage_text'` on each `TestParseUsageText` case.

- [ ] **Step 3: Write minimal implementation**

Append to `payload/tools/usage_poll.py` (after `_playwright_login_launcher`):

```python
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
```

Grammar note: no end-user prose is generated by this task (the raised
`ValueError` strings are internal diagnostics logged by `poll()` in Task 3, not
shown in-session). They are nonetheless proofread — no double spaces, correct
usage.

- [ ] **Step 4: Run test to verify it passes**

```
cd payload/tools/tests && python3 -m unittest test_usage_poll -v
```
Expected: `Ran 8 tests ... OK` (the 4 prior + `TestParseUsageText` ×4).

- [ ] **Step 5: Commit**

```
git add payload/tools/usage_poll.py payload/tools/tests/test_usage_poll.py
git commit -m "feat(usage-poll): usage-page percentage + reset-timestamp extraction

(1) Task & Change
Poller group Task 2. Adds parse_usage_text() — anchors on the session/weekly
section labels, then pulls the first NN% and first ISO-8601 UTC timestamp from
each region, raising ValueError on a missing section/percentage/timestamp or an
out-of-range percentage (the caller treats that as login-redirect / DOM drift).
Adds _fetch_page_text(), the lazy-imported headless Playwright adapter that loads
the persisted storageState and returns (final_url, body_text).

(2) Tests created or modified
- payload/tools/tests/test_usage_poll.py — added TestParseUsageText: extracts both
  percentages + reset timestamps from a fixture usage page; a login-page fixture,
  an out-of-range percentage, and a missing timestamp each raise ValueError.

(3) Test results — evidence
$ cd payload/tools/tests && python3 -m unittest test_usage_poll -v
Ran 8 tests in 0.0XXs
OK

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Atomic cache write + `poll()` orchestration and error handling

**Files:**
- Modify: `payload/tools/usage_poll.py` (append `build_status`, `atomic_write_json`, `poll`)
- Test: `payload/tools/tests/test_usage_poll.py` (append three test classes)

**Interfaces:**
- Consumes: `parse_usage_text`, `_fetch_page_text` (Task 2); `log_line` (Task 1).
- Produces:
  - `build_status(parsed: dict, now=None) -> dict` — adds `polled_at` and returns
    the full 5-field `status.json` object **in the spec's exact key order**.
  - `atomic_write_json(path, obj) -> None` — `.tmp` sibling + `os.rename`.
  - `poll(cache_path, log_path, storage_state_path=STORAGE_STATE_PATH, now=None,
    fetch=None) -> None` — orchestrates a headless poll; writes the cache on
    success, logs and leaves the cache untouched on login-redirect / DOM drift /
    fetch error / unwritable cache; never raises.

- [ ] **Step 1: Write the failing test**

Append to `payload/tools/tests/test_usage_poll.py` (above `if __name__`):

```python
class TestBuildStatus(unittest.TestCase):
    PARSED = {
        "session_pct": 42, "weekly_pct": 68,
        "session_resets_at": "2026-07-17T19:00:00Z",
        "weekly_resets_at": "2026-07-21T00:00:00Z",
    }

    def test_adds_polled_at_in_iso_utc_z_format(self):
        now = datetime(2026, 7, 17, 14, 32, 0, tzinfo=timezone.utc)
        self.assertEqual(up.build_status(self.PARSED, now=now)["polled_at"],
                         "2026-07-17T14:32:00Z")

    def test_exact_schema_keys_order_and_types(self):
        now = datetime(2026, 7, 17, 14, 32, 0, tzinfo=timezone.utc)
        status = up.build_status(self.PARSED, now=now)
        self.assertEqual(
            list(status.keys()),
            ["polled_at", "session_pct", "weekly_pct",
             "session_resets_at", "weekly_resets_at"],
        )
        self.assertIsInstance(status["polled_at"], str)
        self.assertIsInstance(status["session_pct"], int)
        self.assertIsInstance(status["weekly_pct"], int)
        self.assertIsInstance(status["session_resets_at"], str)
        self.assertIsInstance(status["weekly_resets_at"], str)


class TestAtomicWrite(unittest.TestCase):
    def test_writes_final_file_and_leaves_no_tmp(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "state" / "usage" / "status.json"
            obj = {"polled_at": "2026-07-17T14:32:00Z", "session_pct": 42,
                   "weekly_pct": 68, "session_resets_at": "2026-07-17T19:00:00Z",
                   "weekly_resets_at": "2026-07-21T00:00:00Z"}
            up.atomic_write_json(path, obj)
            self.assertEqual(json.loads(path.read_text()), obj)
            self.assertFalse(pathlib.Path(str(path) + ".tmp").exists())

    def test_uses_tmp_then_rename(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "status.json"
            seen = {}
            real_rename = os.rename

            def spy_rename(src, dst):
                seen["src"], seen["dst"] = str(src), str(dst)
                seen["tmp_existed"] = pathlib.Path(src).exists()
                seen["dest_absent"] = not pathlib.Path(dst).exists()
                return real_rename(src, dst)

            os.rename = spy_rename
            try:
                up.atomic_write_json(path, {"a": 1})
            finally:
                os.rename = real_rename
            self.assertEqual(seen["src"], str(path) + ".tmp")
            self.assertEqual(seen["dst"], str(path))
            self.assertTrue(seen["tmp_existed"])
            self.assertTrue(seen["dest_absent"])


class TestPollOrchestration(unittest.TestCase):
    def _paths(self, d):
        return (pathlib.Path(d) / "state" / "usage" / "status.json",
                pathlib.Path(d) / "logs" / "usage_poll.log")

    def test_successful_poll_writes_cache(self):
        with tempfile.TemporaryDirectory() as d:
            cache_path, log_path = self._paths(d)
            up.poll(cache_path, log_path, storage_state_path="/unused",
                    now=datetime(2026, 7, 17, 14, 32, tzinfo=timezone.utc),
                    fetch=lambda ssp: ("https://claude.ai/settings/usage",
                                       SAMPLE_USAGE_HTML))
            data = json.loads(cache_path.read_text())
            self.assertEqual(data["session_pct"], 42)
            self.assertEqual(data["weekly_pct"], 68)
            self.assertEqual(data["polled_at"], "2026-07-17T14:32:00Z")

    def test_login_redirect_leaves_existing_cache_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            cache_path, log_path = self._paths(d)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text('{"stale": true}')
            up.poll(cache_path, log_path, storage_state_path="/unused",
                    fetch=lambda ssp: ("https://claude.ai/login", "<h1>Sign in</h1>"))
            self.assertEqual(json.loads(cache_path.read_text()), {"stale": True})
            self.assertIn("login", log_path.read_text())

    def test_dom_drift_leaves_cache_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            cache_path, log_path = self._paths(d)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text('{"stale": true}')
            up.poll(cache_path, log_path, storage_state_path="/unused",
                    fetch=lambda ssp: ("https://claude.ai/settings/usage",
                                       "<h1>totally different page</h1>"))
            self.assertEqual(json.loads(cache_path.read_text()), {"stale": True})
            self.assertIn("parse", log_path.read_text().lower())

    def test_fetch_error_leaves_cache_untouched_and_does_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            cache_path, log_path = self._paths(d)

            def boom(ssp):
                raise RuntimeError("browser crashed")

            up.poll(cache_path, log_path, storage_state_path="/unused", fetch=boom)
            self.assertFalse(cache_path.exists())
            self.assertIn("browser/fetch error", log_path.read_text())
```

- [ ] **Step 2: Run test to verify it fails**

```
cd payload/tools/tests && python3 -m unittest test_usage_poll -v
```
Expected failure: `AttributeError: module 'usage_poll' has no attribute
'build_status'` (and `atomic_write_json` / `poll`) across the three new classes.

- [ ] **Step 3: Write minimal implementation**

Append to `payload/tools/usage_poll.py` (after `_fetch_page_text`):

```python
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
```

Grammar note: the log strings above are diagnostic (written to the log file,
never surfaced in-session). They are proofread regardless — "cache left
untouched" and "re-run 'usage_poll.py --login'" read cleanly, no double spaces,
no number-adjacent a/an, consistent tense. Task 4 asserts no-double-space
hygiene on one of them.

- [ ] **Step 4: Run test to verify it passes**

```
cd payload/tools/tests && python3 -m unittest test_usage_poll -v
```
Expected: `Ran 16 tests ... OK` (8 prior + TestBuildStatus ×2 + TestAtomicWrite
×2 + TestPollOrchestration ×4).

- [ ] **Step 5: Commit**

```
git add payload/tools/usage_poll.py payload/tools/tests/test_usage_poll.py
git commit -m "feat(usage-poll): atomic status.json write + poll() orchestration

(1) Task & Change
Poller group Task 3. Adds build_status() (adds polled_at, returns the exact
5-field status.json in spec key order), atomic_write_json() (.tmp sibling +
os.rename so the hook never sees a partial file), and poll() — the headless
orchestration that writes the cache on success and, on a login redirect / DOM
drift / fetch error / unwritable cache, logs one line and leaves the existing
cache untouched. poll() never raises. Together these lock the status.json
contract the usage-budget hook (Task 6) consumes.

(2) Tests created or modified
- payload/tools/tests/test_usage_poll.py — added TestBuildStatus (polled_at ISO-Z
  format; exact key order + types), TestAtomicWrite (final file written, no .tmp
  leftover; tmp-then-rename verified via an os.rename spy) and TestPollOrchestration
  (success writes cache; login redirect, DOM drift, and fetch error each leave an
  existing cache untouched and log, without raising).

(3) Test results — evidence
$ cd payload/tools/tests && python3 -m unittest test_usage_poll -v
Ran 16 tests in 0.0XXs
OK

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: CLI surface (`--login` vs default `--poll`) + schema-lock/hygiene tests

**Files:**
- Modify: `payload/tools/usage_poll.py` (append `build_arg_parser`, `main`, `__main__`)
- Test: `payload/tools/tests/test_usage_poll.py` (append three test classes)

**Interfaces:**
- Consumes: `login` (Task 1), `poll`, `resolve_paths`, `log_line` (Tasks 1/3).
- Produces:
  - `build_arg_parser() -> argparse.ArgumentParser` — a mutually exclusive
    `--login` / `--poll` group; default (no flag) = poll.
  - `main(argv=None) -> int` — resolves paths, dispatches to `login()` or
    `poll()`, is fail-open (any top-level exception is logged; always returns 0).
  - `if __name__ == "__main__": sys.exit(main())`.

- [ ] **Step 1: Write the failing test**

Append to `payload/tools/tests/test_usage_poll.py` (above `if __name__`):

```python
class TestCli(unittest.TestCase):
    def test_default_mode_is_poll(self):
        self.assertFalse(up.build_arg_parser().parse_args([]).login)

    def test_login_flag_selects_login(self):
        self.assertTrue(up.build_arg_parser().parse_args(["--login"]).login)

    def test_login_and_poll_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            up.build_arg_parser().parse_args(["--login", "--poll"])

    def test_main_dispatches_to_poll_by_default(self):
        called = {}
        orig_poll, orig_login = up.poll, up.login
        up.poll = lambda *a, **k: called.setdefault("poll", True)
        up.login = lambda *a, **k: called.setdefault("login", True)
        try:
            rc = up.main([])
        finally:
            up.poll, up.login = orig_poll, orig_login
        self.assertEqual(rc, 0)
        self.assertTrue(called.get("poll"))
        self.assertNotIn("login", called)

    def test_main_dispatches_to_login_on_flag(self):
        called = {}
        orig_poll, orig_login = up.poll, up.login
        up.poll = lambda *a, **k: called.setdefault("poll", True)
        up.login = lambda *a, **k: (called.setdefault("login", True),
                                    pathlib.Path("/x"))[1]
        try:
            rc = up.main(["--login"])
        finally:
            up.poll, up.login = orig_poll, orig_login
        self.assertEqual(rc, 0)
        self.assertTrue(called.get("login"))
        self.assertNotIn("poll", called)


class TestSchemaLock(unittest.TestCase):
    """Locks the exact status.json contract the usage-budget hook (Task 6) reads.
    If this test breaks, the hook's cache read breaks with it."""

    def test_end_to_end_schema_matches_spec_verbatim(self):
        with tempfile.TemporaryDirectory() as d:
            cache_path = pathlib.Path(d) / "state" / "usage" / "status.json"
            log_path = pathlib.Path(d) / "logs" / "usage_poll.log"
            up.poll(cache_path, log_path, storage_state_path="/unused",
                    now=datetime(2026, 7, 17, 14, 32, tzinfo=timezone.utc),
                    fetch=lambda ssp: ("https://claude.ai/settings/usage",
                                       SAMPLE_USAGE_HTML))
            data = json.loads(cache_path.read_text())
            self.assertEqual(
                list(data.keys()),
                ["polled_at", "session_pct", "weekly_pct",
                 "session_resets_at", "weekly_resets_at"])
            self.assertEqual(data, {
                "polled_at": "2026-07-17T14:32:00Z",
                "session_pct": 42,
                "weekly_pct": 68,
                "session_resets_at": "2026-07-17T19:00:00Z",
                "weekly_resets_at": "2026-07-21T00:00:00Z",
            })


class TestLogDiagnosticHygiene(unittest.TestCase):
    def test_log_messages_have_no_double_spaces(self):
        with tempfile.TemporaryDirectory() as d:
            log_path = pathlib.Path(d) / "logs" / "usage_poll.log"
            up.log_line(
                log_path,
                "poll aborted: claude.ai redirected to login; session expired, "
                "cache left untouched — re-run 'usage_poll.py --login'")
            # strip the leading "YYYY-...Z " timestamp, then check the message body
            msg = log_path.read_text().split(" ", 1)[1]
            self.assertNotIn("  ", msg)
```

- [ ] **Step 2: Run test to verify it fails**

```
cd payload/tools/tests && python3 -m unittest test_usage_poll -v
```
Expected failure: `AttributeError: module 'usage_poll' has no attribute
'build_arg_parser'` (and `main`) across `TestCli`. (`TestLogDiagnosticHygiene`
and `TestSchemaLock` pass already — they exercise Task-1/3 functions — but the
run as a whole is red until `build_arg_parser`/`main` exist.)

- [ ] **Step 3: Write minimal implementation**

Append to `payload/tools/usage_poll.py` (at the end of the file):

```python
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
```

Grammar note: the only stdout string this task adds is the `--login`
confirmation `f"Saved claude.ai session to {path}"` — a simple, correct
past-tense sentence with no number-adjacent a/an and no double space. It prints
the file **path**, never the file's secret contents. `TestLogDiagnosticHygiene`
guards the diagnostic log copy against a double-space regression.

- [ ] **Step 4: Run test to verify it passes**

```
cd payload/tools/tests && python3 -m unittest test_usage_poll -v
```
Expected: `Ran 23 tests ... OK` (16 prior + TestCli ×5 + TestSchemaLock ×1 +
TestLogDiagnosticHygiene ×1).

- [ ] **Step 5: Commit**

```
git add payload/tools/usage_poll.py payload/tools/tests/test_usage_poll.py
git commit -m "feat(usage-poll): argparse CLI (--login vs default --poll) + main dispatch

(1) Task & Change
Poller group Task 4. Adds build_arg_parser() (mutually exclusive --login/--poll,
default = poll) and a fail-open main() that resolves the METRICS_DIR paths,
dispatches to login() or poll(), logs any top-level error, and always returns 0
so launchd is never broken. Adds a schema-lock test that pins the exact
status.json contract the usage-budget hook (Task 6) reads, and a diagnostic-log
hygiene test.

(2) Tests created or modified
- payload/tools/tests/test_usage_poll.py — added TestCli (default mode is poll;
  --login selects login; --login/--poll are mutually exclusive; main() dispatches to
  poll by default and to login on the flag), TestSchemaLock (end-to-end poll writes
  the exact 5-field status.json in spec key order), and TestLogDiagnosticHygiene
  (log copy has no double spaces).

(3) Test results — evidence
$ cd payload/tools/tests && python3 -m unittest test_usage_poll -v
Ran 23 tests in 0.0XXs
OK

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: launchd plist + MANIFEST/CHANGELOG/INSTALL wiring (+ Ryan-gated install)

**Files:**
- Create: `payload/launchd/com.hdc.claude-agent-loop.usage-poll.plist`
- Modify: `payload/MANIFEST` (add `link-file tools/usage_poll.py` + a new `launchd/` block)
- Modify: `CHANGELOG.md` (new `### Added` bullet under `## [Unreleased]`)
- Modify: `INSTALL.md` (new `## Usage-budget poller (one-time)` section before `## How to undo`)
- Test: `payload/tools/tests/test_usage_poll.py` (append `TestLaunchdAndManifest`)

**Interfaces:**
- Consumes: `payload/tools/usage_poll.py` (Tasks 1–4) — the plist runs it with `--poll`.
- Produces: the installed-but-not-loaded plist template, the MANIFEST link entries
  (so `install.sh` symlinks the tool + plist into `~/.claude/`), and the docs.
  No Python interface is produced.

Note on scope: the README.md / ARCHITECTURE.md **hooks table** row and the
`payload/fragments/settings.fragment.json` `PostToolUse` entry belong to the
**hook** (Task 6), not the poller — they are deliberately excluded here. This
task's CHANGELOG bullet is poller-scoped; the hook group appends its own bullet
(the two may be merged into one release entry at version-cut time).

- [ ] **Step 1: Write the failing test**

Append to `payload/tools/tests/test_usage_poll.py` (above `if __name__`):

```python
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]  # tests->tools->payload->root


class TestLaunchdAndManifest(unittest.TestCase):
    PLIST = REPO_ROOT / "payload" / "launchd" / "com.hdc.claude-agent-loop.usage-poll.plist"
    MANIFEST = REPO_ROOT / "payload" / "MANIFEST"

    def test_plist_exists_and_lints(self):
        self.assertTrue(self.PLIST.exists(), f"missing {self.PLIST}")
        import shutil, subprocess
        if shutil.which("plutil"):  # macOS only; skip the lint on Linux CI
            r = subprocess.run(["plutil", "-lint", str(self.PLIST)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_plist_label_interval_and_poll_mode(self):
        body = self.PLIST.read_text()
        self.assertIn("<string>com.hdc.claude-agent-loop.usage-poll</string>", body)
        self.assertIn("<integer>600</integer>", body)   # USAGE_BUDGET_POLL_SECS
        self.assertIn("--poll", body)
        self.assertIn("usage_poll.py", body)

    def test_manifest_links_tool_and_plist(self):
        lines = self.MANIFEST.read_text().splitlines()
        self.assertIn("link-file tools/usage_poll.py", lines)
        self.assertIn(
            "link-file launchd/com.hdc.claude-agent-loop.usage-poll.plist", lines)
```

- [ ] **Step 2: Run test to verify it fails**

```
cd payload/tools/tests && python3 -m unittest test_usage_poll -v
```
Expected failure: `TestLaunchdAndManifest.test_plist_exists_and_lints` →
`AssertionError: missing .../payload/launchd/com.hdc.claude-agent-loop.usage-poll.plist`,
and `test_manifest_links_tool_and_plist` → `AssertionError` (the two link-file
lines are absent).

- [ ] **Step 3: Write minimal implementation**

(a) Create `payload/launchd/com.hdc.claude-agent-loop.usage-poll.plist`. It runs
the poller through a login shell so `$HOME` resolves (launchd does not expand
`~` or env refs inside plist paths); the poller writes its own diagnostics to
`$METRICS_DIR/logs/usage_poll.log`, so the plist's StandardError/Out only catch
launchd-level failures before Python starts:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hdc.claude-agent-loop.usage-poll</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-lc</string>
        <string>exec /usr/bin/env python3 "$HOME/.claude/tools/usage_poll.py" --poll</string>
    </array>
    <key>StartInterval</key>
    <integer>600</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Background</string>
    <key>StandardOutPath</key>
    <string>/tmp/com.hdc.claude-agent-loop.usage-poll.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/com.hdc.claude-agent-loop.usage-poll.err.log</string>
</dict>
</plist>
```

(b) Edit `payload/MANIFEST`. In the `# --- tools/ (top-level files) ---` block,
add the tool line immediately after `link-file tools/themes_pending.py` (keeping
alphabetical order, right before `link-dir tools/templates`):

```
link-file tools/themes_pending.py
link-file tools/usage_poll.py
link-dir tools/templates
```

Then add a new block immediately after the `link-dir tools/tests` line:

```
# --- launchd/ ---------------------------------------------------------------
link-file launchd/com.hdc.claude-agent-loop.usage-poll.plist
```

(`tools/tests` is already `link-dir`'d, so `test_usage_poll.py` installs
automatically — it needs no MANIFEST line of its own.)

(c) Edit `CHANGELOG.md`. Under `## [Unreleased]` → `### Added`, add this bullet
(modeled on the 2.1.0 `context-budget.sh` entry — bold name + path + event,
em-dash, mechanism, fail-open + covering test):

```
- **Usage-budget poller** (`payload/tools/usage_poll.py`, launchd job
  `com.hdc.claude-agent-loop.usage-poll`) — an out-of-band poller that reads the
  account's session- and weekly-limit percentages from claude.ai's usage page
  through a persisted Playwright session and atomically writes
  `~/.claude/metrics/state/usage/status.json` every 10 minutes, so the
  usage-budget hook can warn before a subscription limit is exhausted. Fail-open:
  any poll failure is logged to `usage_poll.log` and leaves the existing cache
  untouched, and the process always exits 0. Auth is a one-time
  `usage_poll.py --login`; loading the launchd job is a manual `launchctl
  bootstrap` step (see INSTALL.md). Covered by the 23-case
  `payload/tools/tests/test_usage_poll.py`.
```

(d) Edit `INSTALL.md`. Insert a new section immediately before the `## How to
undo` heading:

```
## Usage-budget poller (one-time)

The usage-budget poller (`tools/usage_poll.py`) needs two manual, one-time steps
that `install.sh` deliberately does not perform — it authenticates a real browser
session and loads a user-level launchd job, neither of which the MANIFEST symlink
mechanism touches.

1. **Authenticate once.** Run the poller in login mode; a browser window opens.
   Log in to claude.ai, open the usage page, then return to the terminal and press
   Enter:

   ```bash
   python3 ~/.claude/tools/usage_poll.py --login
   ```

   This writes `~/.claude-agent-loop/usage-session.json` — a persisted Playwright
   session (cookies + localStorage). Treat it exactly like `secrets.env`: it lives
   outside the repo, under your home directory, and must never be committed,
   printed, or logged in full. There is no repo `.gitignore` line for it because it
   is not inside the repo; this note is its safeguard.

2. **Load the launchd job.** Copy the plist template into `~/Library/LaunchAgents/`
   and bootstrap it so macOS runs `usage_poll.py --poll` every 10 minutes:

   ```bash
   cp ~/.claude/launchd/com.hdc.claude-agent-loop.usage-poll.plist \
      ~/Library/LaunchAgents/
   launchctl bootstrap gui/$(id -u) \
      ~/Library/LaunchAgents/com.hdc.claude-agent-loop.usage-poll.plist
   ```

   Confirm it is loaded:

   ```bash
   launchctl list | grep usage-poll
   ```

If claude.ai's session later expires, the poller logs a login-redirect line to
`~/.claude/metrics/logs/usage_poll.log` and leaves the cache untouched; re-run
step 1 to re-authenticate.
```

Grammar note: every string in (c) and (d) is author-written documentation prose,
proofread — "an out-of-band poller" (vowel-sound "an"), "a persisted Playwright
session", consistent present tense, no double spaces, correct its/it's. No
machine-generated end-user narrative is introduced by this task; the poller's
runtime copy was covered in Tasks 3–4.

- [ ] **Step 4: Run test to verify it passes**

```
cd payload/tools/tests && python3 -m unittest test_usage_poll -v
```
Expected: `Ran 26 tests ... OK` (23 prior + TestLaunchdAndManifest ×3). If
running on macOS, `plutil -lint` returns
`com.hdc.claude-agent-loop.usage-poll.plist: OK`.

- [ ] **Step 5: Commit**

```
git add payload/launchd/com.hdc.claude-agent-loop.usage-poll.plist \
        payload/MANIFEST CHANGELOG.md INSTALL.md \
        payload/tools/tests/test_usage_poll.py
git commit -m "feat(usage-poll): launchd plist template + MANIFEST/INSTALL/CHANGELOG wiring

(1) Task & Change
Poller group Task 5. Adds the launchd user-agent plist template
(com.hdc.claude-agent-loop.usage-poll, StartInterval 600s, runs usage_poll.py
--poll through a login shell so \$HOME resolves), MANIFEST link-file entries for
the tool and the plist (install.sh symlinks both under ~/.claude/ but never loads
the job), the CHANGELOG Added bullet, and the INSTALL.md 'Usage-budget poller
(one-time)' section documenting the --login auth and launchctl bootstrap steps
plus the storageState secrets-handling note. install.sh is confirmed to never
touch launchd; loading the job is a manual, Ryan-gated step.

(2) Tests created or modified
- payload/tools/tests/test_usage_poll.py — added TestLaunchdAndManifest: the plist
  exists and passes 'plutil -lint' (skipped where plutil is absent); its Label,
  StartInterval 600, and --poll invocation are present; MANIFEST carries the two new
  link-file lines. Docs (CHANGELOG/INSTALL) are non-executable — evidence is this
  test plus the manual verification recorded below.

(3) Test results — evidence
$ cd payload/tools/tests && python3 -m unittest test_usage_poll -v
Ran 26 tests in 0.0XXs
OK
$ plutil -lint payload/launchd/com.hdc.claude-agent-loop.usage-poll.plist
payload/launchd/com.hdc.claude-agent-loop.usage-poll.plist: OK

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Manual step (Ryan-gated, not automatable — the poller group's exit criteria)

A subagent implementer cannot interactively log into a browser, cannot install a
user-level launchd job under Ryan's own GUI session, and cannot hit the real
claude.ai. These steps are Ryan's, run once on the real machine, and their
output is pasted back into the plan as the poller group's completion evidence
(spec lines 361–372, 276–279):

1. **Install the framework so the symlinks exist:** `bash install.sh --no-plugins`
   (or the manual MANIFEST step in INSTALL.md §2), then confirm
   `~/.claude/tools/usage_poll.py` and
   `~/.claude/launchd/com.hdc.claude-agent-loop.usage-poll.plist` are symlinks
   into the repo.
2. **Install the Python Playwright dependency** (first Python-native Playwright
   use in this repo — the existing `playwright` MCP is the JS/npm server, a
   separate thing): `python3 -m pip install playwright && python3 -m playwright
   install chromium`.
3. **Authenticate once:** `python3 ~/.claude/tools/usage_poll.py --login`,
   log in, open the usage page, press Enter. Confirm
   `~/.claude-agent-loop/usage-session.json` now exists (and never commit it).
4. **Run one headless poll:** `python3 ~/.claude/tools/usage_poll.py --poll`,
   then `cat ~/.claude/metrics/state/usage/status.json` and confirm the five
   fields hold plausible values matching what claude.ai's usage page shows at
   that moment.
5. **Load the launchd job:** the `cp` + `launchctl bootstrap` commands from
   INSTALL.md §"Usage-budget poller (one-time)", then
   `launchctl list | grep usage-poll` and confirm the job is listed. Paste that
   line as evidence.
6. **Confirm the schedule ran:** after ~10 minutes, re-check `status.json`'s
   `polled_at` advanced and that `usage_poll.log` shows no repeated errors.

Only after steps 3–5 pass on the real rig is the poller group "done" and the hook
group (Task 6) unblocked to run its shell tests against a real `status.json`.
```


---

## Hook Group (Tasks 6–10)

Built after the poller group per the phasing constraint above. Consumes `status.json` read-only; performs no network calls of its own.

### Task 6: Bash wrapper + Python heredoc skeleton (read-only cache read, fail-open, state I/O)

**Files:**
- Create: `payload/hooks/usage-budget.sh`

**Interfaces:**
- Consumes (from Tasks 1–5): the cache file `$METRICS_DIR/state/usage/status.json`
  with the schema pinned in the group header above. This task reads it and
  never writes it.
- Produces (relied on by Task 7): a complete bash wrapper (kill switch,
  `HOOK_JSON`/`METRICS_DIR` env plumbing, `python3 <<'PY' … PY || true`, final
  `exit 0`) plus, inside the heredoc, the `bail()` fail-open helper, the
  `int_env()` reader, sanitized `safe` session id, the path constants
  (`status_path`, `state_path`, `ckpt_path`, `session_dir`, `ckpt_dir`),
  defensive per-session `state` load + `save_state()` + `reset_state()`, and
  `read_status() -> (pct, reset_at)` (or `(None, None)` when the cache is
  missing/unreadable/malformed/stale, or has no usable percentage). `pct` is an
  `int`; `reset_at` is the reset timestamp of the *binding* (higher) ceiling.

- [ ] **Step 1: Write the failing test.** No test file yet (the durable suite is
  Task 9); drive the skeleton's fail-open contract with a real inline check.
  Run from the repo root:
  ```bash
  T="$(mktemp -d)"; export METRICS_DIR="$T/metrics"; mkdir -p "$METRICS_DIR/state/usage"
  H="payload/hooks/usage-budget.sh"
  echo "--- missing cache -> silent"
  printf '{"session_id":"probe"}' | bash "$H"; echo "rc=$?"
  echo "--- DISABLE -> silent"
  printf '{"session_id":"probe"}' | USAGE_BUDGET_DISABLE=1 bash "$H"; echo "rc=$?"
  echo "--- missing session_id -> silent"
  printf '{}' | bash "$H"; echo "rc=$?"
  echo "--- sanitization -> state file at sanitized path"
  printf '{"polled_at":"%s","session_pct":40,"weekly_pct":40}' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$METRICS_DIR/state/usage/status.json"
  printf '{"session_id":"a/b c:d"}' | bash "$H"
  ls "$METRICS_DIR/state/usage/session/a_b_c_d.json" && echo "STATE-OK"
  ```
- [ ] **Step 2: Run test to verify it fails.** Expected failure (file absent):
  ```
  --- missing cache -> silent
  bash: payload/hooks/usage-budget.sh: No such file or directory
  rc=127
  ...
  ls: .../a_b_c_d.json: No such file or directory
  ```
- [ ] **Step 3: Write minimal implementation.** Create
  `payload/hooks/usage-budget.sh` (the state machine is deliberately absent —
  the heredoc computes `pct`/`reset_at`, saves state, and always bails):
  ```bash
  #!/bin/bash
  # usage-budget.sh — PostToolUse hook: read the out-of-band usage poller's
  # cached account-usage status and force a durable pause point before a Claude
  # subscription session or weekly limit is exhausted.
  #
  # After every tool call, reads ONLY the cached JSON the poller last wrote
  # ($METRICS_DIR/state/usage/status.json) — no network, no Playwright, no
  # transcript read — and compares max(session_pct, weekly_pct) against
  # USAGE_BUDGET_WARN_PCT (70) / USAGE_BUDGET_CRIT_PCT (85):
  #   - at 70%: one warning per cycle — steer toward a safe pause point;
  #   - at 85%: a checkpoint directive that repeats on EVERY tool call until a
  #     checkpoint file exists at
  #     $METRICS_DIR/state/usage/checkpoints/<session>.md with
  #     mtime >= int(crit_since).
  # A missing / unreadable / malformed / stale (older than
  # USAGE_BUDGET_STALE_SECS, default 1800s) cache is treated as unknown and the
  # hook stays silent — a stale reading must never fire a directive the live
  # number may no longer support. Dropping back below the warn threshold re-arms
  # both tiers. Fail-open: any internal failure degrades to silence, and the
  # hook always exits 0. Kill switch: USAGE_BUDGET_DISABLE=1.
  set -u

  CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
  METRICS_DIR="${METRICS_DIR:-$CLAUDE_DIR/metrics}"

  if [ "${USAGE_BUDGET_DISABLE:-0}" = "1" ]; then
    exit 0
  fi

  INPUT="$(cat 2>/dev/null || true)"

  HOOK_JSON="$INPUT" METRICS_DIR="$METRICS_DIR" python3 <<'PY' || true
  import datetime
  import json
  import os
  import re
  import sys
  import tempfile
  import time


  def bail():
      """Flush stdout and exit 0 — the hook never blocks a tool call."""
      try:
          sys.stdout.flush()
      except Exception:
          pass
      os._exit(0)


  try:
      raw = os.environ.get("HOOK_JSON", "")
      try:
          data = json.loads(raw) if raw.strip() else {}
          if not isinstance(data, dict):
              data = {}
      except Exception:
          data = {}

      session_id = data.get("session_id")
      if not session_id:
          bail()

      metrics_dir = os.environ.get("METRICS_DIR", "")

      def int_env(name, default):
          try:
              return int(os.environ.get(name, ""))
          except Exception:
              return default

      warn_pct = int_env("USAGE_BUDGET_WARN_PCT", 70)
      crit_pct = int_env("USAGE_BUDGET_CRIT_PCT", 85)
      if warn_pct >= crit_pct:
          warn_pct, crit_pct = 70, 85
      check_secs = int_env("USAGE_BUDGET_CHECK_SECS", 30)
      if check_secs < 0:
          check_secs = 30
      stale_secs = int_env("USAGE_BUDGET_STALE_SECS", 1800)
      if stale_secs <= 0:
          stale_secs = 1800

      safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id))[:128]
      state_dir = os.path.join(metrics_dir, "state", "usage")
      session_dir = os.path.join(state_dir, "session")
      ckpt_dir = os.path.join(state_dir, "checkpoints")
      os.makedirs(session_dir, exist_ok=True)
      os.makedirs(ckpt_dir, exist_ok=True)
      status_path = os.path.join(state_dir, "status.json")
      state_path = os.path.join(session_dir, safe + ".json")
      ckpt_path = os.path.join(ckpt_dir, safe + ".md")

      state = {"last_check_ts": 0.0, "warn_fired": False,
               "crit_since": None, "checkpoint_ack": False}
      try:
          with open(state_path) as fh:
              loaded = json.load(fh)
          if isinstance(loaded, dict):
              if isinstance(loaded.get("last_check_ts"), (int, float)):
                  state["last_check_ts"] = float(loaded["last_check_ts"])
              if isinstance(loaded.get("warn_fired"), bool):
                  state["warn_fired"] = loaded["warn_fired"]
              if isinstance(loaded.get("crit_since"), (int, float)):
                  state["crit_since"] = float(loaded["crit_since"])
              if isinstance(loaded.get("checkpoint_ack"), bool):
                  state["checkpoint_ack"] = loaded["checkpoint_ack"]
      except Exception:
          pass

      def save_state():
          fd, tmp = tempfile.mkstemp(dir=session_dir, prefix=safe + ".", suffix=".tmp")
          try:
              with os.fdopen(fd, "w") as fh:
                  json.dump(state, fh)
              os.replace(tmp, state_path)
          finally:
              if os.path.exists(tmp):
                  try:
                      os.unlink(tmp)
                  except Exception:
                      pass

      def reset_state():
          state["last_check_ts"] = 0.0
          state["warn_fired"] = False
          state["crit_since"] = None
          state["checkpoint_ack"] = False

      def read_status():
          """(pct, reset_at) from a FRESH cache, or (None, None) if unknown.

          pct = max(session_pct, weekly_pct); reset_at is the reset timestamp of
          whichever ceiling is the binding (higher) one. Missing / unreadable /
          malformed / stale cache, or one carrying no usable percentage,
          -> (None, None) -> the hook stays silent.
          """
          try:
              with open(status_path) as fh:
                  cache = json.load(fh)
          except Exception:
              return (None, None)
          if not isinstance(cache, dict):
              return (None, None)
          polled_at = cache.get("polled_at")
          if not isinstance(polled_at, str):
              return (None, None)
          try:
              dt = datetime.datetime.strptime(polled_at, "%Y-%m-%dT%H:%M:%SZ")
              dt = dt.replace(tzinfo=datetime.timezone.utc)
          except Exception:
              return (None, None)
          if time.time() - dt.timestamp() > stale_secs:
              return (None, None)
          s = cache.get("session_pct")
          w = cache.get("weekly_pct")
          s = float(s) if isinstance(s, (int, float)) and not isinstance(s, bool) else None
          w = float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else None
          if s is None and w is None:
              return (None, None)
          if w is None or (s is not None and s >= w):
              pct, reset_at = s, cache.get("session_resets_at")
          else:
              pct, reset_at = w, cache.get("weekly_resets_at")
          if pct is None or pct < 0:
              return (None, None)
          if not isinstance(reset_at, str):
              reset_at = "unknown"
          return (int(pct), reset_at)

      pct, reset_at = read_status()

      # (threshold state machine added in Task 7)
      save_state()
      bail()
  except Exception:
      pass
  os._exit(0)
  PY

  exit 0
  ```
- [ ] **Step 4: Run test to verify it passes.** Re-run the Step-1 block. Expected:
  ```
  --- missing cache -> silent
  rc=0
  --- DISABLE -> silent
  rc=0
  --- missing session_id -> silent
  rc=0
  --- sanitization -> state file at sanitized path
  .../metrics/state/usage/session/a_b_c_d.json
  STATE-OK
  ```
  (Every invocation prints nothing to stdout and exits 0; the state file lands
  at the sanitized `a_b_c_d.json` path.)
- [ ] **Step 5: Commit.**
  ```bash
  git add payload/hooks/usage-budget.sh
  git commit -m "feat(hooks): usage-budget skeleton — cache read + fail-open + state I/O

  (1) Task & Change
  Add payload/hooks/usage-budget.sh (Task 6 of the usage-budget hook group):
  the bash wrapper (USAGE_BUDGET_DISABLE kill switch, HOOK_JSON/METRICS_DIR
  plumbing, python3 heredoc, fail-open os._exit(0)) and the read-only skeleton
  — sanitized session id, per-session state load/save/reset, and read_status()
  parsing max(session_pct, weekly_pct) plus the binding reset time from the
  poller's status.json with a USAGE_BUDGET_STALE_SECS freshness gate. No
  threshold/emit logic yet (Task 7). Mirrors context-budget.sh's house style;
  reads only the local cache per the spec (no network, no transcript).

  (2) Tests created or modified
  No durable test file yet (the suite is Task 9). Drove the fail-open contract
  with an inline check: missing cache / USAGE_BUDGET_DISABLE=1 / missing
  session_id all silent+rc0, and session id 'a/b c:d' sanitizes to a_b_c_d.json.

  (3) Test results — evidence
  Inline check: three invocations printed nothing and exited rc=0; state file
  created at metrics/state/usage/session/a_b_c_d.json (STATE-OK).

  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
  git push
  ```

---

### Task 7: Threshold state machine + directive emit (WARN-once / CRIT-repeat-until-ack / reset-on-drop)

This task emits **machine-generated prose shown directly to the agent/user**
(the WARN and CRIT `systemMessage` + `additionalContext`). The exact strings
appear in `emit()` below; the `additionalContext` strings are the spec's Draft
copy (§Firing behavior → Message text) used verbatim. Every string was
proofread per the machine-global grammar-stickler rule (number-aware *a/an*,
subject–verb agreement, its/it's, consistent tense, no double spaces) — no
`a`/`an` immediately precedes a number in any string, `this account's usage
is` and `what's in progress` are correct possessive/contraction usage. Task 8
runs `prose_grammar_gate.py` on these strings and locks them with a
character-for-character regression assertion.

**Files:**
- Modify: `payload/hooks/usage-budget.sh` (replace the Task-6 placeholder tail
  — the two lines `# (threshold state machine added in Task 7)` / `save_state()`
  / `bail()` — with `emit()` and the full state machine).

**Interfaces:**
- Consumes (from Task 6): `read_status() -> (pct, reset_at)`, `state`,
  `save_state()`, `reset_state()`, `warn_pct`, `crit_pct`, `check_secs`,
  `ckpt_path`.
- Produces (relied on by Tasks 8–9): the exact emitted hook-JSON shape
  `{"systemMessage": <str>, "hookSpecificOutput": {"hookEventName":
  "PostToolUse", "additionalContext": <str>}}`, and the firing semantics the
  suite asserts.

- [ ] **Step 1: Write the failing test.** Drive the state machine with a real
  inline check (from repo root):
  ```bash
  T="$(mktemp -d)"; export METRICS_DIR="$T/metrics"; mkdir -p "$METRICS_DIR/state/usage"
  H="payload/hooks/usage-budget.sh"; ST="$METRICS_DIR/state/usage/status.json"
  NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  w(){ printf '{"polled_at":"%s","session_pct":%s,"weekly_pct":%s,"session_resets_at":"2026-07-17T19:00:00Z","weekly_resets_at":"2026-07-21T00:00:00Z"}' "$NOW" "$1" "$2" > "$ST"; }
  export USAGE_BUDGET_CHECK_SECS=0
  echo "--- WARN fires once"; w 70 10
  printf '{"session_id":"w"}' | bash "$H"; echo
  printf '{"session_id":"w"}' | bash "$H"; echo   # expect empty (no repeat)
  echo "--- CRIT repeats"; w 86 10
  printf '{"session_id":"c"}' | bash "$H"; echo
  printf '{"session_id":"c"}' | bash "$H"; echo   # expect a second CRIT
  ```
- [ ] **Step 2: Run test to verify it fails.** With the Task-6 skeleton (no
  emit) every invocation is silent — expected failure is four blank lines where
  the first and both CRIT lines should carry JSON:
  ```
  --- WARN fires once

  
  --- CRIT repeats

  
  ```
- [ ] **Step 3: Write minimal implementation.** In `payload/hooks/usage-budget.sh`,
  replace the placeholder tail
  ```python
      pct, reset_at = read_status()

      # (threshold state machine added in Task 7)
      save_state()
      bail()
  ```
  with:
  ```python
      def emit(tier, pct, reset_at):
          if tier == "warn":
              msg = ("Usage budget: account usage at %d%% of the weekly/session "
                     "limit. Steering toward a pause point." % pct)
              ctx = ("Usage-budget warning: this account's usage is at %d%% of "
                     "its weekly/session limit. Consider steering toward a safe "
                     "pause point in the next hour." % pct)
          else:
              msg = ("Usage budget CRITICAL: account usage at %d%%. Checkpoint "
                     "required." % pct)
              ctx = ("Usage-budget CRITICAL: usage is at %d%%, close to the "
                     "account limit (resets %s). Stop new work, commit and push "
                     "what's in progress, and write a checkpoint file at %s — "
                     "this message will repeat until you do."
                     % (pct, reset_at, ckpt_path))
          out = {
              "systemMessage": msg,
              "hookSpecificOutput": {
                  "hookEventName": "PostToolUse",
                  "additionalContext": ctx,
              },
          }
          sys.stdout.write(json.dumps(out))

      pct, reset_at = read_status()
      now = time.time()

      # Critical tier active and unacknowledged: verify the checkpoint, re-arm,
      # or repeat the directive. No throttle at this tier.
      if state["crit_since"] is not None and not state["checkpoint_ack"]:
          try:
              ck_mtime = os.path.getmtime(ckpt_path)
          except Exception:
              ck_mtime = None
          if ck_mtime is not None and ck_mtime >= int(state["crit_since"]):
              state["checkpoint_ack"] = True
              save_state()
              bail()
          if pct is None:
              bail()  # fail-open: unknown/stale usage, no nag this call
          if pct < warn_pct:
              reset_state()  # usage dropped back: re-arm both tiers
              save_state()
              bail()
          emit("crit", pct, reset_at)
          bail()

      # Normal path: throttled measurement.
      if now - state["last_check_ts"] < check_secs:
          bail()
      state["last_check_ts"] = now
      if pct is None:
          save_state()
          bail()
      if pct >= crit_pct:
          if state["crit_since"] is None:
              state["crit_since"] = now
              save_state()
              emit("crit", pct, reset_at)
          else:
              # crit_since set with checkpoint_ack true: the acknowledgment
              # holds until usage drops below the warn threshold.
              save_state()
          bail()
      if pct >= warn_pct:
          if not state["warn_fired"]:
              state["warn_fired"] = True
              save_state()
              emit("warn", pct, reset_at)
          else:
              save_state()
          bail()
      if state["warn_fired"] or state["crit_since"] is not None or state["checkpoint_ack"]:
          reset_state()
      save_state()
      bail()
  ```
- [ ] **Step 4: Run test to verify it passes.** Re-run the Step-1 block. Expected:
  ```
  --- WARN fires once
  {"systemMessage": "Usage budget: account usage at 70% of the weekly/session limit. Steering toward a pause point.", "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "Usage-budget warning: this account's usage is at 70% of its weekly/session limit. Consider steering toward a safe pause point in the next hour."}}
  
  --- CRIT repeats
  {"systemMessage": "Usage budget CRITICAL: account usage at 86%. Checkpoint required.", "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "Usage-budget CRITICAL: usage is at 86%, close to the account limit (resets 2026-07-17T19:00:00Z). Stop new work, commit and push what's in progress, and write a checkpoint file at <…>/checkpoints/c.md — this message will repeat until you do."}}
  {"systemMessage": "Usage budget CRITICAL: account usage at 86%. Checkpoint required.", ...}
  ```
  (WARN fires on the first `w` call and is empty on the second; CRIT fires on
  both `c` calls. The `86 10` fixture makes the session ceiling binding, so the
  reset time shown is `session_resets_at`.)
- [ ] **Step 5: Commit.**
  ```bash
  git add payload/hooks/usage-budget.sh
  git commit -m "feat(hooks): usage-budget state machine — WARN once, CRIT repeat-until-ack, re-arm

  (1) Task & Change
  Replace the Task-6 placeholder tail in payload/hooks/usage-budget.sh with the
  threshold state machine (Task 7), mirroring context-budget.sh line-for-line
  against the poller's cached percentage: WARN once per cycle at 70%, CRIT from
  85% repeating un-throttled on every tool call until a checkpoint file's mtime
  is >= crit_since, reset-on-drop re-arm below the warn threshold, and the
  30s USAGE_BUDGET_CHECK_SECS throttle on the normal path (bypassed while CRIT
  is active-and-unacknowledged). emit() carries the exact WARN/CRIT systemMessage
  + additionalContext strings (spec Draft copy, proofread).

  (2) Tests created or modified
  No durable test file yet (the suite is Task 9). Drove behavior with an inline
  check: WARN fires once then is silent; CRIT fires and repeats.

  (3) Test results — evidence
  Inline check: first 'w' call emitted the WARN hook JSON, second was empty;
  both 'c' calls emitted the CRIT hook JSON naming the checkpoint path. All rc=0.

  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
  git push
  ```

---

### Task 8: Grammar gate + fixed-string regression lock on the emitted directive prose

The hook emits machine-generated end-user prose (Task 7's WARN/CRIT strings).
Per the machine-global grammar-stickler rule, this task is the proofing/lock
step: it runs `prose_grammar_gate.py` on the exact strings as evidence, and
adds a fixed-string, character-for-character regression assertion so a future
copy edit cannot silently reintroduce a grammar defect. (The assertion is also
carried into the durable suite as case 17 in Task 9 — repeated there verbatim.)

**Files:**
- Test: inline grammar-gate run + the fixed-string assertion shown below (folded
  into `payload/tools/tests/test_usage_budget.sh` in Task 9).

**Interfaces:**
- Consumes (from Task 7): the exact emitted WARN/CRIT `systemMessage` +
  `additionalContext` strings.
- Produces: an authoritative record of the exact final strings + a reusable
  fixed-string assertion.

The exact final strings this task locks (shown in code as the assertion's
expected values):
- WARN `systemMessage`: `Usage budget: account usage at 70% of the weekly/session limit. Steering toward a pause point.`
- WARN `additionalContext`: `Usage-budget warning: this account's usage is at 70% of its weekly/session limit. Consider steering toward a safe pause point in the next hour.`
- CRIT `systemMessage`: `Usage budget CRITICAL: account usage at 86%. Checkpoint required.`
- CRIT `additionalContext`: `Usage-budget CRITICAL: usage is at 86%, close to the account limit (resets 2026-07-21T00:00:00Z). Stop new work, commit and push what's in progress, and write a checkpoint file at <ckpt> — this message will repeat until you do.`

- [ ] **Step 1: Write the failing test (prove the guard bites).** First confirm
  the guard rejects a mutated string, then that it accepts the real one. Run
  from repo root:
  ```bash
  T="$(mktemp -d)"; export METRICS_DIR="$T/metrics"; mkdir -p "$METRICS_DIR/state/usage"
  H="payload/hooks/usage-budget.sh"; ST="$METRICS_DIR/state/usage/status.json"
  export USAGE_BUDGET_CHECK_SECS=0
  printf '{"polled_at":"%s","session_pct":10,"weekly_pct":86,"session_resets_at":"2026-07-17T19:00:00Z","weekly_resets_at":"2026-07-21T00:00:00Z"}' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$ST"
  crit_out="$(printf '{"session_id":"c"}' | bash "$H")"
  CKPT="$METRICS_DIR/state/usage/checkpoints/c.md"
  # (a) RED: assert against a mutant with a double space -> must fail
  python3 - "$crit_out" "$CKPT" <<'PYEOF'
  import json, sys
  crit = json.loads(sys.argv[1]); ckpt = sys.argv[2]
  mutant = ("Usage-budget CRITICAL: usage is at 86%,  close to the account limit "
            "(resets 2026-07-21T00:00:00Z). Stop new work, commit and push what's in "
            "progress, and write a checkpoint file at " + ckpt + " — this message will "
            "repeat until you do.")
  assert crit["hookSpecificOutput"]["additionalContext"] == mutant, "MUTANT-REJECTED"
  PYEOF
  echo "mutant assertion rc=$?"
  # (b) prose gate on the exact live strings
  python3 - "$crit_out" <<'PYEOF' > "$T/prose.txt"
  import json, sys
  d = json.loads(sys.argv[1])
  print(d["systemMessage"]); print(d["hookSpecificOutput"]["additionalContext"])
  PYEOF
  python3 ~/.claude/tools/prose_grammar_gate.py "$T/prose.txt"; echo "gate rc=$?"
  ```
- [ ] **Step 2: Run test to verify it fails.** Expected: the mutant assertion
  raises `AssertionError: MUTANT-REJECTED` and prints `mutant assertion rc=1`
  (the guard correctly rejects the double-space mutant — proving the lock
  discriminates). The prose gate prints a clean pass (`gate rc=0`).
- [ ] **Step 3: Write minimal implementation.** No hook code changes — the
  strings already ship from Task 7. This step is the real (non-mutant)
  fixed-string assertion that will live in the suite:
  ```bash
  python3 - "$warn_out" "$crit_out" "$CKPT_DIR/s17c.md" <<'PYEOF'
  import json, sys
  warn = json.loads(sys.argv[1]); crit = json.loads(sys.argv[2]); ckpt = sys.argv[3]
  w_ctx = (
      "Usage-budget warning: this account's usage is at 70% of its weekly/session "
      "limit. Consider steering toward a safe pause point in the next hour."
  )
  c_ctx = (
      "Usage-budget CRITICAL: usage is at 86%, close to the account limit "
      "(resets 2026-07-21T00:00:00Z). Stop new work, commit and push what's in "
      "progress, and write a checkpoint file at " + ckpt + " — this message will "
      "repeat until you do."
  )
  assert warn["hookSpecificOutput"]["additionalContext"] == w_ctx, "warn text drifted"
  assert crit["hookSpecificOutput"]["additionalContext"] == c_ctx, "critical text drifted"
  assert warn["systemMessage"] == "Usage budget: account usage at 70% of the weekly/session limit. Steering toward a pause point."
  assert crit["systemMessage"] == "Usage budget CRITICAL: account usage at 86%. Checkpoint required."
  PYEOF
  ```
- [ ] **Step 4: Run test to verify it passes.** Drive it against real output
  (WARN from a `70 10` fixture, CRIT from a `10 86` fixture, as the suite does
  in Task 9) and confirm the block exits 0 with no `AssertionError`, and
  `prose_grammar_gate.py` reports the strings clean (no number-aware *a/an*
  violation, no double space, subject–verb agreement OK). Expected: `gate rc=0`
  and the assertion block exits 0.
- [ ] **Step 5: Commit.** No repo file changed by this task on its own (the lock
  lands in the suite in Task 9). Record the proofing evidence in Task 9's commit
  body; there is nothing to commit here beyond that. (If a reviewer wants an
  isolated artifact, the assertion is committed as case 17 within Task 9.)

---

### Task 9: Complete test suite — `test_usage_budget.sh` (17 cases, full green run)

**Files:**
- Create: `payload/tools/tests/test_usage_budget.sh`

**Interfaces:**
- Consumes: `payload/hooks/usage-budget.sh` (Tasks 6–7) and the locked prose
  (Task 8).
- Produces: the durable, repeatable regression suite (the group's test
  deliverable), mirroring `test_context_budget.sh`'s structure exactly
  (`mktemp -d` sandbox, `CLAUDE_DIR`/`METRICS_DIR` exports, synthetic
  `status.json` fixtures, `printf payload | bash "$HOOK"`, `pass()`/`die()`).

- [ ] **Step 1: Write the failing test.** Create
  `payload/tools/tests/test_usage_budget.sh` with all 17 cases:
  ```bash
  #!/bin/bash
  # test_usage_budget.sh — PostToolUse usage-budget hook: cached-status read,
  # warn/critical tiers, checkpoint acknowledgment, re-arm, throttling,
  # staleness and fail-open behavior, session-id sanitization, and the
  # fixed-string grammar regression on the emitted directive prose.
  # macOS bash-3.2 portable.
  set -u

  HOOK="$(cd "$(dirname "$0")/../../hooks" && pwd)/usage-budget.sh"
  fail=0
  pass() { echo "PASS - $1"; }
  die() { echo "FAIL - $1"; fail=1; }

  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  export CLAUDE_DIR="$TMP/claude"
  export METRICS_DIR="$TMP/metrics"
  export USAGE_BUDGET_CHECK_SECS=0   # disable throttling unless a case overrides it

  STATUS_DIR="$METRICS_DIR/state/usage"
  SESSION_DIR="$STATUS_DIR/session"
  CKPT_DIR="$STATUS_DIR/checkpoints"
  STATUS="$STATUS_DIR/status.json"
  mkdir -p "$STATUS_DIR"

  # write_status SESSION_PCT WEEKLY_PCT — a FRESH cache (polled_at = now), with
  # fixed, distinct session/weekly reset timestamps.
  write_status() {
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '{"polled_at":"%s","session_pct":%s,"weekly_pct":%s,"session_resets_at":"2026-07-17T19:00:00Z","weekly_resets_at":"2026-07-21T00:00:00Z"}' \
      "$now" "$1" "$2" > "$STATUS"
  }

  # run SESSION_ID — invoke the hook with a well-formed payload; prints stdout.
  run() {
    printf '{"session_id":"%s"}' "$1" | bash "$HOOK"
  }

  # --- 1. below the warn threshold: silent, exit 0 ----------------------------
  write_status 40 40
  out="$(run s1)"; rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "below thresholds is silent"; else die "below thresholds: rc=$rc out=$out"; fi

  # --- 2. warn fires once per cycle -------------------------------------------
  write_status 70 10
  out="$(run s2)"
  case "$out" in *"usage is at 70%"*) pass "warn fires at 70%";; *) die "warn missing: $out";; esac
  out2="$(run s2)"
  if [ -z "$out2" ]; then pass "warn does not repeat"; else die "warn repeated: $out2"; fi

  # --- 3. above warn, below crit: warn (not critical) -------------------------
  write_status 10 84
  out="$(run s3)"
  case "$out" in
    *CRITICAL*) die "critical fired below crit threshold: $out";;
    *"usage is at 84%"*) pass "84% fires warn, not critical";;
    *) die "no warn at 84%: $out";;
  esac

  # --- 4. critical fires and names the checkpoint path ------------------------
  write_status 86 10
  out="$(run s4)"
  case "$out" in *CRITICAL*"$CKPT_DIR/s4.md"*) pass "critical names checkpoint path";; *) die "critical wrong: $out";; esac

  # --- 5. critical repeats while no checkpoint exists -------------------------
  out="$(run s4)"; out2="$(run s4)"
  case "$out" in *CRITICAL*) : ;; *) out="";; esac
  case "$out2" in *CRITICAL*) : ;; *) out2="";; esac
  if [ -n "$out" ] && [ -n "$out2" ]; then pass "critical repeats every call"; else die "critical did not repeat"; fi

  # --- 6. a checkpoint written after crit_since silences the nag; ack holds ---
  echo "resume brief" > "$CKPT_DIR/s4.md"
  out="$(run s4)"
  if [ -z "$out" ]; then pass "checkpoint acknowledges critical"; else die "not silenced: $out"; fi
  out="$(run s4)"
  if [ -z "$out" ]; then pass "acknowledgment holds"; else die "ack did not hold: $out"; fi

  # --- 7. re-arm on drop; fresh critical; back-dated checkpoint rejected -------
  write_status 40 40
  out="$(run s4)"
  if [ -z "$out" ]; then pass "re-arm on drop is silent"; else die "re-arm not silent: $out"; fi
  touch -t 202601010000 "$CKPT_DIR/s4.md"
  write_status 86 10
  out="$(run s4)"
  case "$out" in *CRITICAL*) pass "fresh critical after re-arm";; *) die "no fresh critical: $out";; esac
  out="$(run s4)"
  case "$out" in *CRITICAL*) pass "back-dated checkpoint does not silence";; *) die "back-dated checkpoint silenced: $out";; esac

  # --- 8. metric = max(session_pct, weekly_pct); binding reset time -----------
  write_status 10 88   # weekly is the binding ceiling
  out="$(run s8)"
  case "$out" in
    *CRITICAL*"88%"*"2026-07-21T00:00:00Z"*) pass "max() picks weekly; weekly reset time used";;
    *) die "max/reset selection wrong: $out";;
  esac

  # --- 9. stale cache: silent even at 95% -------------------------------------
  printf '{"polled_at":"2000-01-01T00:00:00Z","session_pct":95,"weekly_pct":95,"session_resets_at":"2026-07-17T19:00:00Z","weekly_resets_at":"2026-07-21T00:00:00Z"}' > "$STATUS"
  out="$(run s9)"; rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "stale cache is silent"; else die "stale cache fired: rc=$rc out=$out"; fi

  # --- 10. missing cache file: silent -----------------------------------------
  rm -f "$STATUS"
  out="$(run s10)"; rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "missing cache is silent"; else die "missing cache: rc=$rc out=$out"; fi

  # --- 11. malformed JSON cache: silent, no crash -----------------------------
  printf 'not json at all' > "$STATUS"
  out="$(run s11)"; rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "malformed cache fails open"; else die "malformed cache: rc=$rc out=$out"; fi

  # --- 12. missing session_id: silent -----------------------------------------
  write_status 90 90
  out="$(printf '{}' | bash "$HOOK")"; rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "missing session_id is silent"; else die "missing session_id: rc=$rc out=$out"; fi

  # --- 13. kill switch ---------------------------------------------------------
  write_status 90 90
  out="$(printf '{"session_id":"s13"}' | USAGE_BUDGET_DISABLE=1 bash "$HOOK")"; rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass "USAGE_BUDGET_DISABLE=1 silences"; else die "kill switch failed: rc=$rc out=$out"; fi

  # --- 14. emitted JSON shape --------------------------------------------------
  write_status 70 10
  out="$(run s14)"
  if printf '%s' "$out" | python3 -c '
  import json, sys
  d = json.load(sys.stdin)
  assert isinstance(d["systemMessage"], str) and d["systemMessage"]
  h = d["hookSpecificOutput"]
  assert h["hookEventName"] == "PostToolUse"
  assert isinstance(h["additionalContext"], str) and h["additionalContext"]
  ' 2>/dev/null; then pass "emitted JSON shape"; else die "bad JSON shape: $out"; fi

  # --- 15. throttling ----------------------------------------------------------
  write_status 40 40   # first call stamps the throttle clock
  out="$(printf '{"session_id":"s15"}' | USAGE_BUDGET_CHECK_SECS=3600 bash "$HOOK")"
  write_status 90 90   # would be critical if measured
  out2="$(printf '{"session_id":"s15"}' | USAGE_BUDGET_CHECK_SECS=3600 bash "$HOOK")"
  if [ -z "$out" ] && [ -z "$out2" ]; then pass "second call inside the window is throttled"; else die "throttle failed: out=$out out2=$out2"; fi

  # --- 16. session-id sanitization ---------------------------------------------
  write_status 40 40
  printf '{"session_id":"%s"}' 'a/b c:d' | bash "$HOOK" >/dev/null
  if [ -f "$SESSION_DIR/a_b_c_d.json" ]; then pass "session-id sanitized into state path"; else die "state file not at sanitized path"; fi

  # --- 17. grammar regression: exact directive strings -------------------------
  write_status 70 10
  warn_out="$(run s17w)"
  write_status 10 86
  crit_out="$(run s17c)"
  if python3 - "$warn_out" "$crit_out" "$CKPT_DIR/s17c.md" <<'PYEOF'
  import json, sys
  warn = json.loads(sys.argv[1])
  crit = json.loads(sys.argv[2])
  ckpt = sys.argv[3]
  w_ctx = (
      "Usage-budget warning: this account's usage is at 70% of its weekly/session "
      "limit. Consider steering toward a safe pause point in the next hour."
  )
  c_ctx = (
      "Usage-budget CRITICAL: usage is at 86%, close to the account limit "
      "(resets 2026-07-21T00:00:00Z). Stop new work, commit and push what's in "
      "progress, and write a checkpoint file at " + ckpt + " — this message will "
      "repeat until you do."
  )
  assert warn["hookSpecificOutput"]["additionalContext"] == w_ctx, "warn text drifted"
  assert crit["hookSpecificOutput"]["additionalContext"] == c_ctx, "critical text drifted"
  assert warn["systemMessage"] == "Usage budget: account usage at 70% of the weekly/session limit. Steering toward a pause point."
  assert crit["systemMessage"] == "Usage budget CRITICAL: account usage at 86%. Checkpoint required."
  PYEOF
  then pass "grammar regression: exact strings"; else die "directive prose drifted from spec"; fi

  echo ""
  if [ "$fail" -eq 0 ]; then
    echo "test_usage_budget: OK"
    exit 0
  else
    echo "test_usage_budget: FAIL"
    exit 1
  fi
  ```
  Then `chmod +x payload/tools/tests/test_usage_budget.sh`.
- [ ] **Step 2: Run test to verify it fails.** To prove the suite discriminates,
  first run it against a hook that has NOT yet had Task 7 applied (or transiently
  comment out `emit(...)` calls): the behavioral cases (2–8, 14, 17) fail.
  Command: `bash payload/tools/tests/test_usage_budget.sh; echo "rc=$?"`.
  Expected (pre-Task-7 state): multiple `FAIL - …` lines (e.g. `FAIL - warn
  missing:`), ending `test_usage_budget: FAIL` / `rc=1`. (With Tasks 6–7 already
  landed, this red state is demonstrated only by the transient emit removal;
  restore it before Step 3.)
- [ ] **Step 3: Write minimal implementation.** No hook change — the suite runs
  against the finished `usage-budget.sh` from Tasks 6–7. (Restore any transiently
  removed `emit(...)` calls used to show red in Step 2.)
- [ ] **Step 4: Run test to verify it passes.** Run:
  ```bash
  bash payload/tools/tests/test_usage_budget.sh; echo "rc=$?"
  ```
  Expected: 17 `PASS - …` lines, then:
  ```
  test_usage_budget: OK
  rc=0
  ```
  Also record the Task-8 proofing evidence here: write the WARN + CRIT strings
  to a temp file and run `python3 ~/.claude/tools/prose_grammar_gate.py <file>`;
  expected a clean pass (no number-aware *a/an* violation, no double space,
  subject–verb agreement OK).
- [ ] **Step 5: Commit.**
  ```bash
  git add payload/tools/tests/test_usage_budget.sh
  git commit -m "test(hooks): 17-case usage-budget suite incl. fixed-string grammar regression

  (1) Task & Change
  Add payload/tools/tests/test_usage_budget.sh (Tasks 8–9): the durable
  regression suite for the usage-budget PostToolUse hook, mirroring
  test_context_budget.sh's structure (mktemp sandbox, CLAUDE_DIR/METRICS_DIR
  exports, synthetic status.json fixtures, printf-payload | bash HOOK,
  pass()/die()). 17 cases: WARN-once, WARN-not-CRIT below 85, CRIT fire + names
  checkpoint path, CRIT repeat, checkpoint ack + hold, re-arm-on-drop + fresh
  CRIT + back-dated-checkpoint rejection, max(session,weekly) + binding reset
  time, stale/missing/malformed cache silence, missing session_id, kill switch,
  emitted-JSON shape, throttling, session-id sanitization, and case 17 — the
  character-for-character grammar-regression lock on the emitted WARN/CRIT prose
  (Task 8). The exact strings were also run through prose_grammar_gate.py.

  (2) Tests created or modified
  - payload/tools/tests/test_usage_budget.sh — the full 17-case suite above.

  (3) Test results — evidence
  bash payload/tools/tests/test_usage_budget.sh
  -> 17x 'PASS - …'; 'test_usage_budget: OK'; rc=0.
  prose_grammar_gate.py on the WARN+CRIT strings: clean pass (rc=0).

  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
  git push
  ```

---

### Task 10: Wiring + docs — MANIFEST, settings fragment, README/ARCHITECTURE/CHANGELOG

**Files:**
- Modify: `payload/MANIFEST` (hooks block, after the `context-budget.sh` line)
- Modify: `payload/fragments/settings.fragment.json` (`PostToolUse` array)
- Modify: `README.md` (hooks table)
- Modify: `ARCHITECTURE.md` (runtime-loop-layer bullets)
- Modify: `CHANGELOG.md` (`[Unreleased]` → `### Added`)

**Interfaces:**
- Consumes: the finished `payload/hooks/usage-budget.sh` (Tasks 6–7).
- Produces: the install wiring that symlinks the hook into `~/.claude/hooks/`
  and registers it on `PostToolUse`, plus the doc rows. (The MANIFEST/plist
  lines and INSTALL.md one-time-setup subsection for `usage_poll.py` belong to
  the poller task group — this task adds ONLY the hook's own wiring to avoid a
  double edit.)

Doc prose below is machine-authored end-user text; proofread per the grammar
rule (checked: "an out-of-band" matches the vowel sound of "out"; "the account's",
"it stays silent", "exists" all agree; no double spaces).

- [ ] **Step 1: Write the failing test.** Config/doc change — evidence-based, no
  unit test. Establish the red state:
  ```bash
  grep -n 'usage-budget.sh' payload/MANIFEST payload/fragments/settings.fragment.json README.md ARCHITECTURE.md CHANGELOG.md; echo "rc=$?"
  ```
  Expected failure: no matches, `rc=1`.
- [ ] **Step 2: Run test to verify it fails.** As above — `rc=1`, no output
  lines. (The hook is built but unwired: nothing references it.)
- [ ] **Step 3: Write minimal implementation.**
  - `payload/MANIFEST` — in the `# --- hooks/ ---` block, add the line
    immediately after `link-file hooks/context-budget.sh`:
    ```
    link-file hooks/usage-budget.sh
    ```
  - `payload/fragments/settings.fragment.json` — replace the `PostToolUse`
    array (currently a single `context-budget.sh` element) with both elements:
    ```json
        "PostToolUse": [
          {
            "hooks": [
              {
                "type": "command",
                "command": "$HOME/.claude/hooks/context-budget.sh"
              }
            ]
          },
          {
            "hooks": [
              {
                "type": "command",
                "command": "$HOME/.claude/hooks/usage-budget.sh"
              }
            ]
          }
        ],
    ```
  - `README.md` — in the "Hooks (the deterministic entries)" table, add this row
    immediately after the `context-budget.sh` row:
    ```
    | `usage-budget.sh` | PostToolUse | Reads the out-of-band usage poller's cached account status and steers the agent to a pause point before a Claude session or weekly subscription limit is exhausted; warns at 70% of the higher of the two ceilings and, from 85%, repeats a checkpoint directive on every tool call until a checkpoint file exists. Stays silent when the cache is missing or stale. |
    ```
  - `ARCHITECTURE.md` — in "### 2. Runtime loop layer …", add this bullet
    immediately after the `context-budget.sh` bullet:
    ```
    - **`payload/hooks/usage-budget.sh`** (PostToolUse) reads a small JSON cache
      that an out-of-band launchd poller (`usage_poll.py`) refreshes every ~10
      minutes with the account's session-limit and weekly-limit percentages, and
      steers the agent to a durable pause point before either Claude subscription
      ceiling is exhausted — one warning at 70% of the higher percentage, then a
      repeating checkpoint directive from 85% until a checkpoint file exists on
      disk. It reads only the cache (never the network), and it stays silent
      whenever that cache is missing or stale. Kill switch: `USAGE_BUDGET_DISABLE=1`.
    ```
    Also add the matching row to the "Hooks (the deterministic entries)" table
    that ARCHITECTURE.md carries (identical to the README row above).
  - `CHANGELOG.md` — under `## [Unreleased]` → `### Added`, prepend:
    ```
    - **Usage-budget hook** (`payload/hooks/usage-budget.sh`, PostToolUse) —
      reads the cached account-usage status that the out-of-band `usage_poll.py`
      launchd poller writes to `~/.claude/metrics/state/usage/status.json`, and
      steers the agent to a durable pause point before a Claude session or weekly
      subscription limit is exhausted: a single warning at 70% of
      `max(session_pct, weekly_pct)`, then a checkpoint directive from 85% that
      repeats on every tool call until a checkpoint file exists at
      `~/.claude/metrics/state/usage/checkpoints/<session>.md`. Reads only the
      local cache (no network in the hot path) and stays silent when the cache is
      missing or older than 30 minutes. Fail-open, always exits 0; kill switch
      `USAGE_BUDGET_DISABLE=1`. Covered by the 17-case
      `payload/tools/tests/test_usage_budget.sh`, including a fixed-string grammar
      regression on the emitted directive prose.
    ```
- [ ] **Step 4: Run test to verify it passes.** Confirm wiring + doc rows landed
  and the fragment is still valid JSON:
  ```bash
  grep -c 'usage-budget.sh' payload/MANIFEST payload/fragments/settings.fragment.json README.md ARCHITECTURE.md CHANGELOG.md
  python3 -m json.tool payload/fragments/settings.fragment.json >/dev/null && echo "FRAGMENT-JSON-OK"
  # regression: the hook suite still passes after wiring
  bash payload/tools/tests/test_usage_budget.sh; echo "rc=$?"
  ```
  Expected: each file reports ≥1 match (MANIFEST 1, fragment 1, README 1,
  ARCHITECTURE 2, CHANGELOG 1); `FRAGMENT-JSON-OK`; `test_usage_budget: OK` /
  `rc=0`.
- [ ] **Step 5: Commit.**
  ```bash
  git add payload/MANIFEST payload/fragments/settings.fragment.json README.md ARCHITECTURE.md CHANGELOG.md
  git commit -m "feat(install): wire usage-budget.sh into MANIFEST, PostToolUse, and docs

  (1) Task & Change
  Wire payload/hooks/usage-budget.sh into the install path and docs (Task 10):
  a link-file MANIFEST entry in the hooks block, a second PostToolUse element in
  settings.fragment.json (alongside context-budget.sh, matcher-less), the
  README/ARCHITECTURE hooks-table row + ARCHITECTURE runtime-loop bullet, and a
  CHANGELOG [Unreleased] Added entry. The usage_poll.py MANIFEST/plist lines and
  the INSTALL.md one-time-setup subsection belong to the poller task group and
  are intentionally not touched here.

  (2) Tests created or modified
  No executable unit test (config/docs). Verified via grep for the wired
  filename across all five files, python3 -m json.tool on the fragment, and a
  full re-run of the hook suite as a regression gate.

  (3) Test results — evidence
  grep -c usage-budget.sh -> MANIFEST 1, fragment 1, README 1, ARCHITECTURE 2,
  CHANGELOG 1. python3 -m json.tool payload/fragments/settings.fragment.json ->
  FRAGMENT-JSON-OK. bash payload/tools/tests/test_usage_budget.sh ->
  test_usage_budget: OK, rc=0.

  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
  git push
  ```
