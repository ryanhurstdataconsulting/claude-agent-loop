# Read-Guard Hook — Design Spec

**Date:** 2026-07-14
**Status:** Approved (design chunks 1 & 2, "looks good" / "looks great")

## Problem

The machine-global `~/.claude/CLAUDE.md` "Autocompact Anti-Thrash" section
documents a recurring failure pattern: a session's context fills, compacts,
and fills again within a few turns — almost always because one oversized
artifact re-enters the window (a whole-file `Read` of something huge, or a
verbose command's raw output pasted back into the conversation). The section
lays out seven textual rules an agent is supposed to follow by discipline
alone: size-gate every Read, never read certain file classes wholesale, cap
command output at the source, search narrow, ingest once, and so on.

Textual discipline is not enforcement. An agent under context pressure, mid-
task, with no external check, can and does violate its own stated rules — this
exact session did, hitting four consecutive text-only compaction turns. A
mechanical backstop is needed: something that runs outside the model's own
judgment and can catch an oversized `Read` before it lands in context.

## Chosen approach

Build a new `PreToolUse` hook, `read-guard.sh`, in `claude-agent-loop`,
matched to the `Read` tool. It inspects every `Read` call before it executes
and:

- **Hard-blocks** reads of a fixed list of file classes that should never be
  read whole under any circumstance (lockfiles, minified/bundled assets,
  `node_modules/`, build output directories, log/transcript/data files).
- **Soft-nudges** (allows, but injects a reminder) when a `Read` targets a
  large-but-not-hard-blocked file without `offset`/`limit`, prompting the
  agent to re-issue the read narrowly or delegate to a subagent.
- **Fails open** on any ambiguity — malformed input, an unreadable path, an
  unexpected error — because a hook that occasionally blocks a legitimate
  read is a worse failure mode than one that occasionally lets an oversized
  read through.

This was chosen over two alternatives considered earlier in the design
conversation: relying solely on Claude's platform-level context-editing
feature (`clear_tool_uses`), and a hybrid of context-editing plus a lighter
hook. Context-editing clears *already-ingested* tool results after the fact —
it reduces the damage of a bad read retroactively, but doesn't stop the read
from spiking the window in the first place, and it's a session-level
platform setting the agent can't reliably self-configure per project. A
mechanical pre-flight gate closes the gap at its source: the read never
executes at full size to begin with.

## Architecture

### New file: `payload/hooks/read-guard.sh`

Follows the existing shape used by `precompact-event.sh` in this repo:

```bash
#!/bin/bash
set -u
INPUT="$(cat 2>/dev/null || true)"
python3 <<'PYEOF'
import json, sys, os

try:
    payload = json.loads(os.environ.get("READ_GUARD_INPUT", "") or sys.stdin.read())
except Exception:
    payload = {}

# ... decision logic (see below) ...
PYEOF
```

(Exact stdin-handoff mechanics — env var vs. heredoc stdin passthrough — are
an implementation detail for the plan, not the spec; the constraint is that
JSON parsing happens in Python inside a `try/except` that defaults to `{}`
on any failure, matching `precompact-event.sh`'s pattern of never trusting
its own input.)

No `set -e`. Bash-3.2-portable throughout (see below). The hook always
flushes stdout and exits 0 — never exit 2 (see "Error handling," below).

### Decision logic

1. Parse stdin JSON. On failure, default to `{}` and fall through to "allow,
   no context" (see step 5).
2. Extract `tool_input.file_path`. This is the only `tool_input` key
   confirmed via real PreToolUse fixtures for the `Read` tool (see "Open
   Questions / Assumptions," item 2). If missing, allow with no context —
   nothing to check.
3. **Hard-block check.** Match `file_path` (or its basename, or any path
   segment) against the hard-blocked classes below via a `case` statement.
   On a match, emit a `deny` decision with a `permissionDecisionReason`
   naming the matched class.
4. **Soft-nudge check.** If not hard-blocked, `stat` the file for size and
   (if readable as text) line count. If either exceeds the threshold (see
   below) AND neither `tool_input.offset` nor `tool_input.limit` is present
   in the payload, emit an `allow` decision with `additionalContext`
   reminding the agent to re-issue the read with `offset`/`limit` or
   delegate to a subagent. `stat` failures (file doesn't exist, permission
   denied, etc.) fall through to allow with no context — this hook isn't the
   place to raise "file not found," the `Read` tool call itself will surface
   that.
5. **Default.** Any file that's neither hard-blocked nor over-threshold: emit
   a plain `allow` with no `additionalContext`.

### Hard-blocked file classes

Verbatim from the CLAUDE.md Anti-Thrash rule's item 2:

- Lockfiles: `package-lock.json`, `poetry.lock`, `Cargo.lock`
- Minified or bundled JS/CSS (matched by filename pattern, e.g. `*.min.js`,
  `*.min.css`, or a `.bundle.` infix)
- Source maps: `*.map`
- Anything with a path segment `node_modules/`, `dist/`, `build/`, `.vite/`,
  or `coverage/`
- JSONL session transcripts: `*.jsonl`
- Log files: `*.log`
- CSV/Parquet data files: `*.csv`, `*.parquet`

"Generated HTML reports" — present in the CLAUDE.md list but deliberately
**excluded** from the hard-block set here, per the approved design. HTML
reports are sometimes small and legitimately worth reading whole (a short
status page); the size-based soft-nudge check already covers the case where
one is large, without permanently blocking every `*.html` file by extension.

### Soft-nudge threshold

A file is "large" if it exceeds **1,000 lines OR 100 KB** (matching the
CLAUDE.md rule's own stated cap), and the `Read` call supplies neither
`offset` nor `limit`. The nudge never blocks — it only adds
`additionalContext` to an `allow` decision.

### `hookSpecificOutput` shape

Confirmed via the background research pass (official docs + a real shipped
hook implementation + a GitHub issue trail — see citations at the end of
this doc):

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow" | "deny",
    "permissionDecisionReason": "...",
    "additionalContext": "..."
  }
}
```

- `hookEventName` is always the literal string `"PreToolUse"`.
- `permissionDecision` is `"deny"` for hard-blocked reads, `"allow"` for
  everything else (including nudged reads). This hook never emits `"ask"` or
  `"defer"` — both are out of scope for a mechanical size/class gate.
- `permissionDecisionReason` is required on `deny` (names the matched
  class) and omitted on plain `allow`.
- `additionalContext` is present only on a nudged `allow`; omitted
  otherwise.

### Registration

**`payload/fragments/settings.fragment.json`** gets a new `"PreToolUse"` key:

```json
"PreToolUse": [
  {
    "matcher": "Read",
    "hooks": [
      {
        "type": "command",
        "command": "$HOME/.claude/hooks/read-guard.sh"
      }
    ]
  }
]
```

This is the first `matcher` field used anywhere in this repo's hook wiring —
every existing hook (`inject-resource-loop.sh`, `harvest-metrics.sh`,
`precompact-event.sh`, `auto-update.sh`) fires unconditionally on its event
with no matcher. `"Read"` is confirmed safe as an **exact-string** match
(all-letters matchers are exact matches, not regex — see "Open Questions /
Assumptions" for the general matcher-syntax caveat).

**`payload/MANIFEST`** gets one new line under `# --- hooks/ ---`:

```
link-file hooks/read-guard.sh
```

This slots in alongside the four existing entries
(`inject-resource-loop.sh`, `harvest-metrics.sh`, `precompact-event.sh`,
`auto-update.sh`) and is picked up automatically by the existing
`test_install_symlinks.sh` MANIFEST-driven install/uninstall scenarios — no
new test needed there (see test case 8, below).

## Error handling — fail open

Every failure mode defaults to allow, never to block:

- **Malformed or empty stdin JSON** → `json.loads()` wrapped in
  `try/except`, defaulting to `{}`. An empty payload has no
  `tool_input.file_path`, which falls through to plain allow.
- **Missing `tool_input.file_path`** → plain allow (nothing to check).
- **`stat`/line-count failures on the target path** (file doesn't exist,
  permission denied, race condition between the hook running and the file
  changing) → caught, allow with no nudge context.
- **Any other unexpected exception in the embedded Python** → caught at the
  top level of the script, allow and exit 0.

Only a positive, confirmed match against the hard-block list actively
denies. Every ambiguous or error case defaults to the safer failure mode for
this hook's purpose: letting a read through beats blocking a legitimate one
and stalling the agent's work. This mirrors `precompact-event.sh`'s own
explicit contract ("The hook ALWAYS exits 0 and never blocks compaction") and
`inject-resource-loop.sh`'s "ADDITIVE-ONLY" posture.

**Exit code discipline:** `read-guard.sh` commits to exit-0 plus JSON
(`hookSpecificOutput.permissionDecision`) as its *sole* signaling mechanism.
It must never exit 2. Exit code and stdout JSON are mutually exclusive per
invocation — an exit-2 causes Claude Code to discard any JSON on stdout and
instead feed the hook's stderr text back to the agent as a raw, unstructured
blocking error. This was confirmed via three independent sources (official
docs, a real shipped hook's source, and a GitHub issue where an exit-2 +
JSON-deny-body was silently ignored until the hook switched to exit-0 +
`hookSpecificOutput`). All of `read-guard.sh`'s decisions — including denies
— go through the JSON body on an exit-0 return.

## Bash-3.2 portability

macOS ships bash 3.2. `read-guard.sh` avoids:

- `declare -A` (associative arrays)
- `mapfile`
- GNU-only flags (e.g. GNU-specific `base64`/`base32` options, GNU `stat`
  flags)

File-class matching uses a `case` statement against the basename and full
path (bash 3.2-safe), matching `inject-resource-loop.sh`'s existing
portability pattern. File-size checks detect the `stat` dialect at runtime
rather than assuming one:

```bash
size=$(stat -f%z "$path" 2>/dev/null || stat -c%s "$path" 2>/dev/null)
```

(BSD `stat -f%z` first, falling back to GNU `stat -c%s` — this repo's CI/dev
boxes may be either.)

## Testing plan

New file: `payload/tools/tests/test_read_guard.sh`, modeled on
`test_precompact_tmx.sh`'s shape — `printf '%s' "$PAYLOAD" | bash "$HOOK"`,
`pass`/`die` helpers, inline `python3 -c` assertions on the JSON shape of
the hook's stdout. Eight cases:

1. **Hard-blocked file** (e.g. `package-lock.json`) → `deny` with a reason
   naming the matched class.
2. **Hard-blocked directory** (e.g. `node_modules/foo.js`) → `deny`.
3. **Normal small file, no `offset`/`limit`** → `allow`, no
   `additionalContext`.
4. **Large file, no `offset`/`limit`** → `allow` + `additionalContext`
   nudge present.
5. **Large file, `offset`/`limit` already supplied** → `allow`, no nudge.
6. **Malformed stdin JSON** → `allow`, exit 0, no crash.
7. **Missing/unreadable file path** → `allow`, exit 0.
8. **MANIFEST wiring** — no new test needed; `test_install_symlinks.sh`'s
   existing MANIFEST-driven install/uninstall scenarios pick up
   `read-guard.sh` automatically once the new `link-file` line lands.

## Open Questions / Assumptions

These are the genuine unknowns surfaced by the background research pass.
None of them block the design above, but each represents something the
implementation should treat as an assumption rather than a fact, or a
non-load-bearing gap:

1. **Multi-hook precedence order** is unresolved/contradicted across
   sources (the official docs gave two different orderings on separate
   fetches: "deny, defer, ask, allow" vs. "deny > ask > defer > allow"; a
   third variant omitting `defer` appears in secondary community
   write-ups). Not load-bearing here — `read-guard.sh` is the only hook on
   `PreToolUse`/`Read` in this repo, so there's no multi-hook interaction to
   resolve.
2. **`tool_input.offset` / `tool_input.limit` as sibling keys of
   `file_path`** are assumed, not confirmed from a primary source. Only
   `file_path` is verified via real shipped PreToolUse fixtures for `Read`;
   the `offset`/`limit` field names come from a third party's own
   reverse-engineered schema doc, not a fixture. This is a reasonable
   inference from the `Read` tool's own documented parameters. The natural
   fail-safe: if the field names turn out wrong, the nudge simply always
   fires on oversized files (a harmless false-positive that just means an
   extra reminder gets shown) — it can never silently fail to fire, which
   would be the actually dangerous direction.
3. **Matcher case sensitivity** is not stated anywhere in the official
   docs; all worked examples use canonical tool-name casing (`"Read"`,
   `"Edit"`, etc.). `read-guard.sh` uses `"Read"` verbatim, matching every
   documented example.
4. Whether `permissionDecisionReason` is **also shown in the human-visible
   transcript**, versus being Claude-only (with `systemMessage` reserved for
   the user), is not definitively confirmed either way. Not load-bearing:
   the reason text is written to be reasonable either way (a short,
   factual statement of which file class was blocked).
5. **Non-2 nonzero exit codes** (e.g. exit 1) on a hook have been reported
   as failing open in at least one case (a hook exiting 1 was logged as a
   hook error but did not block the tool call) — but this behavior was
   reported in an unresolved GitHub issue, not confirmed as intentional or
   stable. `read-guard.sh` sidesteps this entirely by always exiting 0.
6. **`""` vs `"*"` matcher equivalence** for older Claude Code versions, and
   other version-dependent matcher-syntax changes beyond the documented
   hyphen caveat, are not independently verified beyond what's stated in
   the docs. Not load-bearing: `"Read"` (all letters) is safe on every
   version per the confirmed exact-match rule.
7. A third-party "smart-read" line-count Read-blocking hook is referenced
   in a GitHub issue's prose, but the actual script could not be located
   during research. It is **not** cited as a working reference
   implementation anywhere in this design — `precompact-event.sh` and
   `inject-resource-loop.sh` (both in this repo) are the actual structural
   precedents used.

## Citations

- `https://code.claude.com/docs/en/hooks` — canonical hooks reference
  (`docs.claude.com/en/docs/claude-code/hooks` 301-redirects here);
  `hookSpecificOutput` shape, `permissionDecision` values, matcher syntax.
- `https://code.claude.com/docs/en/hooks.md` — same content, markdown form.
- `https://github.com/kornysietsma/claude-code-permissions-hook/blob/main/src/hook_io.rs`
  — real shipped hook serializing a `deny` decision via
  `hookSpecificOutput`/exit-0.
- `https://github.com/kornysietsma/claude-code-permissions-hook/blob/main/tests/read_allowed.json`,
  `.../tests/read_path_traversal.json` — real PreToolUse stdin fixtures for
  the `Read` tool, confirming `tool_input.file_path` as a top-level key.
- `https://github.com/anthropics/claude-code/issues/37210` — exit-2 +
  JSON-deny-body silently ignored until switched to exit-0 +
  `hookSpecificOutput`.
- `https://github.com/anthropics/claude-code/issues/21988` — a hook exiting
  1 logged as a hook error but did not block the tool call (unresolved by
  its own reporter).
