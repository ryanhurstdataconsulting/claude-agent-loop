# Context-Budget Hook — Design Spec

- **Date:** 2026-07-15
- **Status:** Approved design, pending user review of this written spec
- **Branch:** `feat/context-budget-hook`
- **Companion plan (to be written):** `docs/superpowers/plans/2026-07-15-context-budget-hook.md`

## Problem

Long autonomous tasks lose progress when the session's context window fills:
auto-compaction summarizes away working state, or the session stalls outright,
and the next turn re-derives work that was never checkpointed. Ryan asked for a
hook that watches remaining "usage," gauges exhaustion, and brings the session
to a safe pause point before progress is lost.

**Signal decision (resolved during brainstorming):** true account-level quota
(Claude Pro/Max session or weekly limits) has no local or API exposure at all —
hook payloads carry no usage fields, and no endpoint reports remaining
subscription quota. The one signal that is genuinely measurable in real time is
the **session's context-window occupancy**, read from the local transcript.
Ryan chose that signal explicitly. The budget defaults to 150,000 tokens — the
`autoCompactWindow` threshold — so the hook's job is to force a durable pause
point *before* auto-compaction destroys working state.

## Goal

A `PostToolUse` hook that (1) measures current context occupancy from the
session transcript, (2) warns once at 70% of budget, and (3) at 85% repeats a
pause-point directive on **every tool call** until a resume-brief checkpoint
file verifiably exists on disk. No blocking, ever — a denied tool call near
exhaustion could strand the session, which is the exact failure this prevents.

## Architecture

One new hook plus wiring and tests, in the established house style
(bash wrapper + embedded Python heredoc, defensive JSON parse, fail-open,
always exit 0 — the same rules as `payload/hooks/precompact-event.sh`):

| File | Change |
|---|---|
| `payload/hooks/context-budget.sh` | **Create** — the hook |
| `payload/tools/tests/test_context_budget.sh` | **Create** — test suite, auto-discovered by `run_all.sh` |
| `payload/MANIFEST` | **Modify** — add `link-file hooks/context-budget.sh` under `# --- hooks/ ---` |
| `payload/fragments/settings.fragment.json` | **Modify** — add a `"PostToolUse"` group |
| `README.md` | **Modify** — add a row to the hooks table (near line 191) |
| `ARCHITECTURE.md` | **Modify** — add the hook to the hooks section (near line 162) |
| `INSTALL.md` | **Modify** — add the `PostToolUse` line to the fragment example (near line 111) |
| `CHANGELOG.md` | **Modify** — new entry |

`LEARNING.md` is untouched: it maps hook events to metric records, and this
hook writes no metric records.

## Component 1: `payload/hooks/context-budget.sh`

### Inputs

Stdin is the PostToolUse hook JSON. Only two fields are used: `session_id` and
`transcript_path`. Parsing is defensive (any failure → `{}`); if either field
is missing, the hook exits 0 silently.

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `CONTEXT_BUDGET_TOKENS` | `150000` | The context budget. Values that fail to parse, or are below 1,000, fall back to the default. |
| `CONTEXT_BUDGET_WARN_PCT` | `70` | Warn-tier threshold (percent). |
| `CONTEXT_BUDGET_CRIT_PCT` | `85` | Critical-tier threshold (percent). If `WARN_PCT >= CRIT_PCT` after parsing, both reset to defaults. |
| `CONTEXT_BUDGET_CHECK_SECS` | `30` | Measurement throttle below the critical tier. `0` disables throttling (used by tests). Negative or unparseable → default. |
| `CONTEXT_BUDGET_DISABLE` | unset | Set to `1` to make the hook exit 0 immediately (kill switch — this hook rides every tool call). |
| `CLAUDE_DIR` | `$HOME/.claude` | Same convention as `precompact-event.sh`. |
| `METRICS_DIR` | `$CLAUDE_DIR/metrics` | Same convention as `precompact-event.sh`. |

### Measurement

Occupancy is the context size reported by the **most recent** main-loop
assistant record in the transcript:

1. Open `transcript_path` in binary mode; seek to `max(0, size - 262144)`
   (a 256 KB tail); read to end; decode UTF-8 with `errors="replace"`.
2. Split into lines; if the seek offset was greater than 0, drop the first
   (possibly partial) line.
3. Iterate the lines **in reverse**. For each line that parses as JSON:
   skip it if `isSidechain` is `true` (subagent records must not pollute the
   main-loop reading); otherwise, if `type == "assistant"` and
   `message.usage` is present, compute
   `occupancy = input_tokens + cache_read_input_tokens + cache_creation_input_tokens`
   (each via `.get(field, 0) or 0`) and stop at the first match.
4. No match, an unreadable file, or a computed occupancy of 0 → treat as
   "no reading"; the hook stays silent and never fires a tier on it.

`percent = occupancy * 100 / budget`, compared against the tier thresholds.

### Per-session state

`$METRICS_DIR/state/budget/<safe_session_id>.json`, where `safe_session_id`
sanitizes `session_id` to `[A-Za-z0-9_.-]` and truncates to 128 characters
(identical to `precompact-event.sh`). The directories
`$METRICS_DIR/state/budget/` and `$METRICS_DIR/state/budget/checkpoints/` are
created on first use. Writes go to a temp file in the same directory followed
by `os.replace` (atomic). A missing or corrupt state file loads as defaults.

```json
{
  "last_check_ts": 0.0,
  "warn_fired": false,
  "crit_since": null,
  "checkpoint_ack": false
}
```

### Decision flow (per invocation)

1. `CONTEXT_BUDGET_DISABLE=1` → exit 0, no output.
2. Parse stdin; missing `session_id` or `transcript_path` → exit 0.
3. Load state.
4. **Critical tier active** (`crit_since` set, `checkpoint_ack` false):
   a. If the checkpoint file exists with `mtime >= int(crit_since)` → set
      `checkpoint_ack = true`, save state, exit silently. The nag is over.
      (The `int()` floor tolerates filesystems with one-second mtime
      resolution, so a checkpoint written in the same second as `crit_since`
      still counts.)
   b. Otherwise re-measure occupancy (no throttle at this tier — accuracy
      matters most near the end). No valid reading → exit silently
      (fail-open, the same as any other measurement failure). If the reading
      drops below the warn threshold (compaction happened), **re-arm**: reset
      the state to defaults, save, exit silently.
   c. Otherwise emit the critical message again, interpolating the fresh
      reading's values, and exit 0.
5. **Not critical** (no `crit_since`, or `checkpoint_ack` is true): if
   `now - last_check_ts < CHECK_SECS` → exit silently (throttled; the only
   cost of most invocations is reading one small state file). Otherwise
   measure, set `last_check_ts = now`, and:
   - no valid reading → save state, exit silently;
   - `percent >= CRIT_PCT` and `crit_since` is null → set `crit_since = now`,
     save, emit **critical**. (If `crit_since` is already set with
     `checkpoint_ack = true`, stay silent — the acknowledgment holds until a
     re-arm.)
   - `percent >= WARN_PCT` and `warn_fired` is false → set
     `warn_fired = true`, save, emit **warn**;
   - `percent < WARN_PCT` and any tier state is set (including
     `checkpoint_ack = true`) → **re-arm**: reset state to defaults, save,
     exit silently;
   - otherwise → save state, exit silently.

After an acknowledged checkpoint (`checkpoint_ack = true`), the hook stays
silent at high occupancy and keeps measuring on the throttle; a later drop
below the warn threshold re-arms the full cycle, so a session that compacts
and climbs again gets a fresh warn → critical → checkpoint sequence. The
checkpoint-file mtime is always compared against the **current** `crit_since`,
so a stale brief from an earlier cycle never silences a new one.

### Checkpoint artifact

`$METRICS_DIR/state/budget/checkpoints/<safe_session_id>.md` — a resume brief
the *agent* writes when directed: task state, branch names, next steps, and
key file paths. The hook only ever `stat`s this path; it never writes or
deletes it.

### Output

Silence is no stdout at all (matching `precompact-event.sh` below threshold).
When a tier fires, exactly one JSON object goes to stdout:

```json
{
  "systemMessage": "<short one-liner for the user>",
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "<directive for the agent>"
  }
}
```

**Warn tier (fires once per cycle):**

- `systemMessage`:
  `Context budget: {occupancy} of {budget} tokens used ({percent}%). Steering toward a pause point.`
- `additionalContext`:
  `Context-budget warning: this session's context window is at {percent}% of its {budget}-token budget ({occupancy} tokens). Begin steering toward a safe pause point: finish the current step, commit and push work in progress, and update your ledger and todos. A critical reminder will fire at {crit_pct}% and will repeat until you write a checkpoint file.`

**Critical tier (fires every tool call until acknowledged):**

- `systemMessage`:
  `Context budget CRITICAL: {occupancy} of {budget} tokens used ({percent}%). Checkpoint required.`
- `additionalContext`:
  `Context-budget CRITICAL: this session's context window is at {percent}% of its {budget}-token budget ({occupancy} tokens). Reach a safe pause point now: (1) commit and push all work in progress; (2) update your progress ledger and todos; (3) write a resume brief to {checkpoint_path} covering task state, branch names, next steps, and key file paths. This reminder repeats on every tool call until that file exists.`

`{occupancy}` and `{budget}` render as plain integers; `{percent}` and
`{crit_pct}` render as integers (floor); `{checkpoint_path}` renders as the
absolute checkpoint-file path. These strings are user-facing
machine-generated prose:
the implementation must reproduce them exactly, and the test suite pins them
(grammar regression, per the machine-prose mandate).

### Failure policy

Any exception anywhere → exit 0 with no output (fail-open). The hook never
exits non-zero and never blocks a tool call. A broken hook must degrade to
"the feature doesn't exist," not "the session is disrupted."

## Component 2: Wiring

`payload/MANIFEST`, under `# --- hooks/ ---`:

```
link-file hooks/context-budget.sh
```

`payload/fragments/settings.fragment.json`, new top-level key inside
`"hooks"` (the repo's first `PostToolUse` group; no `matcher`, so it fires
after every tool call — independent of the read-guard plan's pending
`"PreToolUse"` key, whichever lands first):

```json
"PostToolUse": [
  { "hooks": [ { "type": "command", "command": "$HOME/.claude/hooks/context-budget.sh" } ] }
]
```

## Component 3: Documentation one-liners

- `README.md` hooks table — new row:
  `| context-budget.sh | PostToolUse | Watches context-window occupancy from the session transcript; warns at 70% of the 150k budget and, from 85%, repeats a pause-point directive on every tool call until a resume-brief checkpoint file exists. |`
- `ARCHITECTURE.md` hooks section — one sentence introducing the hook beside
  the existing `precompact-event.sh` description, noting the complementary
  split: context-budget acts *before* compaction; precompact-event records
  and escalates *after* it.
- `INSTALL.md` fragment example — add the `PostToolUse` line shown above.
- `CHANGELOG.md` — one entry under a new version heading, following the
  file's existing format.

## Component 4: `payload/tools/tests/test_context_budget.sh`

Modeled on `payload/tools/tests/test_precompact_tmx.sh`: `mktemp -d` sandbox
with `CLAUDE_DIR`/`METRICS_DIR` exported, synthetic transcript JSONL fixtures,
payloads piped via `printf '%s' "$PAYLOAD" | bash "$HOOK"`, stdout and exit
codes asserted, and a Python one-liner validating emitted JSON shape. Unless a
case says otherwise, tests set `CONTEXT_BUDGET_CHECK_SECS=0`.

| # | Case | Expectation |
|---|---|---|
| 1 | Occupancy 60,000 / 150,000 (40%) | Empty stdout, exit 0 |
| 2 | Occupancy 110,000 (73%) | Warn JSON once; an identical second call is silent |
| 3 | Occupancy 130,000 (86%) | Critical JSON naming the checkpoint path |
| 4 | Repeated calls at 130,000, no checkpoint | Critical JSON re-emitted every call |
| 5 | Checkpoint file written after `crit_since` | Next call silent; subsequent calls silent |
| 6 | After ack, occupancy fixture drops to 60,000, then climbs to 130,000 | Silent re-arm, then a fresh critical; a checkpoint file back-dated with `touch -t` (mtime before the new `crit_since`) does **not** silence it |
| 7 | Malformed stdin (not JSON) | Empty stdout, exit 0 |
| 8 | `transcript_path` missing from payload, or pointing at a nonexistent file | Empty stdout, exit 0 |
| 9 | Tail ends with `isSidechain: true` records carrying huge usage; older main-loop record is small | The main-loop record wins (silence at 40%) |
| 10 | `CONTEXT_BUDGET_DISABLE=1` at occupancy 130,000 | Empty stdout, exit 0 |
| 11 | Emitted JSON shape | `systemMessage` present; `hookSpecificOutput.hookEventName == "PostToolUse"`; `additionalContext` present |
| 12 | `CONTEXT_BUDGET_CHECK_SECS=3600`, first call below warn, transcript replaced with 130,000 occupancy, immediate second call | Second call silent (throttled) |
| 13 | Grammar regression | The emitted warn and critical `additionalContext` strings match this spec's texts verbatim (with the case's values interpolated) |

## Rejected alternatives

- **Reading account quota (the literal request).** Not buildable: hook
  payloads carry no usage fields; Pro/Max limits are server-side only; the
  Admin API needs an org-admin key and reports with a delay. Documented here
  so the constraint isn't re-litigated later.
- **Estimating whether the task will finish.** No reliable task-size signal
  exists; fixed thresholds are the honest version of "gauge if it will
  finish before running out."
- **Hard blocking at the critical tier (Approach C).** Deny-listing tool
  calls near exhaustion risks stranding the session; classification of Bash
  commands into "checkpoint-related or not" is brittle.
- **One-time advisory only (Approach A).** A single nudge gets buried —
  exactly the observed failure mode. The artifact-verified nag closes the
  gap at modest extra complexity.
- **Also binding `UserPromptSubmit`.** PostToolUse already covers the danger
  zone (long autonomous turns); YAGNI.
- **Emitting metric records for the LEARN loop.** Deferred; can be added
  later without changing this design's interface.

## Out of scope

- Changing `precompact-event.sh` or its TOKEN MINIMIZER escalation (the two
  hooks are complementary and share no state).
- Any UI beyond the `systemMessage` one-liners.
- Per-project budget configuration files (environment variables suffice).
