# Usage-Budget Hook — Design Spec

## Problem

Claude subscription plans carry two usage ceilings: a rolling **session
limit** and a **weekly limit**. Both are visible on claude.ai's usage page,
but nothing local watches them. A long-running or large task can run
straight into either ceiling mid-stream, with no warning and no
pause-and-checkpoint discipline — losing whatever progress hadn't yet been
committed to a durable artifact (a file, a commit, a ledger entry).

`context-budget.sh` already solves the adjacent problem — this session's
*context-window* occupancy — by warning at 70% and escalating to a
repeating critical reminder at 85% until a resume-brief checkpoint file is
written. That pattern is proven and well-liked (see the live
context-budget warning that fired during this very design session). This
feature is the same idea applied to the account-level usage ceiling that
`context-budget.sh` cannot see.

## Goal

Warn Ryan — and any agent in a session — before a Claude subscription
session or weekly usage limit is exhausted, with enough lead time to reach
a safe, resumable pause point: work committed, a checkpoint written,
nothing left stranded in conversational-only state.

## Non-goals

- **Not model-switching.** This feature never changes which model a
  session uses. It only warns and nudges toward a pause point.
- **Not context-window budget.** That signal is already fully handled by
  `context-budget.sh`. This feature reads a completely different number
  (account usage-limit percentage) from a completely different source
  (the claude.ai web console, not the local transcript).
- **Not API spend/billing budget.** Ryan's `six8`/AWS cost-tracking is a
  separate concern with its own tooling; this hook does not touch billing
  data.
- **Not task-size-aware.** Approach B (estimate remaining todo-list size
  against remaining budget) is explicitly deferred. This spec is Approach
  A: pure reactive thresholds on the raw usage percentage, mirroring
  `context-budget.sh`'s own design exactly.

## Signal chosen

The subscription's **session-limit percentage** and **weekly-limit
percentage**, as shown on claude.ai's usage page. The hook's effective
metric is `max(session_pct, weekly_pct)` — whichever ceiling is closer
matters more, since hitting either one halts the session.

## Data source rationale

No official local API or CLI exposes these two percentages. Prior research
in this session confirmed the only reliable read is the claude.ai web
console's usage page, rendered client-side. Screenshot/OCR was considered
and rejected as fragile; a DOM/accessibility-tree read via Playwright
(already an available MCP tool in this environment, and a real npm
dependency) is more robust to minor visual restyling, since it reads text
content and ARIA roles rather than pixels.

Because this requires a real, authenticated browser session against
claude.ai, it cannot run as a fast synchronous `PostToolUse` hook (that
would add multi-second browser-launch latency to every tool call, and
would require the hook's Python subprocess to carry Playwright + a browser
binary into every session's hot path). It is therefore split into two
decoupled components, matching how `context-budget.sh` itself only ever
reads a fast local file (the transcript) rather than a network resource.

## Architecture

Two decoupled components:

1. **`payload/tools/usage_poll.py`** — a standalone poller, run out-of-band
   by a launchd user-agent job on a fixed interval (~10 minutes). It is
   the only component that touches the network or Playwright. It opens
   claude.ai's usage page headlessly using a persisted browser session,
   reads the two percentages plus their reset timestamps from the
   accessibility tree, and atomically writes a small JSON cache file. It
   never talks to a running Claude Code session directly.

2. **`payload/hooks/usage-budget.sh`** — a `PostToolUse` hook, in the same
   bash-wrapper/Python-heredoc house style as `context-budget.sh` and
   `precompact-event.sh`. On every tool call it reads *only* the cached
   JSON file the poller last wrote — no network, no Playwright, no
   meaningful latency — and fires a warning or critical directive based on
   the cached percentage and this session's own per-session fire-state.

This mirrors `context-budget.sh`'s own shape: a hook that does a cheap
local read and a threshold check, decoupled from anything slow. The
difference is that `context-budget.sh`'s "slow part" (parsing a 256 KB
transcript tail) is still cheap enough to inline; a browser launch is not,
so here the slow part is pulled out into its own out-of-band process.

## Data flow

```
launchd (every ~10 min)
  -> usage_poll.py
       -> Playwright, persisted storageState (~/.claude-agent-loop/usage-session.json)
       -> claude.ai/usage (or equivalent), DOM/accessibility-tree read
       -> writes $METRICS_DIR/state/usage/status.json (atomic: tmp + rename)

Claude Code session, any tool call
  -> PostToolUse hook fires
       -> usage-budget.sh
            -> reads $METRICS_DIR/state/usage/status.json (cache only)
            -> reads/writes $METRICS_DIR/state/usage/session/<safe_session_id>.json (fire-state)
            -> checks $METRICS_DIR/state/usage/checkpoints/<safe_session_id>.md mtime (re-arm)
            -> emits WARN / CRIT text on stdout, or stays silent
```

## Components in detail

### `usage_poll.py`

- **Modes:**
  - `--login` — opens a *visible* (non-headless) browser window so Ryan
    can manually authenticate to claude.ai once. On success, persists the
    Playwright `storageState` (cookies + localStorage) to
    `~/.claude-agent-loop/usage-session.json`. This file is gitignored and
    treated exactly like `secrets.env`: never committed, never printed,
    never logged in full.
  - `--poll` (default, what launchd invokes) — headless. Loads the
    persisted `storageState`, navigates to the usage page, reads the
    session-limit % and weekly-limit % (and their reset timestamps) via
    the accessibility tree, and writes the cache.
- **Cache write:** `$METRICS_DIR/state/usage/status.json`, written
  atomically (write to a `.tmp` sibling, then `os.rename`) so the hook
  never observes a partially-written file. Shape:
  ```json
  {
    "polled_at": "2026-07-17T14:32:00Z",
    "session_pct": 42,
    "weekly_pct": 68,
    "session_resets_at": "2026-07-17T19:00:00Z",
    "weekly_resets_at": "2026-07-21T00:00:00Z"
  }
  ```
- **Session expiry:** if the page redirects to a login screen instead of
  showing usage data, the poller logs a one-line warning to its own log
  file (`$METRICS_DIR/logs/usage_poll.log`) and **exits without touching
  the existing cache** — a stale-but-real cache is safer than overwriting
  it with garbage or a zeroed reading that would suppress a warning that
  should have fired.
- **Any other exception** (network failure, Playwright timeout, DOM shape
  changed): caught, logged to the same log file, cache left untouched.
  The poller always exits 0 so a failed poll never breaks the launchd job
  definition.

### `usage-budget.sh`

Same house style as `context-budget.sh`: a thin bash wrapper that reads
stdin (the hook JSON payload) and pipes it, plus `METRICS_DIR`, into a
`python3 <<'PY' || true` heredoc. Kill switch: `USAGE_BUDGET_DISABLE=1`
(checked first, mirroring `CONTEXT_BUDGET_DISABLE=1`).

- **Reads:**
  - `$METRICS_DIR/state/usage/status.json` (the poller's cache).
  - `$METRICS_DIR/state/usage/session/<safe_session_id>.json` (this
    session's own WARN/CRIT fire-state — same `warn_fired` /
    `crit_since`-style shape as `context-budget.sh`'s per-session state).
  - `$METRICS_DIR/state/usage/checkpoints/<safe_session_id>.md` (mtime
    only, for CRIT re-arm).
- **Session-id sanitization:** identical regex to `context-budget.sh` —
  `re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id))[:128]`.
- **Staleness check:** if `status.json` is missing, unreadable, malformed
  JSON, or `polled_at` is older than `USAGE_BUDGET_STALE_SECS` (default
  1800s — three missed 10-minute polls), the hook treats usage as
  **unknown** and stays silent. A stale cache must never be used to fire a
  CRIT the live number might no longer support.
- **Metric:** `pct = max(session_pct, weekly_pct)` from the cache.
- **Thresholds:** `USAGE_BUDGET_WARN_PCT` (default 70) and
  `USAGE_BUDGET_CRIT_PCT` (default 85) — the exact same default values as
  `CONTEXT_BUDGET_WARN_PCT` / `CONTEXT_BUDGET_CRIT_PCT`, for a consistent
  mental model across both hooks.
- **Firing behavior**, mirroring `context-budget.sh` exactly:
  - `pct >= WARN_PCT` and WARN not yet fired this session → emit one WARN
    message, set `warn_fired = true`.
  - `pct >= CRIT_PCT` → emit a CRIT directive. If this is the first time
    CRIT fires, record `crit_since = <now>`. On every subsequent tool
    call, keep repeating the CRIT directive **unless** the checkpoint file
    at `$METRICS_DIR/state/usage/checkpoints/<safe_session_id>.md` has an
    mtime `>= crit_since` — i.e., re-arm only after a checkpoint is
    written *after* CRIT first fired, not before.
  - `USAGE_BUDGET_CHECK_SECS` (default 30, same as
    `CONTEXT_BUDGET_CHECK_SECS`) throttles how often the hook re-reads
    the cache/state files per session, to keep the common case (no
    threshold crossed) cheap.
- **Message text:** WARN and CRIT strings are distinct, fixed strings
  (not templated per-call beyond the percentage and reset time), so the
  shell test suite's grammar regression test has stable text to assert
  against. Draft copy (subject to the grammar gate before shipping):
  - WARN: `"Usage-budget warning: this account's usage is at {pct}% of its weekly/session limit. Consider steering toward a safe pause point in the next hour."`
  - CRIT: `"Usage-budget CRITICAL: usage is at {pct}%, close to the account limit (resets {reset_at}). Stop new work, commit and push what's in progress, and write a checkpoint file at {checkpoint_path} — this message will repeat until you do."`
  - Both strings run through the number-aware a/an and grammar checks
    (`python3 ~/.claude/tools/prose_grammar_gate.py`) before merge, per
    the machine-global grammar-stickler directive, since these are
    machine-generated strings shown directly to an agent/user.

## File locations

| Path | Purpose |
|---|---|
| `payload/tools/usage_poll.py` | The poller (login mode + poll mode) |
| `payload/hooks/usage-budget.sh` | The `PostToolUse` hook |
| `payload/launchd/com.hdc.claude-agent-loop.usage-poll.plist` | launchd user-agent job template (installed by the existing install flow, same as other payload files) |
| `$METRICS_DIR/state/usage/status.json` | Poller's cache (shared across all sessions on the machine) |
| `$METRICS_DIR/state/usage/session/<safe_session_id>.json` | Per-session WARN/CRIT fire-state |
| `$METRICS_DIR/state/usage/checkpoints/<safe_session_id>.md` | Resume-brief checkpoint, written by the agent to re-arm CRIT |
| `$METRICS_DIR/logs/usage_poll.log` | Poller's own error/warning log |
| `~/.claude-agent-loop/usage-session.json` | Gitignored persisted Playwright `storageState` (treated like `secrets.env`) |

## Auth / session persistence

- One-time manual step: run `usage_poll.py --login`, authenticate in the
  visible browser window, close it. This writes
  `~/.claude-agent-loop/usage-session.json`.
- Every subsequent `--poll` run reuses that state — no interactive login
  in the normal path.
- If claude.ai's session eventually expires (cookie TTL, forced re-auth,
  etc.), the poller detects the login-page redirect, logs it, and leaves
  the cache untouched (see above). The cache goes stale, `usage-budget.sh`
  falls silent (per the staleness rule) rather than firing on old data,
  and Ryan re-runs `--login` when he notices the log warning or the
  absence of fresh warnings over an extended period.
- This file is gitignored and excluded from the installer's tracked
  payload the same way `secrets.env` and `.secrets/` are for the 68
  Platform engagement — never committed, never printed in full, redacted
  in any diagnostic output.

## Scheduling

A launchd user-agent plist, installed alongside the other payload files,
runs `usage_poll.py --poll` every `USAGE_BUDGET_POLL_SECS` (default 600s
= 10 minutes) via `StartInterval`. Ten minutes was chosen as a balance:
frequent enough that the cache is never more than one interval stale
relative to the 30-minute staleness cutoff (three missed polls before the
hook goes silent), infrequent enough to avoid hammering claude.ai or
running a browser process too often in the background.

## Thresholds and state

- `USAGE_BUDGET_WARN_PCT` = 70 (default, matches `CONTEXT_BUDGET_WARN_PCT`)
- `USAGE_BUDGET_CRIT_PCT` = 85 (default, matches `CONTEXT_BUDGET_CRIT_PCT`)
- `USAGE_BUDGET_CHECK_SECS` = 30 (default, matches `CONTEXT_BUDGET_CHECK_SECS`)
- `USAGE_BUDGET_STALE_SECS` = 1800 (default; no equivalent in
  `context-budget.sh`, since a transcript file can't go "stale" the way a
  polled cache can)
- `USAGE_BUDGET_POLL_SECS` = 600 (poller-side, not hook-side; consumed by
  the launchd plist template, not by `usage-budget.sh`)
- Metric = `max(session_pct, weekly_pct)` from the cache.
- Per-session fire-state JSON shape (mirrors `context-budget.sh`):
  ```json
  {"last_check_ts": 0.0, "warn_fired": false, "crit_since": null}
  ```

## Error handling

Fail-open in every case, matching `context-budget.sh`'s discipline
exactly:

- `USAGE_BUDGET_DISABLE=1` → hook no-ops immediately.
- Cache missing / unreadable / malformed JSON → silent no-op.
- Cache present but stale (`polled_at` older than
  `USAGE_BUDGET_STALE_SECS`) → treated as absent; silent no-op.
- Per-session state file missing/corrupt → treated as fresh state
  (`warn_fired=false`, `crit_since=null`), never crashes.
- Any unexpected exception in the Python heredoc → defensive
  try/except around the body, hook always exits 0 (`|| true` in the bash
  wrapper is the outer safety net; the Python side should not rely on it
  alone, matching `precompact-event.sh`'s `os._exit(0)` pattern).
- Poller-side exceptions (network, Playwright, DOM-shape drift, expired
  session) → always caught, logged, cache left untouched, poller exits 0.

## Configuration

Environment variables (all optional, all with defaults above):

- `USAGE_BUDGET_DISABLE` — kill switch, mirrors `CONTEXT_BUDGET_DISABLE`.
- `USAGE_BUDGET_WARN_PCT`, `USAGE_BUDGET_CRIT_PCT`, `USAGE_BUDGET_CHECK_SECS`
  — mirror the `CONTEXT_BUDGET_*` equivalents.
- `USAGE_BUDGET_STALE_SECS` — cache staleness cutoff.
- `USAGE_BUDGET_POLL_SECS` — poller interval (consumed by the plist
  template's `StartInterval`, documented here for a single source of
  truth on the number).
- `METRICS_DIR` — already a shared, existing convention; no new variable
  needed, reused as-is.

## Testing plan

- **`payload/tools/tests/test_usage_budget.sh`** — a shell test suite in
  the `test_context_budget.sh`/`test_precompact_tmx.sh` style: `mktemp -d`
  sandbox, `CLAUDE_DIR`/`METRICS_DIR` exports, synthetic `status.json`
  fixtures written directly (no real Playwright involved), `printf payload
  | bash "$HOOK"`, `pass()`/`die()` helpers. Cases include:
  1. Below WARN threshold (69%) → silent.
  2. At WARN threshold (70%) → fires WARN once.
  3. WARN already fired this session → does not repeat.
  4. Below CRIT threshold (84%) → no CRIT.
  5. At CRIT threshold (85%) → fires CRIT.
  6. CRIT repeats on subsequent calls with no checkpoint written.
  7. CRIT stops repeating once a checkpoint file is written with
     mtime ≥ `crit_since`.
  8. CRIT resumes if usage climbs again after a prior checkpoint (fresh
     `crit_since`).
  9. Stale cache (`polled_at` > 30 min old) → silent, even at 95%.
  10. Missing cache file → silent.
  11. Malformed JSON cache → silent, no crash.
  12. `USAGE_BUDGET_DISABLE=1` → silent regardless of cache content.
  13. Grammar regression: the exact WARN and CRIT strings pass
      `prose_grammar_gate.py` (number-aware a/an, no double spaces,
      subject-verb agreement) — a fixed-string assertion so future edits
      to the copy can't silently reintroduce a grammar defect.
- **`payload/tools/tests/test_usage_poll.py`** — a unit test against a
  **mocked** Playwright page (a fixture HTML string resembling the real
  usage page's DOM/ARIA structure) verifying the percentage-extraction and
  reset-timestamp-extraction logic, and verifying the atomic-write
  behavior (temp file + rename, no partial-write window). This test never
  touches the network or a real browser.
- **Manual, one-time verification** (not a repeatable automated test,
  since it requires real network access and a real login): run
  `usage_poll.py --login`, authenticate, then run `usage_poll.py --poll`
  once and confirm `status.json` contains plausible values matching what
  claude.ai's usage page shows at that moment. This step is recorded as
  evidence in the implementation plan's final task, not encoded as CI.

## Deliverables checklist

- [ ] `payload/tools/usage_poll.py` (login mode + poll mode)
- [ ] `payload/hooks/usage-budget.sh`
- [ ] `payload/tools/tests/test_usage_budget.sh` (13 cases above)
- [ ] `payload/tools/tests/test_usage_poll.py` (mocked-Playwright unit test)
- [ ] `payload/launchd/com.hdc.claude-agent-loop.usage-poll.plist` (template)
- [ ] `payload/MANIFEST` — new `link-file hooks/usage-budget.sh` line
      (exact format confirmed at the existing `link-file
      hooks/context-budget.sh` entry) plus an analogous entry for
      `tools/usage_poll.py` and the launchd plist.
- [ ] `payload/fragments/settings.fragment.json` — new `PostToolUse` array
      entry `{"hooks": [{"type": "command", "command":
      "$HOME/.claude/hooks/usage-budget.sh"}]}`, added alongside the
      existing `context-budget.sh` entry in the same `PostToolUse` list.
- [ ] One-line doc updates: README.md hooks table, ARCHITECTURE.md,
      INSTALL.md fragment example, CHANGELOG.md — matching the doc-update
      pattern used for `context-budget.sh`.
- [ ] `.gitignore` entry for `~/.claude-agent-loop/usage-session.json`
      (it lives outside the repo, under the user's home directory, so
      this is a documentation note in INSTALL.md rather than a repo
      `.gitignore` line — flagged here so the plan doesn't drop it).

## Open risks / trade-offs

- **UI-scraping fragility.** claude.ai's usage page can change its DOM
  structure without notice, silently breaking extraction. Mitigated by:
  fail-open behavior (a broken poller just means silence, never a false
  alarm) and a log file Ryan can check if warnings stop appearing.
  Accepted as the only currently-available data source.
- **Session expiry requires manual re-login.** There is no fully
  passive way to detect "the login has silently expired" other than the
  next poll attempt failing. The staleness cutoff (30 min) bounds how
  long a silent failure can go unnoticed before warnings simply stop
  firing — which is itself a detectable (if passive) signal.
- **Ten-minute poll granularity.** Usage can cross a threshold between
  polls; worst case, a WARN/CRIT fires up to ~10 minutes later than the
  true crossing. Given the thresholds (70%/85%) leave meaningful runway
  before exhaustion, this lag is accepted as a reasonable trade-off
  against not running a browser more frequently.
- **Fallback if persistent auth proves too painful in practice.**
  Approach C (on-demand-only scraping, no background poller) remains
  available as a fallback design if the persisted-session approach turns
  out to be unreliable in practice — not built now, noted here so a
  future revision has the alternative on record.
