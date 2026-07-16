# Read-Guard Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `PreToolUse` hook, `read-guard.sh`, that hard-blocks whole-file `Read` calls against never-read-whole file classes, soft-nudges large reads issued without `offset`/`limit`, and fails open on every ambiguous case — a mechanical backstop for the machine-global "Autocompact Anti-Thrash" discipline.

**Architecture:** A thin bash wrapper (`cat` stdin into an env var, then `exit 0`) hands the raw hook JSON to an embedded Python 3 heredoc that does all decision work: it parses the payload defensively, classifies `tool_input.file_path` against a fixed hard-block list, sizes the target for the soft-nudge check, and writes exactly one `hookSpecificOutput` object to stdout. The hook signals only through that JSON — it always exits 0. This follows the shape of the repo's existing `precompact-event.sh` hook.

**Tech Stack:** bash 3.2 (macOS-portable wrapper), Python 3 (embedded heredoc for parsing, classification, and sizing), the Claude Code `PreToolUse` hook contract (`hookSpecificOutput.permissionDecision`), the repo's MANIFEST-driven symlink installer, and the bash test-harness style used across `payload/tools/tests/`.

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the design spec (`docs/superpowers/specs/2026-07-14-read-guard-hook-design.md`).

- **Always exit 0; never exit 2.** `read-guard.sh` commits to exit-0 plus JSON (`hookSpecificOutput.permissionDecision`) as its *sole* signaling mechanism. Exit code and stdout JSON are mutually exclusive per invocation — an exit-2 causes Claude Code to discard any JSON on stdout and instead feed the hook's stderr back to the agent as a raw, unstructured blocking error. All decisions — including denies — go through the JSON body on an exit-0 return.
- **`permissionDecision` is only `"allow"` or `"deny"` — never `"ask"` or `"defer"`.** Both `"ask"` and `"defer"` are out of scope for a mechanical size/class gate.
- **Fail open on any ambiguity.** Malformed or empty stdin JSON, a missing `tool_input.file_path`, a `stat`/line-count failure on the target path, and any other unexpected exception all default to **allow**. Only a positive, confirmed match against the hard-block list actively denies.
- **JSON parsing happens in Python inside a `try/except` that defaults to `{}`** on any failure, mirroring `precompact-event.sh`'s pattern of never trusting its own input.
- **Bash-3.2 portable.** macOS ships bash 3.2. The hook avoids `declare -A` (associative arrays), `mapfile`, and GNU-only flags (e.g. GNU-specific `stat` flags). The bash layer stays trivial — `cat` plus `exit 0` — and all classification and sizing run in Python, which is bash-version-independent.
- **`hookSpecificOutput.hookEventName` is always the literal string `"PreToolUse"`.**
- **Soft-nudge threshold: over 1,000 lines OR 100 KB.** The nudge fires only when the file is large *and* the `Read` call supplies neither `offset` nor `limit`. The nudge never blocks — it only adds `additionalContext` to an `allow` decision.
- **The hard-block set deliberately excludes generated HTML reports.** They are sometimes small and legitimately worth reading whole; the size-based soft-nudge covers the large case without permanently blocking every `*.html` file.

## File Structure

- **Create `payload/hooks/read-guard.sh`** — the hook itself. One responsibility: decide `allow`/`deny`/`allow-with-nudge` for a single `Read` call and emit the `hookSpecificOutput` JSON. Self-contained; no dependencies on other payload files.
- **Create `payload/tools/tests/test_read_guard.sh`** — the 8-case bash test suite for the hook, modeled on `test_precompact_tmx.sh`. Auto-discovered by `run_all.sh` (which globs `test_*.sh`).
- **Modify `payload/MANIFEST`** — one new `link-file` line under `# --- hooks/ ---` so the installer symlinks the hook into `~/.claude/hooks/`.
- **Modify `payload/fragments/settings.fragment.json`** — a new `"PreToolUse"` key registering the hook against the `Read` matcher.

### Resolved implementation decision (read before Task 1)

The spec's "Bash-3.2 portability" section mentions a bash `case` statement for file-class matching and a runtime `stat`-dialect line. Its "Architecture" and "Decision logic" sections, however, place the decision logic *inside the Python heredoc* (`# ... decision logic (see below) ...`), and the spec names `precompact-event.sh` as the "shape to follow" — a hook that does 100% of its logic in Python with only a trivial bash wrapper. These two mechanisms cannot both be literal without a clumsy, escaping-prone bash↔Python round trip. This plan resolves the tension toward the Architecture block and the named precedent: **all classification and sizing run in Python** (string matching in place of the `case` statement; `os.path.getsize` plus a line count in place of the bash `stat`-dialect probe — which is *more* portable, not less). This honors every verbatim value the spec requires (the hard-block class list, the 1,000-line / 100-KB threshold, the JSON keys) and every Global Constraint, while keeping the bash layer free of the `declare -A`/`mapfile`/GNU-flag hazards the portability section guards against.

---

### Task 1: `read-guard.sh` hook + `test_read_guard.sh` suite

**Files:**
- Create: `payload/hooks/read-guard.sh`
- Test: `payload/tools/tests/test_read_guard.sh`

**Interfaces:**
- Consumes: the Claude Code `PreToolUse` hook JSON on stdin — a dict whose relevant keys are `tool_input.file_path` (string), and optionally `tool_input.offset` / `tool_input.limit`.
- Produces: exactly one JSON object on stdout of the form
  `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"|"deny", "permissionDecisionReason"?: str, "additionalContext"?: str}}`.
  `permissionDecisionReason` is present only on `deny`; `additionalContext` is present only on a nudged `allow`. The process always exits 0. Later tasks rely on the script existing at `payload/hooks/read-guard.sh` and on the suite passing via `bash test_read_guard.sh`.

- [ ] **Step 1: Write the failing test suite**

Create `payload/tools/tests/test_read_guard.sh` with exactly this content:

```bash
#!/bin/bash
# test_read_guard.sh — PreToolUse read-guard hook.
#
# The hook hard-blocks whole-file Reads of never-read-whole file classes
# (deny), soft-nudges large files read without offset/limit (allow +
# additionalContext), and fails open on every ambiguous or error case (allow).
# It ALWAYS exits 0 and signals only through hookSpecificOutput JSON — never
# exit 2, never "ask"/"defer". macOS bash-3.2 portable. Modeled on
# test_precompact_tmx.sh.
set -u

HOOK="$(cd "$(dirname "$0")/../../hooks" && pwd)/read-guard.sh"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Fixtures: one small text file, one large text file (1,500 lines).
SMALL="$TMP/notes.txt"
printf 'hello world\n' > "$SMALL"
BIG="$TMP/big.txt"
python3 -c "open('$BIG','w').write('x\n'*1500)"

# assert_json <label> <stdout> <python-assertion-body>
# Loads the hook's stdout as JSON, asserts hookEventName, then runs the body.
# A parse failure or a failed assert makes this return non-zero (the caller dies).
assert_json() {
  echo "$2" | python3 -c "import json,sys
d=json.load(sys.stdin)
h=d['hookSpecificOutput']
assert h['hookEventName']=='PreToolUse', 'wrong hookEventName'
$3" >/dev/null 2>&1
}

# 1. Hard-blocked file (package-lock.json) -> deny naming the class.
P1='{"tool_name":"Read","tool_input":{"file_path":"/repo/package-lock.json"}}'
out1="$(printf '%s' "$P1" | bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "1 hard-block file: exit 0" || die "1 exit $rc"
assert_json "1" "$out1" "
assert h['permissionDecision']=='deny', 'expected deny'
r=h.get('permissionDecisionReason','')
assert isinstance(r,str) and r.strip(), 'missing reason'
assert 'lockfile' in r.lower(), 'reason must name the class'
" && pass "1 hard-block file: deny + reason names class" || die "1 bad JSON: $out1"

# 2. Hard-blocked directory segment (node_modules/) -> deny.
P2='{"tool_name":"Read","tool_input":{"file_path":"/repo/node_modules/left-pad/index.js"}}'
out2="$(printf '%s' "$P2" | bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "2 hard-block dir: exit 0" || die "2 exit $rc"
assert_json "2" "$out2" "
assert h['permissionDecision']=='deny', 'expected deny'
assert 'node_modules' in h.get('permissionDecisionReason',''), 'reason names dir'
" && pass "2 hard-block dir: deny" || die "2 bad JSON: $out2"

# 3. Normal small file, no offset/limit -> allow, no additionalContext.
P3="{\"tool_name\":\"Read\",\"tool_input\":{\"file_path\":\"$SMALL\"}}"
out3="$(printf '%s' "$P3" | bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "3 small file: exit 0" || die "3 exit $rc"
assert_json "3" "$out3" "
assert h['permissionDecision']=='allow', 'expected allow'
assert 'additionalContext' not in h, 'small file must not nudge'
" && pass "3 small file: allow, no nudge" || die "3 bad JSON: $out3"

# 4. Large file, no offset/limit -> allow + additionalContext nudge.
P4="{\"tool_name\":\"Read\",\"tool_input\":{\"file_path\":\"$BIG\"}}"
out4="$(printf '%s' "$P4" | bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "4 large file: exit 0" || die "4 exit $rc"
assert_json "4" "$out4" "
assert h['permissionDecision']=='allow', 'expected allow'
c=h.get('additionalContext','')
assert isinstance(c,str) and c.strip(), 'large file must nudge'
assert 'offset' in c.lower(), 'nudge should mention offset/limit'
" && pass "4 large file: allow + nudge" || die "4 bad JSON: $out4"

# 5. Large file WITH offset/limit -> allow, no nudge.
P5="{\"tool_name\":\"Read\",\"tool_input\":{\"file_path\":\"$BIG\",\"offset\":100,\"limit\":50}}"
out5="$(printf '%s' "$P5" | bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "5 large+offset: exit 0" || die "5 exit $rc"
assert_json "5" "$out5" "
assert h['permissionDecision']=='allow', 'expected allow'
assert 'additionalContext' not in h, 'offset/limit read must not nudge'
" && pass "5 large+offset: allow, no nudge" || die "5 bad JSON: $out5"

# 6. Malformed stdin JSON -> exit 0, allow, no crash.
out6="$(printf '%s' 'not json {{{' | bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "6 malformed stdin: exit 0" || die "6 exit $rc"
assert_json "6" "$out6" "
assert h['permissionDecision']=='allow', 'malformed -> allow'
" && pass "6 malformed stdin: allow, no crash" || die "6 bad JSON: $out6"

# 7. Missing file_path AND nonexistent path -> allow, exit 0.
P7A='{"tool_name":"Read","tool_input":{}}'
out7a="$(printf '%s' "$P7A" | bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "7a missing file_path: exit 0" || die "7a exit $rc"
assert_json "7a" "$out7a" "assert h['permissionDecision']=='allow', 'missing path -> allow'" \
  && pass "7a missing file_path: allow" || die "7a bad JSON: $out7a"
P7B='{"tool_name":"Read","tool_input":{"file_path":"/no/such/file/here.txt"}}'
out7b="$(printf '%s' "$P7B" | bash "$HOOK")"; rc=$?
[ $rc -eq 0 ] && pass "7b unreadable path: exit 0" || die "7b exit $rc"
assert_json "7b" "$out7b" "
assert h['permissionDecision']=='allow', 'unreadable path -> allow'
assert 'additionalContext' not in h, 'stat failure must not nudge'
" && pass "7b unreadable path: allow, no nudge" || die "7b bad JSON: $out7b"

# 8. MANIFEST wiring: no dedicated case here. test_install_symlinks.sh's existing
#    MANIFEST-driven install/uninstall scenarios pick up hooks/read-guard.sh
#    automatically once its `link-file` line lands in payload/MANIFEST (Task 2).

echo "---"
if [ $fail -eq 0 ]; then echo "test_read_guard: OK"; exit 0; else echo "test_read_guard: FAIL"; exit 1; fi
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests && bash test_read_guard.sh`
Expected: FAIL — the hook does not exist yet, so every case's `bash "$HOOK"` errors, `out*` is empty, the `assert_json` JSON parse fails, and each case reports `FAIL - ...`. The suite ends with `test_read_guard: FAIL` and a non-zero exit.

- [ ] **Step 3: Write the hook**

Create `payload/hooks/read-guard.sh` with exactly this content:

```bash
#!/bin/bash
# read-guard.sh — PreToolUse hook on the Read tool. A mechanical backstop for
# the machine-global "Autocompact Anti-Thrash" discipline. It inspects every
# Read call before it executes and:
#   - HARD-BLOCKS (deny) whole-file reads of file classes that should never
#     enter the context window whole: lockfiles, minified/bundled assets,
#     source maps, node_modules/dist/build/.vite/coverage paths, JSONL
#     transcripts, .log files, and CSV/Parquet data files.
#   - SOFT-NUDGES (allow + additionalContext) a large file (over 1,000 lines
#     OR 100 KB) read without offset/limit, prompting a narrow re-read or a
#     subagent hand-off.
#   - FAILS OPEN (allow) on every ambiguous or error case.
#
# The hook ALWAYS exits 0 and signals ONLY through the hookSpecificOutput JSON
# on stdout (permissionDecision "allow"/"deny"); it NEVER exits 2 and never
# emits "ask"/"defer". JSON parsing happens in Python inside a try/except that
# defaults to {} on any failure, mirroring precompact-event.sh. No set -e.
# macOS bash-3.2 portable: the bash layer is trivial (cat + exit 0), so it uses
# no declare -A, no mapfile, and no GNU-only flags; all classification and
# sizing run in Python, which is bash-version-independent.
set -u

INPUT="$(cat 2>/dev/null || true)"

READ_GUARD_INPUT="$INPUT" python3 <<'PY' || true
import json
import os
import sys

# --- defensive parse: any failure -> {} (mirrors precompact-event.sh) ---------
raw = os.environ.get("READ_GUARD_INPUT", "")
try:
    payload = json.loads(raw) if raw.strip() else {}
    if not isinstance(payload, dict):
        payload = {}
except Exception:
    payload = {}

LINE_CAP = 1000
BYTE_CAP = 100 * 1024  # 100 KB

HARD_LOCKFILES = ("package-lock.json", "poetry.lock", "Cargo.lock")
HARD_SEGMENTS = ("node_modules", "dist", "build", ".vite", "coverage")


def hard_block_label(file_path):
    """Return a noun-phrase label if file_path is a hard-blocked class, else None."""
    base = os.path.basename(file_path)
    lower = base.lower()
    if base in HARD_LOCKFILES:
        return "a lockfile"
    if lower.endswith(".min.js") or lower.endswith(".min.css") or ".bundle." in lower:
        return "a minified or bundled asset"
    if lower.endswith(".map"):
        return "a source map"
    if lower.endswith(".jsonl"):
        return "a JSONL session transcript"
    if lower.endswith(".log"):
        return "a log file"
    if lower.endswith(".csv") or lower.endswith(".parquet"):
        return "a data file (CSV or Parquet)"
    for seg in file_path.replace("\\", "/").split("/"):
        if seg in HARD_SEGMENTS:
            return "inside a %s/ directory" % seg
    return None


def is_large(file_path):
    """True if the file is over the byte OR line cap. Any stat/read failure -> False."""
    try:
        if os.path.getsize(file_path) > BYTE_CAP:
            return True
    except Exception:
        return False
    try:
        lines = 0
        with open(file_path, "rb") as fh:
            for _ in fh:
                lines += 1
                if lines > LINE_CAP:
                    return True
    except Exception:
        return False
    return lines > LINE_CAP


def allow(context=None):
    hook = {"hookEventName": "PreToolUse", "permissionDecision": "allow"}
    if context:
        hook["additionalContext"] = context
    return {"hookSpecificOutput": hook}


def deny(reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


# --- decision logic: any exception -> plain allow (fail open) ------------------
result = None
try:
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        result = allow()
    else:
        label = hard_block_label(file_path)
        if label:
            result = deny(
                "Blocked whole-file Read of %s: it is %s; reading such a file "
                "whole floods the context window. Pull a targeted span with "
                "offset/limit, grep it, or delegate the sweep to a subagent."
                % (file_path, label)
            )
        elif (
            "offset" not in tool_input
            and "limit" not in tool_input
            and is_large(file_path)
        ):
            result = allow(
                "read-guard: %s is large (over 1,000 lines or 100 KB) and you "
                "requested it without offset/limit. Re-issue the Read with "
                "offset/limit to pull only the span you need, or delegate the "
                "sweep to a subagent that returns the conclusion." % file_path
            )
        else:
            result = allow()
except Exception:
    result = allow()

if result is None:
    result = allow()

sys.stdout.write(json.dumps(result))
# os._exit does not flush Python's buffered stdout — flush the decision first.
try:
    sys.stdout.flush()
except Exception:
    pass
os._exit(0)
PY

exit 0
```

- [ ] **Step 4: Make the hook executable**

Run: `chmod +x /Users/ryanhurst/dev/claude-agent-loop/payload/hooks/read-guard.sh`
Expected: no output, exit 0. (The suite invokes the hook via `bash "$HOOK"`, so this is not strictly required for the test to pass, but the sibling hooks are executable and the installer symlinks a runnable file — match the convention.)

- [ ] **Step 5: Run the suite to verify it passes**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests && bash test_read_guard.sh`
Expected: PASS — every `PASS - ...` line prints, the suite ends with `test_read_guard: OK`, and the exit code is 0. Confirm all eight scenarios (cases 1, 2, 3, 4, 5, 6, 7a, 7b) report PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop
git add payload/hooks/read-guard.sh payload/tools/tests/test_read_guard.sh
git commit -F - <<'MSG'
feat(hooks): add read-guard PreToolUse hook with 8-case suite

(1) Task & Change
Add payload/hooks/read-guard.sh, a PreToolUse hook matched to the Read tool
that hard-blocks whole-file reads of never-read-whole file classes, soft-nudges
large reads issued without offset/limit, and fails open on every ambiguous
case. Implements the approved design in
docs/superpowers/specs/2026-07-14-read-guard-hook-design.md. All decision logic
runs in an embedded Python 3 heredoc behind a trivial bash wrapper, mirroring
precompact-event.sh; the hook always exits 0 and signals only through
hookSpecificOutput JSON.

(2) Tests created or modified
- payload/tools/tests/test_read_guard.sh — 8 cases: hard-blocked file (deny),
  hard-blocked directory segment (deny), small file (allow, no nudge), large
  file (allow + nudge), large file with offset/limit (allow, no nudge),
  malformed stdin (allow, no crash), missing file_path and unreadable path
  (allow). Modeled on test_precompact_tmx.sh.

(3) Test results — evidence
Command: bash payload/tools/tests/test_read_guard.sh
Output: all PASS lines; final line "test_read_guard: OK"; exit 0.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
MSG
```

---

### Task 2: Register the hook in `payload/MANIFEST`

**Files:**
- Modify: `payload/MANIFEST` (the `# --- hooks/ ---` block, currently ending at `link-file hooks/auto-update.sh`)

**Interfaces:**
- Consumes: the `read-guard.sh` file created in Task 1.
- Produces: an installer instruction that symlinks `payload/hooks/read-guard.sh` into `~/.claude/hooks/read-guard.sh`. Task 4's `test_install_symlinks.sh` run relies on this line being present.

- [ ] **Step 1: Add the `link-file` line**

Edit `payload/MANIFEST`. Find the hooks block:

```
# --- hooks/ ---------------------------------------------------------------
link-file hooks/inject-resource-loop.sh
link-file hooks/harvest-metrics.sh
link-file hooks/precompact-event.sh
link-file hooks/auto-update.sh
```

Replace it with (adds one line at the end of the block):

```
# --- hooks/ ---------------------------------------------------------------
link-file hooks/inject-resource-loop.sh
link-file hooks/harvest-metrics.sh
link-file hooks/precompact-event.sh
link-file hooks/auto-update.sh
link-file hooks/read-guard.sh
```

- [ ] **Step 2: Verify the line is present and well-formed**

Run: `grep -n 'read-guard.sh' /Users/ryanhurst/dev/claude-agent-loop/payload/MANIFEST`
Expected: one line, `link-file hooks/read-guard.sh`, printed under the hooks block (a line number in the low 200s). No other match.

- [ ] **Step 3: Commit**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop
git add payload/MANIFEST
git commit -F - <<'MSG'
build(manifest): install read-guard.sh into ~/.claude/hooks

(1) Task & Change
Add one link-file line under the MANIFEST hooks block so install.sh symlinks
payload/hooks/read-guard.sh into ~/.claude/hooks/read-guard.sh alongside the
four existing hooks. No new install test is needed — the existing
test_install_symlinks.sh MANIFEST-driven scenarios cover the new entry
automatically.

(2) Tests created or modified
- No new test. payload/tools/tests/test_install_symlinks.sh walks the MANIFEST
  and now exercises the read-guard.sh link/unlink path with no change.

(3) Test results — evidence
Command: grep -n 'read-guard.sh' payload/MANIFEST
Output: single match "link-file hooks/read-guard.sh" in the hooks block.
(Full install verification runs in the final verification task.)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
MSG
```

---

### Task 3: Register the hook in `payload/fragments/settings.fragment.json`

**Files:**
- Modify: `payload/fragments/settings.fragment.json` (the `"hooks"` object)

**Interfaces:**
- Consumes: the installed `~/.claude/hooks/read-guard.sh` path.
- Produces: a `"PreToolUse"` hook registration with `matcher` `"Read"` that fires `$HOME/.claude/hooks/read-guard.sh`. This is the first `matcher` field used anywhere in this repo's hook wiring; `"Read"` is an exact-string (all-letters) match.

- [ ] **Step 1: Add the `PreToolUse` block**

Edit `payload/fragments/settings.fragment.json`. Find the `UserPromptSubmit` block and the closing of the `"hooks"` object:

```json
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/hooks/auto-update.sh"
          }
        ]
      }
    ]
  },
```

Replace it with (adds a comma after `UserPromptSubmit`'s closing `]`, then the new `PreToolUse` key):

```json
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/hooks/auto-update.sh"
          }
        ]
      }
    ],
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
  },
```

- [ ] **Step 2: Verify the fragment is still valid JSON**

Run: `python3 -m json.tool /Users/ryanhurst/dev/claude-agent-loop/payload/fragments/settings.fragment.json > /dev/null && echo VALID`
Expected: `VALID` and exit 0. (A missing or misplaced comma would raise a `json.decoder.JSONDecodeError` and exit non-zero.)

- [ ] **Step 3: Confirm the matcher wiring**

Run: `python3 -c "import json; h=json.load(open('/Users/ryanhurst/dev/claude-agent-loop/payload/fragments/settings.fragment.json'))['hooks']['PreToolUse']; assert h[0]['matcher']=='Read'; assert h[0]['hooks'][0]['command'].endswith('read-guard.sh'); print('WIRED')"`
Expected: `WIRED` and exit 0.

- [ ] **Step 4: Commit**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop
git add payload/fragments/settings.fragment.json
git commit -F - <<'MSG'
build(settings): register read-guard.sh on PreToolUse/Read

(1) Task & Change
Add a PreToolUse hook block to the settings fragment with matcher "Read" firing
$HOME/.claude/hooks/read-guard.sh. This is the first matcher field in the
repo's hook wiring; "Read" is an exact-string (all-letters) match, safe on
every documented Claude Code version.

(2) Tests created or modified
- No executable unit test; the fragment is install-time input. Verified by JSON
  round-trip and a structural assertion on the matcher/command.

(3) Test results — evidence
Command: python3 -m json.tool payload/fragments/settings.fragment.json
Output: valid JSON (exit 0).
Command: python3 -c "...assert matcher=='Read' and command endswith read-guard.sh..."
Output: WIRED (exit 0).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
MSG
```

---

### Task 4: Final verification

**Files:**
- No file changes. This task runs the suites and confirms the wiring holds end to end.

**Interfaces:**
- Consumes: `read-guard.sh` (Task 1), the MANIFEST line (Task 2), and the settings fragment block (Task 3).
- Produces: recorded evidence that the new suite passes, that the full suite still passes, and that `test_install_symlinks.sh` (unmodified) picks up the MANIFEST wiring automatically.

- [ ] **Step 1: Run the read-guard suite in isolation**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests && bash test_read_guard.sh`
Expected: every `PASS - ...` line, final line `test_read_guard: OK`, exit 0.

- [ ] **Step 2: Run the install-symlinks suite (confirms the MANIFEST pickup)**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests && bash test_install_symlinks.sh`
Expected: PASS lines, exit 0. `test_install_symlinks.sh` walks the MANIFEST and now links/unlinks `hooks/read-guard.sh` in its throwaway `$HOME` sandbox with no change to the test file — the new `link-file` line is exercised automatically. (This is spec test case 8: no new install test is written; the existing MANIFEST-driven scenarios cover it.)

- [ ] **Step 3: Run the whole suite to confirm no regressions**

Run: `cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests && bash run_all.sh > /tmp/read_guard_run_all.log 2>&1; echo "exit=$?"; tail -5 /tmp/read_guard_run_all.log`
Expected: `exit=0` and a final summary line `run_all: N suites, 0 failed`. Confirm `PASS - test_read_guard.sh` and `PASS - test_install_symlinks.sh` both appear:
`grep -E 'test_read_guard.sh|test_install_symlinks.sh' /tmp/read_guard_run_all.log`
Expected: both lines prefixed `PASS - `.

- [ ] **Step 4: No commit needed**

This task changes no files; its output is the evidence recorded in the Task 1–3 commit bodies and in `/tmp/read_guard_run_all.log`. If the branch's purpose is complete, open a PR summarizing all four tasks (hook, tests, MANIFEST, settings fragment) and merge to the default branch.

---

## Self-Review

**1. Spec coverage.** Every spec section maps to a task:

- *Chosen approach — hard-block / soft-nudge / fail-open* → Task 1 (`hard_block_label`, the `is_large` nudge branch, and the two fail-open `try/except` layers).
- *Architecture — new file `payload/hooks/read-guard.sh`; bash wrapper + Python heredoc; `try/except` → `{}`; no `set -e`; always exit 0* → Task 1 Step 3 (verbatim).
- *Decision logic steps 1–5* → Task 1 Step 3: parse (default `{}`); extract `tool_input.file_path` (missing → allow); hard-block `label` match (deny); size + offset/limit nudge (allow + context); default plain allow.
- *Hard-blocked file classes* (lockfiles, `*.min.js`/`*.min.css`/`.bundle.`, `*.map`, `node_modules`/`dist`/`build`/`.vite`/`coverage` segments, `*.jsonl`, `*.log`, `*.csv`/`*.parquet`; HTML **excluded**) → `HARD_LOCKFILES`, `HARD_SEGMENTS`, and the `endswith`/infix checks in `hard_block_label`. No `*.html` rule — matches the deliberate exclusion.
- *Soft-nudge threshold — over 1,000 lines OR 100 KB, only when neither offset nor limit present* → `LINE_CAP = 1000`, `BYTE_CAP = 100 * 1024`, and the `"offset" not in ... and "limit" not in ...` guard.
- *`hookSpecificOutput` shape — `hookEventName` always `"PreToolUse"`; `permissionDecision` `"allow"`/`"deny"` only; reason on deny; `additionalContext` on nudged allow only* → the `allow`/`deny` helpers.
- *Registration — settings fragment `PreToolUse`/`Read` block; MANIFEST `link-file` line* → Task 3 and Task 2 (verbatim JSON and line).
- *Error handling — fail open; exit-0-only; never exit 2* → Task 1 Step 3 (`try/except` layers, `os._exit(0)`, `exit 0`) and the Global Constraints.
- *Bash-3.2 portability* → trivial bash layer + Python classification; recorded in Global Constraints and the "Resolved implementation decision" note.
- *Testing plan — 8 cases* → Task 1 Step 1 (cases 1, 2, 3, 4, 5, 6, 7a+7b) and case 8 (MANIFEST) verified in Task 4 Step 2.

No gaps found.

**2. Placeholder scan.** No `TBD`/`TODO`/`implement later`, no "add appropriate error handling," no "write tests for the above," no "similar to Task N." Every code step contains the actual, complete bash/JSON/Python content. Every referenced name (`hard_block_label`, `is_large`, `allow`, `deny`, `HARD_LOCKFILES`, `HARD_SEGMENTS`, `LINE_CAP`, `BYTE_CAP`, `assert_json`) is defined in the same task where it is used.

**3. Type consistency.** The JSON contract is identical across the hook and the test: `hookSpecificOutput.hookEventName == "PreToolUse"`, `permissionDecision` ∈ {`"allow"`, `"deny"`}, `permissionDecisionReason` (str, deny only), `additionalContext` (str, nudged allow only). The test asserts exactly the keys the hook emits — case 1 checks `permissionDecisionReason` contains `lockfile` (the hook's `"a lockfile"` label yields that substring); case 2 checks it contains `node_modules` (the hook's `"inside a node_modules/ directory"` label yields that); case 4 checks `additionalContext` contains `offset` (the hook's nudge names `offset/limit`). The `is_large` line/byte caps (`1000`/`100 * 1024`) match the 1,500-line fixture the test writes. No signature or key drift.
