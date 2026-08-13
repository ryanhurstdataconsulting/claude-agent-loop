# Dispatcher Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Move the four nightly repo-security-audit tools out of the flat
`payload/tools/` namespace into a `payload/tools/dispatch/` package, repair
every path reference they and their callers depend on, and make the sweep's
runner come from a job-definition file (`jobs/security-audit.yml`) selected by
a new `--job-type` flag — with the live 03:17 launchd job's behavior byte-for-byte
unchanged.

**Architecture:** A `git mv` of `audit_dispatch.py` / `audit_run.sh` /
`audit_store.py` / `audit_digest.py` to `dispatch/{dispatch.py,run.sh,store.py,digest.py}`,
followed by three classes of repair: same-directory Python imports, `run.sh`'s
sibling-lookup shell variables (which currently resolve two *different*
families of tool from one variable), and the six test files plus the launchd
plist, the SessionStart hook, and `MANIFEST` that name the old paths. The
generalization itself is deliberately one axis wide: `dispatch.py` gains
`--job-type <name>`, which loads `jobs/<name>.yml` from beside itself and reads
one key out of it — `runner`, the per-package script the sweep invokes. Job #1
(`security-audit`) declares `runner: run.sh`, which is exactly what the
hardcoded sibling lookup resolved to before.

**Tech Stack:** Python 3 stdlib only (no PyYAML — see Grounding correction 3),
bash 3.2-portable shell, macOS `launchd`, `unittest` (via
`payload/tools/tests/run_all.sh`, which runs `python3 -m unittest <name>` and
`bash <file>` — not pytest).

**Spec:** `docs/superpowers/specs/2026-08-06-agent-loop-v2-design.md`
(Phase 5 — "Dispatcher generalization", lines 290–301)

## Grounding correction (read before Task 1)

Five things the spec's two-sentence Phase 5 description does not say, each
found by reading the code rather than the spec.

**1. `run.sh` resolves two different tool families through one variable, and
the rename splits them.** `audit_run.sh` computes `SELF_DIR` and then uses it
for three separate lookups: the two safety gates (`secret_pii_scrub_gate.py`,
`prose_grammar_gate.py`, via `GATE_DIR`), `audit_store.py` (via `TOOL_DIR`,
line 419), and `obs_emit.py` (also via `TOOL_DIR`, line 451). After the move,
`store.py` is a sibling in `dispatch/` while the gates and `obs_emit.py` stay
one level up in `tools/`. One variable can no longer serve both, so `TOOL_DIR`
is redefined as "the `tools/` directory one level up" (which keeps
`obs_emit.py` and the gates resolving, and keeps
`test_audit_run_kind_run.sh`'s existing `TOOL_DIR=` injection working
unchanged), and a new `DISPATCH_DIR` resolves `store.py` beside the script.
Both keep the existing sibling-then-`$HOME/.claude` fallback shape.

**2. The spec says "renamed in place" but does not mention `MANIFEST`, which
currently ships these four files as four individual `link-file` lines.** The
installer (`install.sh`, lines 174–199) understands exactly three verbs —
`link-dir`, `link-file`, `copy-if-absent` — and treats `link-dir` and
`link-file` identically (both call `link_entry`, which makes one symlink).
So the four `link-file tools/audit_*` lines become one `link-dir tools/dispatch`,
which has the additional property of carrying `jobs/security-audit.yml` into
the installed tree automatically — code and its job definitions can never
drift out of sync, because they are the same symlink. This does mean a machine
installed before this change keeps four now-dangling `~/.claude/tools/audit_*`
symlinks until it is reinstalled; that cleanup belongs to the deployment step,
which is Ryan's, not this plan's.

**3. The spec says `.yml`, but PyYAML is not a dependency this code may take.**
All four modules document themselves as "Stdlib only — no third-party imports,
so this tool has no install step and no supply-chain surface of its own," and
no file under `payload/tools/` imports `yaml`. PyYAML happens to be present on
this machine as a user-level `pip install --user` under Python 3.9, but the
launchd job runs `/usr/bin/env python3` inside `bash -lc` on whatever machine
the framework is installed to — making an unattended nightly job depend on an
un-vendored third-party import is exactly the failure this codebase avoids
elsewhere. This plan honors the spec's `.yml` filename and adds a **strict,
flat-subset parser** (`_parse_job_yaml`, roughly 25 lines) that accepts only
`key: value` lines, full-line `#` comments, and blank lines, and **raises on
anything else** — indentation, list items, a line with no colon, a duplicate
key. Rejecting loudly is the point: a job definition names the executable an
unattended sweep will run, so a silent mis-parse is a safety hole, not a
convenience gap. Job files must stay inside that subset; the parser is not a
YAML implementation and does not pretend to be one.

**4. `--job-type` cannot generalize the store layout, and this plan does not
pretend it does.** `store.py` hardcodes `audit/` as the store subtree
(`SUBDIRS`, `load_config`, `commit_paths`), `digest.py` hardcodes
`audit/runs` and `audit/digests`, and `run.sh` hardcodes
`$STORE/audit/runs/$PKG_KEY`. Generalizing all of that is a much larger
refactor than Phase 5 asks for and would change the on-disk layout of a live
store. The one axis that genuinely differs between job types — and the only
one the spec's own deferred examples (`dep-refresh`, `doc-drift`,
`metric-summary`) would need — is *which script runs against each due
package*. That is what the job definition carries. Everything else (tier
scheduling, due selection, the store, the digest) is shared machinery that all
job types would use identically.

**5. Three of the spec's four job types are explicitly out of scope, by the
spec's own instruction.** `dep-refresh.yml`, `doc-drift.yml`, and
`metric-summary.yml` are to be "added after the rename is proven on at least
one real nightly run." That live validation has not happened — this plan only
changes the dev repo, and deployment onto the machine that runs the 03:17 job
is a separate, deliberate, owner-held step. So this plan ships exactly one job
definition, `security-audit`, and deliberately leaves the other three unwritten.
They are deferred, not forgotten.

## Deliberate decisions recorded here rather than left implicit

- **Registry row IDs stay `audit-store` / `audit-dispatch` / `audit-run` /
  `audit-digest`.** The rows describe behavior, not file paths, and none of the
  four contains a path at all — only the guide files' "Lives at" and "Interface"
  lines do. Renaming the rows would churn every cross-reference in five guide
  files to describe the same four tools doing the same four jobs.
- **The six test files keep their `test_audit_*` names.** They test the
  repo-security-audit pipeline, which is still what these tools are; renaming
  them adds churn with no functional gain, and `run_all.sh`'s `test_*.py` /
  `test_*.sh` globs are non-recursive over `payload/tools/tests/`, so the tests
  must stay in that directory regardless.
- **The `AUDIT_*` environment-variable namespace is preserved verbatim**
  (`AUDIT_RUN_BIN`, `AUDIT_GATE_DIR`, `AUDIT_CLAUDE_BIN`, `AUDIT_NOTIFY`,
  `AUDIT_MAX_TURNS`, `AUDIT_TIMEOUT`, `AUDIT_GIT_TIMEOUT`), as is the
  `--audit-run-bin` CLI flag. These are a documented test-and-calibration
  contract that the guides and the test harness both rely on; the job file is
  the new generalization axis, not the override names.
- **The `--dispatch-run-id` value keeps its `night-<date>-<package>` format.**
  Adding the job type to it would be correct once a second job type exists (two
  job types sweeping the same package on the same night would otherwise collide),
  but changing it now would alter the live nightly job's emitted OTel attribute
  for no present benefit. It is noted in `dispatch.py` as the follow-up that
  belongs with job #2.

## Global Constraints

- **The live `~/.claude` install is never touched.** This plan changes only
  this dev repo's `payload/` tree and its root-level docs. Deployment and
  migration onto the machine running the 03:17 job is a separate owner-held step.
- **Stdlib only** in all four Python modules — no third-party imports, no
  install step, no supply-chain surface. This is a documented invariant of every
  one of them.
- **`run.sh` stays macOS bash-3.2 portable**: no `mapfile`, no associative
  arrays, no `set -e`.
- **The existing nightly job's runtime behavior does not change.** Same runner,
  same store paths, same run-id format, same exit codes, same JSON keys plus one
  additive `job_type`.
- **`git mv`, never delete-and-recreate** — history must follow the files.
- **Stage explicit paths** (`git add <path>`), never `git add -A` or `git add .`.
- **New commits only, never `--amend`.** Never push, never merge to `main`.
- Commit bodies use the three-section format: `(1) Task & Change`,
  `(2) Tests created / modified`, `(3) Test results — evidence` with real
  command output pasted, never paraphrased.

---

## File Structure

**Moved (via `git mv`, contents edited in the same commit):**

| From | To | Responsibility |
|---|---|---|
| `payload/tools/audit_dispatch.py` | `payload/tools/dispatch/dispatch.py` | Nightly sweep: select due packages, run each, close with a digest |
| `payload/tools/audit_run.sh` | `payload/tools/dispatch/run.sh` | One package, one unattended audit, inside a throwaway worktree |
| `payload/tools/audit_store.py` | `payload/tools/dispatch/store.py` | The local-only, no-remote output store and its git history |
| `payload/tools/audit_digest.py` | `payload/tools/dispatch/digest.py` | Severity gating, the batched digest, the SessionStart nudge |

**Created:**
- `payload/tools/dispatch/jobs/security-audit.yml` — job #1's definition.

**Modified (path repairs, Task 1):**
- `payload/tools/tests/test_audit_dispatch.py` — import paths, the default-runner assertion, three `mock.patch.object` targets.
- `payload/tools/tests/test_audit_store.py` — import path.
- `payload/tools/tests/test_audit_digest.py` — import paths (module level and one in-method import).
- `payload/tools/tests/test_audit_run.sh` — `SCRIPT=` path, one embedded `import audit_dispatch`.
- `payload/tools/tests/test_audit_run_kind_run.sh` — `AUDIT_RUN=` path.
- `payload/tools/tests/test_audit_run_retry.sh` — `AUDIT_RUN=` path.
- `payload/tools/tests/test_hook_inject.sh` — the `cp` that stages fake installed tools.
- `payload/hooks/inject-resource-loop.sh` — `AUDIT_DIGEST_TOOL` path.
- `payload/launchd/com.hdc.claude-agent-loop.repo-audit.plist` — `ProgramArguments`.
- `payload/MANIFEST` — four `link-file` lines become one `link-dir`.

**Modified (documentation, Task 3):**
- `ARCHITECTURE.md`, `INSTALL.md`, `payload/registry/guides/audit-{dispatch,run,store,digest}.md`,
  `payload/registry/guides/repo-audit-action.md`,
  `payload/observability/alerts/{cost-per-day,repo-audit-silent}.yaml`,
  `payload/observability/dashboards/{run-timelines,scheduler-liveness}.json`.

**Deliberately not modified:** the historical plan and spec documents under
`docs/superpowers/plans/2026-08-05-obs-phase*.md`,
`docs/superpowers/specs/2026-08-05-agent-observability-layer-design.md`, and
the `link-file tools/audit_store.py` textual anchors in
`docs/superpowers/plans/2026-08-13-plan-{worktree-execute,consensus-gate}.md`.
These are accurate records of what those phases did to the files as they existed
then; rewriting history to match a later rename would make them lie.

---

### Task 1: Rename the four tools and repair every path that named them

The spec requires the plist re-point to land **in the same commit as the
rename**, "so the nightly run is never left pointing at a deleted file." That
makes this one commit rather than several. There is no new behavior here, so
there is no new test to write first: the existing 123 Python test cases and
three shell suites *are* the test, and a green run after the move is the proof
that nothing broke.

**Files:**
- Move: the four files in the table above.
- Modify: the ten files in the "Modified (path repairs)" list above.
- Test: `payload/tools/tests/test_audit_{dispatch,store,digest}.py`,
  `test_audit_run.sh`, `test_audit_run_kind_run.sh`, `test_audit_run_retry.sh`,
  `test_hook_inject.sh`.

**Interfaces:**
- Consumes: nothing from earlier tasks (this is the first).
- Produces: `payload/tools/dispatch/` as an importable directory whose modules
  are `dispatch`, `run.sh`, `store`, `digest`. Task 2 adds `load_job()` and
  `runner_bin()` to `dispatch.py`; Task 3 documents the new paths.

- [ ] **Step 1: Confirm the suite is green BEFORE the move**

This is the baseline the post-move run is compared against. Without it, a
pre-existing failure would be misread as rename damage.

```bash
cd /Users/ryanhurst/dev/claude-agent-loop
mkdir -p /tmp/agent-loop-phase5
bash payload/tools/tests/run_all.sh > /tmp/agent-loop-phase5/baseline.log 2>&1; echo "exit=$?"
tail -20 /tmp/agent-loop-phase5/baseline.log
```

Expected: a summary line reporting 0 failed. Record the exact suite/failure
counts — they are the numbers Step 12 must match or beat.

- [ ] **Step 2: `git mv` the four files**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop
mkdir -p payload/tools/dispatch
git mv payload/tools/audit_dispatch.py payload/tools/dispatch/dispatch.py
git mv payload/tools/audit_run.sh      payload/tools/dispatch/run.sh
git mv payload/tools/audit_store.py    payload/tools/dispatch/store.py
git mv payload/tools/audit_digest.py   payload/tools/dispatch/digest.py
git status --short
```

Expected: four `R` (rename) entries, no `D`/`A` pairs. If git shows `D`+`??`
instead, the move was done wrong — reset and redo with `git mv`.

- [ ] **Step 3: Repair `dispatch.py`'s same-directory imports and its docstring**

`payload/tools/dispatch/dispatch.py` lines 58–60 currently read:

```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_digest
import audit_store
```

Replace with:

```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import digest
import store
```

Then replace every use of the old module names in the body:
`audit_store.ConfigError` → `store.ConfigError` (line ~343),
`audit_store.store_root()` → `store.store_root()` (lines ~500, ~528),
`audit_store.ensure_store` / `.assert_no_remote` / `.load_config` →
`store.*` (lines ~533–535), `audit_digest.severity_alert` →
`digest.severity_alert` (line ~489), `audit_digest.write_digest` →
`digest.write_digest` (line ~569).

Also update the module docstring's file references: `audit_store` → `store`,
`audit_run.sh` → `run.sh`, `audit_digest` → `digest`, and change the opening
identity line from `"""audit_dispatch — the nightly repo-security-audit sweep: decide, then run.`
to `"""dispatch — the nightly repo-security-audit sweep: decide, then run.`
(that first line is `main()`'s argparse description, so it is user-facing text).

Finally, line 368's hardcoded default runner filename:

```python
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "audit_run.sh")
```

becomes:

```python
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "run.sh")
```

- [ ] **Step 4: Repair `digest.py`'s same-directory import and its docstring**

`payload/tools/dispatch/digest.py` lines 47–48 currently read:

```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_store  # noqa: E402  (path set up above)
```

Replace with:

```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402  (path set up above)
```

Then `audit_store.store_root` → `store.store_root` (lines ~18, ~340, ~348) and
`audit_store.commit_paths` → `store.commit_paths` (line ~291). Update the
docstring's `audit_run.sh` → `run.sh`, `audit_dispatch.last_state` →
`dispatch.last_state`, `audit_store.store_root` → `store.store_root`, and the
identity line to `"""digest — the surfacing layer for the repo-security-audit scheduler.`

- [ ] **Step 5: Repair `store.py`'s docstring only (it imports nothing local)**

`store.py` has no local imports — it needs no code change. Update its
docstring's identity line to `"""store — the consolidated output store for the repo-security-audit scheduler.`
and its references to `audit_run.sh` → `run.sh` and
`audit_digest.write_digest` → `digest.write_digest` (in `commit_paths`'
docstring).

- [ ] **Step 6: Split `run.sh`'s tool lookups (the load-bearing shell repair)**

`payload/tools/dispatch/run.sh` lines 59–80 currently read:

```bash
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- gate location ------------------------------------------------------------
# The gates sit beside this script both in the framework checkout and in the
# installed ~/.claude/tools tree, so a sibling lookup covers both; the explicit
# fallback covers an unusual install, and the env override keeps tests hermetic.
GATE_DIR="${AUDIT_GATE_DIR:-}"
if [ -z "$GATE_DIR" ]; then
  if [ -f "$SELF_DIR/secret_pii_scrub_gate.py" ]; then
    GATE_DIR="$SELF_DIR"
  else
    GATE_DIR="$HOME/.claude/tools"
  fi
fi

# audit_store.py sits beside this script in both trees, the same way the gates
# do, so the same sibling-then-fallback lookup resolves it.
if [ -f "$SELF_DIR/audit_store.py" ]; then
  TOOL_DIR="$SELF_DIR"
else
  TOOL_DIR="$HOME/.claude/tools"
fi
```

Replace that whole block with:

```bash
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- tools/ location ----------------------------------------------------------
# This script lives in tools/dispatch/, so the wider tools/ tree — the two
# safety gates and obs_emit.py — is one level up, in the framework checkout and
# in the installed ~/.claude tree alike (MANIFEST links tools/dispatch as a
# directory, so `..` from it is ~/.claude/tools). The explicit fallback covers
# an unusual install where that parent is not the tools tree.
TOOL_DIR="$(cd "$SELF_DIR/.." 2>/dev/null && pwd)"
if [ -z "$TOOL_DIR" ] || [ ! -f "$TOOL_DIR/obs_emit.py" ]; then
  TOOL_DIR="$HOME/.claude/tools"
fi

# --- gate location ------------------------------------------------------------
# The gates live in tools/ alongside obs_emit.py; the env override keeps tests
# hermetic.
GATE_DIR="${AUDIT_GATE_DIR:-}"
if [ -z "$GATE_DIR" ]; then
  if [ -f "$TOOL_DIR/secret_pii_scrub_gate.py" ]; then
    GATE_DIR="$TOOL_DIR"
  else
    GATE_DIR="$HOME/.claude/tools"
  fi
fi

# store.py sits beside this script in both trees, so a sibling lookup with the
# same shape resolves it — but it is a DIFFERENT directory from TOOL_DIR now
# that this script lives one level down, which is why it gets its own variable.
if [ -f "$SELF_DIR/store.py" ]; then
  DISPATCH_DIR="$SELF_DIR"
else
  DISPATCH_DIR="$HOME/.claude/tools/dispatch"
fi
```

Then line 419's store invocation:

```bash
  python3 "$TOOL_DIR/audit_store.py" --root "$STORE" --message "$msg" commit \
```

becomes:

```bash
  python3 "$DISPATCH_DIR/store.py" --root "$STORE" --message "$msg" commit \
```

Line 451's `TOOLS_DIR="$TOOL_DIR"` (which feeds `obs_emit.py`'s lookup) stays
exactly as it is — `TOOL_DIR` now means the `tools/` tree, which is where
`obs_emit.py` still lives, and `test_audit_run_kind_run.sh` injects that same
variable name.

Finally update the header comment and `usage()` text: `audit_run.sh` → `run.sh`
(lines 2, 4, 93), `audit_store.py` → `store.py` (the comment at line 74 is
replaced above), `audit_dispatch.last_state()` → `dispatch.last_state()`
(line 174), `audit_dispatch.py's` → `dispatch.py's` (lines 184, 853), and the
`audit_run:` message prefixes stay as they are — that string is the tool's
log identity, not a filename.

- [ ] **Step 7: Repair the three Python test files**

`payload/tools/tests/test_audit_dispatch.py` lines 23–26:

```python
TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import audit_dispatch as ad  # noqa: E402  (path set up above)
import audit_store as st  # noqa: E402
```

becomes:

```python
TOOLS = pathlib.Path(__file__).resolve().parent.parent
DISPATCH = TOOLS / "dispatch"
sys.path.insert(0, str(DISPATCH))
import dispatch as ad  # noqa: E402  (path set up above)
import store as st  # noqa: E402
```

Line 658's default-runner assertion:

```python
            self.assertEqual(ad.audit_run_bin(), str(TOOLS / "audit_run.sh"))
```

becomes:

```python
            self.assertEqual(ad.audit_run_bin(), str(DISPATCH / "run.sh"))
```

and its enclosing test's name changes from
`test_the_default_is_the_sibling_audit_run_script` to
`test_the_default_is_the_sibling_run_script`.

The three `mock.patch.object(ad.audit_digest, "write_digest")` calls (lines
479, 494, 504) become `mock.patch.object(ad.digest, "write_digest")`.

`payload/tools/tests/test_audit_store.py` lines 18–20:

```python
TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import audit_store as st  # noqa: E402  (path set up above)
```

becomes:

```python
TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS / "dispatch"))
import store as st  # noqa: E402  (path set up above)
```

`payload/tools/tests/test_audit_digest.py` lines 23–26:

```python
TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import audit_digest as ad  # noqa: E402  (path set up above)
import prose_grammar_gate as pg  # noqa: E402
```

becomes (note that `prose_grammar_gate` does *not* move, so `TOOLS` must stay
on the path too):

```python
TOOLS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "dispatch"))
import digest as ad  # noqa: E402  (path set up above)
import prose_grammar_gate as pg  # noqa: E402
```

and the in-method import at line 258, `import audit_store as st`, becomes
`import store as st`.

- [ ] **Step 8: Repair the four shell test files**

`test_audit_run.sh` line 19:

```bash
SCRIPT="$(cd "$HERE/.." && pwd)/audit_run.sh"
```
becomes
```bash
SCRIPT="$(cd "$HERE/.." && pwd)/dispatch/run.sh"
```

and its embedded round-trip check at lines 240–245:

```bash
ROUNDTRIP="$(cd "$HERE/.." && python3 -c '
import sys
sys.path.insert(0, ".")
import audit_dispatch
print(audit_dispatch.last_state(sys.argv[1], sys.argv[2]).get("last_audited_sha") or "")
' "$STORE" "$NESTED_KEY" 2>/dev/null)"
```

becomes:

```bash
ROUNDTRIP="$(cd "$HERE/../dispatch" && python3 -c '
import sys
sys.path.insert(0, ".")
import dispatch
print(dispatch.last_state(sys.argv[1], sys.argv[2]).get("last_audited_sha") or "")
' "$STORE" "$NESTED_KEY" 2>/dev/null)"
```

`test_audit_run_kind_run.sh` line 10:

```bash
AUDIT_RUN="$TOOLS_ROOT/audit_run.sh"
```
becomes
```bash
AUDIT_RUN="$TOOLS_ROOT/dispatch/run.sh"
```

(`TOOLS_ROOT` itself is unchanged and its `TOOL_DIR="$TOOLS_ROOT"` injections at
lines 38, 47, and 55 stay — `obs_emit.py` is still in `payload/tools/`. Update
the `die` message at line 24, which names `audit_run.sh`, to say `run.sh`.)

`test_audit_run_retry.sh` line 9:

```bash
AUDIT_RUN="$(cd "$HERE/.." && pwd)/audit_run.sh"
```
becomes
```bash
AUDIT_RUN="$(cd "$HERE/.." && pwd)/dispatch/run.sh"
```

`test_hook_inject.sh` lines 156–162 — the fake-install `cp`:

```bash
# Build an isolated HOME with audit_digest.py (and its audit_store.py
# dependency) installed. Prints the HOME path.
audit_home() {
  h="$SANDBOX/$1"
  rm -rf "$h"
  mkdir -p "$h/.claude/tools" "$h/.claude/metrics/audit/digests"
  cp "$TOOLS/audit_digest.py" "$TOOLS/audit_store.py" "$h/.claude/tools/" 2>/dev/null
  printf '%s' "$h"
}
```

becomes:

```bash
# Build an isolated HOME with dispatch/digest.py (and its dispatch/store.py
# dependency) installed. Prints the HOME path.
audit_home() {
  h="$SANDBOX/$1"
  rm -rf "$h"
  mkdir -p "$h/.claude/tools/dispatch" "$h/.claude/metrics/audit/digests"
  cp "$TOOLS/dispatch/digest.py" "$TOOLS/dispatch/store.py" \
     "$h/.claude/tools/dispatch/" 2>/dev/null
  printf '%s' "$h"
}
```

- [ ] **Step 9: Re-point the SessionStart hook**

`payload/hooks/inject-resource-loop.sh` line 123:

```bash
AUDIT_DIGEST_TOOL="$HOME/.claude/tools/audit_digest.py"
```
becomes
```bash
AUDIT_DIGEST_TOOL="$HOME/.claude/tools/dispatch/digest.py"
```

and the comment two lines above it, which reads
`# (see severity_alert in audit_digest.py — the same rule drives its own OS`,
becomes `# (see severity_alert in dispatch/digest.py — the same rule drives its own OS`.
The `audit_run.sh` on the line before it becomes `dispatch/run.sh`.

- [ ] **Step 10: Re-point the launchd plist (the same-commit requirement)**

`payload/launchd/com.hdc.claude-agent-loop.repo-audit.plist` line 29:

```xml
        <string>LOGS="$HOME/.claude/metrics/audit/logs"; mkdir -p "$LOGS"; exec /usr/bin/env python3 "$HOME/.claude/tools/audit_dispatch.py" >>"$LOGS/repo-audit.out.log" 2>>"$LOGS/repo-audit.err.log"</string>
```

becomes:

```xml
        <string>LOGS="$HOME/.claude/metrics/audit/logs"; mkdir -p "$LOGS"; exec /usr/bin/env python3 "$HOME/.claude/tools/dispatch/dispatch.py" >>"$LOGS/repo-audit.out.log" 2>>"$LOGS/repo-audit.err.log"</string>
```

and the comment at line 23, `audit_dispatch falls back`, becomes
`dispatch.py falls back`.

- [ ] **Step 11: Replace the four MANIFEST entries with one `link-dir`**

`payload/MANIFEST` lines 216–219:

```
link-file tools/audit_digest.py
link-file tools/audit_dispatch.py
link-file tools/audit_run.sh
link-file tools/audit_store.py
```

becomes (keeping the file's alphabetical ordering within its section, and
placing the `link-dir` beside the other `link-dir` entries for `tools/` at
lines 257–258):

```
# The dispatcher and its job definitions ship as one directory so code and
# jobs/*.yml can never drift apart across an install.
link-dir tools/dispatch
```

Verify no other `link-file tools/audit_` line remains:

```bash
grep -n "audit" payload/MANIFEST
```
Expected: no output.

- [ ] **Step 12: Run the full suite and confirm it matches the Step 1 baseline**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop
bash payload/tools/tests/run_all.sh > /tmp/agent-loop-phase5/after-rename.log 2>&1; echo "exit=$?"
tail -20 /tmp/agent-loop-phase5/after-rename.log
grep -c FAIL /tmp/agent-loop-phase5/after-rename.log
```

Expected: the same suite count and the same `0 failed` as Step 1. Any new
failure is rename damage — fix it before committing, do not commit a red tree.

- [ ] **Step 13: Commit**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop
git add payload/tools/dispatch payload/tools/tests/test_audit_dispatch.py \
        payload/tools/tests/test_audit_store.py payload/tools/tests/test_audit_digest.py \
        payload/tools/tests/test_audit_run.sh payload/tools/tests/test_audit_run_kind_run.sh \
        payload/tools/tests/test_audit_run_retry.sh payload/tools/tests/test_hook_inject.sh \
        payload/hooks/inject-resource-loop.sh \
        payload/launchd/com.hdc.claude-agent-loop.repo-audit.plist \
        payload/MANIFEST
git commit
```

Subject: `refactor(dispatch): move the four audit tools into tools/dispatch/`.
The body must state, in section (1), that the plist re-point rides in this same
commit deliberately, per the spec's Phase 5 requirement.

---

### Task 2: `--job-type` and `jobs/security-audit.yml`

This is the only new behavior in the phase, so it is TDD: the tests come first
and must be seen to fail.

**Files:**
- Create: `payload/tools/dispatch/jobs/security-audit.yml`
- Modify: `payload/tools/dispatch/dispatch.py`
- Test: `payload/tools/tests/test_audit_dispatch.py`

**Interfaces:**
- Consumes: `payload/tools/dispatch/` from Task 1, imported in the test as
  `import dispatch as ad`.
- Produces, all on `dispatch.py`:
  - `class JobError(Exception)` — missing, malformed, or unsafe job definition.
  - `JOBS_DIR_ENV = "AUDIT_JOBS_DIR"`, `DEFAULT_JOB_TYPE = "security-audit"`,
    `DEFAULT_RUNNER = "run.sh"`.
  - `jobs_dir() -> str` — `$AUDIT_JOBS_DIR` if set (even if empty), else
    `<dispatch dir>/jobs`.
  - `load_job(job_type: str, directory: str | None = None) -> dict` — returns
    the parsed definition with `job_type` and `runner` guaranteed present and
    validated; raises `JobError` otherwise.
  - `runner_bin(job: dict | None = None) -> str` — replaces `audit_run_bin()`.
    `$AUDIT_RUN_BIN` still wins when set (including when set but empty), else
    `<dispatch dir>/<job["runner"] or DEFAULT_RUNNER>`.
  - `main()` gains `--job-type` (default `security-audit`) and both JSON output
    shapes gain a `"job_type"` key.

- [ ] **Step 1: Write the failing tests**

Append to `payload/tools/tests/test_audit_dispatch.py`, before the
`if __name__ == "__main__":` block:

```python
class TestJobDefinitions(unittest.TestCase):
    """The job definition is what makes the dispatcher job-type-generic."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_the_shipped_security_audit_job_declares_run_sh(self):
        job = ad.load_job("security-audit")
        self.assertEqual(job["job_type"], "security-audit")
        self.assertEqual(job["runner"], "run.sh")

    def test_the_shipped_job_resolves_to_the_sibling_runner(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            resolved = ad.runner_bin(ad.load_job("security-audit"))
        self.assertEqual(
            resolved,
            str(pathlib.Path(ad.__file__).resolve().parent / "run.sh"))

    def test_comments_and_blank_lines_are_ignored(self):
        self._write("j.yml", "# a comment\n\njob_type: j\nrunner: r.sh\n")
        job = ad.load_job("j", self.tmp)
        self.assertEqual(job["runner"], "r.sh")

    def test_quoted_values_are_unquoted(self):
        self._write("j.yml", 'job_type: j\nrunner: "r.sh"\n')
        self.assertEqual(ad.load_job("j", self.tmp)["runner"], "r.sh")

    def test_a_missing_job_definition_is_loud(self):
        with self.assertRaises(ad.JobError) as caught:
            ad.load_job("no-such-job", self.tmp)
        self.assertIn("no-such-job", str(caught.exception))

    def test_a_job_without_a_runner_is_refused(self):
        self._write("j.yml", "job_type: j\n")
        with self.assertRaises(ad.JobError):
            ad.load_job("j", self.tmp)

    def test_an_absolute_runner_is_refused(self):
        self._write("j.yml", "runner: /bin/sh\n")
        with self.assertRaises(ad.JobError) as caught:
            ad.load_job("j", self.tmp)
        self.assertIn("relative", str(caught.exception))

    def test_a_runner_escaping_the_dispatch_directory_is_refused(self):
        self._write("j.yml", "runner: ../../evil.sh\n")
        with self.assertRaises(ad.JobError) as caught:
            ad.load_job("j", self.tmp)
        self.assertIn("..", str(caught.exception))

    def test_a_job_type_containing_a_path_is_refused(self):
        with self.assertRaises(ad.JobError) as caught:
            ad.load_job("../../etc/passwd", self.tmp)
        self.assertIn("bare file name", str(caught.exception))

    def test_a_mismatched_declared_job_type_is_refused(self):
        self._write("j.yml", "job_type: something-else\nrunner: r.sh\n")
        with self.assertRaises(ad.JobError) as caught:
            ad.load_job("j", self.tmp)
        self.assertIn("something-else", str(caught.exception))

    def test_nested_structure_is_refused_rather_than_silently_dropped(self):
        self._write("j.yml", "runner: r.sh\nnested:\n  key: value\n")
        with self.assertRaises(ad.JobError) as caught:
            ad.load_job("j", self.tmp)
        self.assertIn("flat", str(caught.exception))

    def test_a_list_item_is_refused_rather_than_silently_dropped(self):
        self._write("j.yml", "runner: r.sh\n- one\n")
        with self.assertRaises(ad.JobError):
            ad.load_job("j", self.tmp)

    def test_a_line_with_no_colon_is_refused(self):
        self._write("j.yml", "runner: r.sh\ngarbage\n")
        with self.assertRaises(ad.JobError):
            ad.load_job("j", self.tmp)

    def test_a_duplicate_key_is_refused(self):
        self._write("j.yml", "runner: r.sh\nrunner: other.sh\n")
        with self.assertRaises(ad.JobError) as caught:
            ad.load_job("j", self.tmp)
        self.assertIn("duplicate", str(caught.exception))

    def test_the_env_override_still_wins_over_the_job_definition(self):
        with mock.patch.dict(os.environ, {ad.AUDIT_RUN_BIN_ENV: "/stub/x.sh"}):
            self.assertEqual(ad.runner_bin({"runner": "r.sh"}), "/stub/x.sh")

    def test_an_empty_env_override_still_resolves_empty_and_fails_loudly(self):
        with mock.patch.dict(os.environ, {ad.AUDIT_RUN_BIN_ENV: ""}):
            self.assertEqual(ad.runner_bin({"runner": "r.sh"}), "")

    def test_the_jobs_dir_env_override_is_honoured(self):
        with mock.patch.dict(os.environ, {ad.JOBS_DIR_ENV: self.tmp}):
            self.assertEqual(ad.jobs_dir(), self.tmp)
```

And, in the existing `TestMainCli` class, one test proving the flag reaches the
output and one proving a bad job type stops the sweep:

```python
    def test_the_job_type_is_reported_in_the_json_output(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ad.main(["--root", self.tmp, "--workspace", self.ws,
                          "--dry-run", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["job_type"],
                         "security-audit")

    def test_an_unknown_job_type_raises_rather_than_running_anything(self):
        with self.assertRaises(ad.JobError):
            ad.main(["--root", self.tmp, "--workspace", self.ws,
                     "--dry-run", "--job-type", "no-such-job"])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests
python3 -m unittest test_audit_dispatch -v 2>&1 | tail -30
```

Expected: FAIL/ERROR on every new test, with `AttributeError: module 'dispatch'
has no attribute 'load_job'` (and `JobError`, `runner_bin`, `jobs_dir`,
`JOBS_DIR_ENV`) — plus `unrecognized arguments: --job-type` for the two
`TestMainCli` additions.

- [ ] **Step 3: Write `jobs/security-audit.yml`**

Create `payload/tools/dispatch/jobs/security-audit.yml`:

```yaml
# security-audit — job #1 for the nightly dispatcher.
#
# This is the job the 03:17 launchd run has always executed; it was hardcoded
# in dispatch.py until Phase 5 of the agent-loop-v2 design moved it here.
# Selecting it is the default, so the plist passes no --job-type at all.
#
# FORMAT: a flat map of `key: value` lines, plus blank lines and full-line
# `#` comments. Nothing else is accepted — no nesting, no lists, no inline
# comments. dispatch.py parses this with a small strict reader rather than
# PyYAML, because the tools in this directory are stdlib-only by design and
# an unattended nightly job must not depend on a third-party import that may
# not be installed on the machine it runs on. A line outside the subset raises
# rather than being skipped: this file names the executable the sweep runs, so
# a silent mis-parse would be a safety hole.
#
# Keys:
#   job_type — must match this file's name; the file name is the identity.
#   runner   — the per-package script, relative to tools/dispatch/. Never
#              absolute, never containing '..'.
job_type: security-audit
runner: run.sh
description: One unattended repo-security audit per due package, inside a throwaway worktree.
```

- [ ] **Step 4: Implement the loader and the flag in `dispatch.py`**

Add near the other module constants (after `DEFAULT_WORKSPACE`):

```python
JOBS_DIR_ENV = "AUDIT_JOBS_DIR"

#: The job this sweep runs when nothing says otherwise. The launchd plist
#: passes no --job-type, so this default is what the nightly run resolves.
DEFAULT_JOB_TYPE = "security-audit"

#: The per-package script a job definition falls back to. Only reached by a
#: caller that resolves a runner without a job (``run_package``'s own default);
#: a real sweep always goes through ``load_job``, which requires ``runner``.
DEFAULT_RUNNER = "run.sh"


class JobError(Exception):
    """Raised when a job definition is missing, malformed, or unsafe."""
```

Then the three functions:

```python
def jobs_dir():
    """Return the directory holding ``<job-type>.yml`` definitions.

    ``AUDIT_JOBS_DIR`` overrides the sibling lookup and is read with no
    default, so a harness that computes an EMPTY path gets the empty path and
    fails loudly rather than silently falling through to the shipped
    definitions — the same rule :func:`runner_bin` applies to
    ``AUDIT_RUN_BIN``, for the same reason.
    """
    override = os.environ.get(JOBS_DIR_ENV)
    if override is not None:
        return override
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs")


def _parse_job_yaml(text, path):
    """Parse the flat ``key: value`` subset a job definition may use.

    Deliberately NOT a YAML implementation. Accepts blank lines, full-line
    ``#`` comments, and ``key: value`` pairs whose value may be wrapped in
    matched single or double quotes. Everything else — an indented line, a
    list item, a line with no colon, an empty key, a repeated key — raises
    :class:`JobError`.

    Raising rather than skipping is the whole design. This file names the
    executable an unattended nightly sweep will run, so a construct the reader
    does not understand must stop the run, not be silently dropped on the
    floor and leave the sweep running something other than what the file says.
    """
    data = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw[:1].isspace():
            raise JobError(
                "%s line %d: indented lines are not supported — a job "
                "definition is a flat map of 'key: value' pairs" % (path, lineno))
        if stripped.startswith("-"):
            raise JobError(
                "%s line %d: list items are not supported — a job definition "
                "is a flat map of 'key: value' pairs" % (path, lineno))
        if ":" not in stripped:
            raise JobError(
                "%s line %d: expected 'key: value', got %r" % (path, lineno, raw))
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not key:
            raise JobError("%s line %d: empty key" % (path, lineno))
        if key in data:
            raise JobError("%s line %d: duplicate key %r" % (path, lineno, key))
        data[key] = value
    return data


def load_job(job_type, directory=None):
    """Load and validate the definition for ``job_type``. Return it as a dict.

    ``job_type`` names the file ``<jobs-dir>/<job-type>.yml``, and the file
    name is the job's identity: a ``job_type`` key inside the file that
    disagrees with it is an error, not an override. The returned dict always
    carries a validated ``runner`` and a ``job_type`` matching the file.

    Two path checks, both because this resolves what an unattended sweep
    executes: ``job_type`` must be a bare file name (no directory separator, no
    leading dot), and ``runner`` must be relative to the dispatch directory
    with no ``..`` segment. Either would otherwise let a job definition point
    the nightly run at an arbitrary executable.
    """
    if not isinstance(job_type, str) or not job_type.strip():
        raise JobError("job type must be a non-empty name; got %r" % (job_type,))
    job_type = job_type.strip()
    if job_type != os.path.basename(job_type) or job_type.startswith("."):
        raise JobError(
            "job type %r must be a bare file name, not a path — a job type "
            "that can traverse directories would let the nightly sweep be "
            "pointed at an arbitrary file" % (job_type,))

    directory = directory if directory is not None else jobs_dir()
    path = os.path.join(directory, job_type + ".yml")
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise JobError("no job definition for %r at %s: %s" % (job_type, path, exc))

    job = _parse_job_yaml(text, path)

    declared = job.get("job_type")
    if declared and declared != job_type:
        raise JobError(
            "%s declares job_type %r but was loaded as %r — the file name is "
            "the job's identity" % (path, declared, job_type))

    runner = job.get("runner")
    if not runner:
        raise JobError(
            "%s declares no 'runner' — a job definition must name the script "
            "each due package is handed" % path)
    if os.path.isabs(runner) or ".." in pathlib.PurePosixPath(runner).parts:
        raise JobError(
            "%s: 'runner' must be relative to the dispatch directory with no "
            "'..' segment; got %r — an unattended sweep must not be pointable "
            "at an arbitrary executable" % (path, runner))

    job["job_type"] = job_type
    job["runner"] = runner
    return job
```

Replace `audit_run_bin()` (lines ~353–368) with:

```python
def runner_bin(job=None):
    """Resolve the per-package runner this sweep will invoke.

    The runner comes from the job definition (:func:`load_job` guarantees the
    key is present and safe), resolved against this script's own directory.
    ``AUDIT_RUN_BIN`` overrides it, and the override is read with
    ``os.environ.get`` and NO default so that a variable which is set but EMPTY
    resolves to the empty string and fails loudly. That is the same rule
    ``run.sh`` applies to ``AUDIT_CLAUDE_BIN``, and for the same reason: a
    harness that computes an empty path must not fall through to the real thing
    and start a live, billed agent session. A prior agent did exactly that; the
    indirection exists so no test can repeat it.
    """
    override = os.environ.get(AUDIT_RUN_BIN_ENV)
    if override is not None:
        return override
    runner = (job or {}).get("runner") or DEFAULT_RUNNER
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), runner)
```

Keep a thin alias so the name the guides document still resolves, and so
`run_package`'s no-job default is explicit:

```python
def audit_run_bin():
    """Back-compatible alias for ``runner_bin()`` with no job definition."""
    return runner_bin()
```

In `run_package`, change `runner = binary if binary is not None else audit_run_bin()`
to `runner = binary if binary is not None else runner_bin()`.

In `main()`, add the flag after `--dry-run`:

```python
    parser.add_argument(
        "--job-type",
        default=DEFAULT_JOB_TYPE,
        help="the job definition to run, named by jobs/<job-type>.yml beside "
             "this script (default: %s)" % DEFAULT_JOB_TYPE,
    )
```

and in the body, replace

```python
    runner = args.audit_run_bin if args.audit_run_bin is not None else audit_run_bin()
```

with

```python
    job = load_job(args.job_type)
    runner = args.audit_run_bin if args.audit_run_bin is not None else runner_bin(job)
```

placing the `load_job` call **before** `store.ensure_store(root)`, so an
unknown job type stops the run before anything is created or written.

Add `"job_type": job["job_type"],` to both `json.dumps` payloads (the
`--dry-run` one and the `nothing due` one) and to the final result payload.

Update the module docstring to describe `--job-type` and the `jobs/` directory,
and add the one-line note that the `--dispatch-run-id` format
(`night-<date>-<package>`) should gain the job type when a second job type
lands, since two job types sweeping one package on one night would otherwise
collide.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop/payload/tools/tests
python3 -m unittest test_audit_dispatch -v 2>&1 | tail -15
```

Expected: `OK`, with the run count risen by 19 from Task 1's figure.

- [ ] **Step 6: Run the full suite**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop
bash payload/tools/tests/run_all.sh > /tmp/agent-loop-phase5/after-jobtype.log 2>&1; echo "exit=$?"
tail -20 /tmp/agent-loop-phase5/after-jobtype.log
```

Expected: 0 failed, same suite count as Task 1 Step 12.

- [ ] **Step 7: Commit**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop
git add payload/tools/dispatch/dispatch.py \
        payload/tools/dispatch/jobs/security-audit.yml \
        payload/tools/tests/test_audit_dispatch.py
git commit
```

Subject: `feat(dispatch): --job-type reads the runner from jobs/<type>.yml`.
The body's section (1) must state that the three deferred job types
(`dep-refresh`, `doc-drift`, `metric-summary`) are out of scope per the spec's
own "after the rename is proven on at least one real nightly run" condition.

---

### Task 3: Documentation, registry guides, and observability prose

**Files:**
- Modify: `ARCHITECTURE.md`, `INSTALL.md`,
  `payload/registry/guides/audit-dispatch.md`,
  `payload/registry/guides/audit-run.md`,
  `payload/registry/guides/audit-store.md`,
  `payload/registry/guides/audit-digest.md`,
  `payload/registry/guides/repo-audit-action.md`,
  `payload/observability/alerts/cost-per-day.yaml`,
  `payload/observability/alerts/repo-audit-silent.yaml`,
  `payload/observability/dashboards/run-timelines.json`,
  `payload/observability/dashboards/scheduler-liveness.json`.
- Test: `python3 payload/tools/lint_registry.py payload/registry` and the full
  suite (`test_hook_inject.sh` reads the hook, and several guides are linted).

**Interfaces:**
- Consumes: the paths established in Tasks 1 and 2.
- Produces: nothing other tasks depend on. This is the last task.

- [ ] **Step 1: Update `ARCHITECTURE.md`'s scheduler diagram and prose**

Lines 127, 141, 153, and 160 carry a right-aligned path column. Update both
halves of each:

- `audit_dispatch.py` / `payload/tools/audit_dispatch.py` → `dispatch.py` / `payload/tools/dispatch/dispatch.py`
- `audit_run.sh <pkg> <store> --key KEY` / `payload/tools/audit_run.sh` → `run.sh <pkg> <store> --key KEY` / `payload/tools/dispatch/run.sh`
- `audit_store.py` / `payload/tools/audit_store.py` → `store.py` / `payload/tools/dispatch/store.py`
- `audit_digest.py` / `payload/tools/audit_digest.py` → `digest.py` / `payload/tools/dispatch/digest.py`

Then the bare module references in prose at lines 133, 136, 169, 170, 207, 208,
242, 413, 421, 423, and 432–435: `audit_store` → `store`, `audit_run.sh` →
`run.sh`, `audit_dispatch` → `dispatch`, `audit_digest.py` → `digest.py`. Add
one sentence under the diagram recording that these four now ship as one
directory and that the runner comes from `jobs/security-audit.yml`, selected by
`--job-type`.

- [ ] **Step 2: Update `INSTALL.md`'s scheduler section**

Lines 299, 307, 328, and 330: `payload/tools/audit_dispatch.py` →
`payload/tools/dispatch/dispatch.py`, `audit_dispatch.py` → `dispatch.py`,
`payload/tools/audit_store.py` → `payload/tools/dispatch/store.py`.

- [ ] **Step 3: Update the four registry guides' Interface and "Lives at" lines**

`audit-dispatch.md` lines 36–37:
```
audit_dispatch.py [--workspace DIR] [--root DIR] [--json] [--dry-run]
                  [--audit-run-bin PATH]
```
becomes
```
dispatch.py [--job-type NAME] [--workspace DIR] [--root DIR] [--json]
            [--dry-run] [--audit-run-bin PATH]
```
and line 100's `Lives at \`payload/tools/audit_dispatch.py\`` becomes
`Lives at \`payload/tools/dispatch/dispatch.py\``. Add two sentences to the
guide describing `--job-type` and `jobs/security-audit.yml`, including that
job definitions are a flat `key: value` subset, not full YAML.

`audit-run.md` line 27: `audit_run.sh <package-path> ...` → `run.sh <package-path> ...`;
line 100: `payload/tools/audit_run.sh` → `payload/tools/dispatch/run.sh`;
line 101's test path is unchanged (`payload/tools/tests/test_audit_run.sh`).

`audit-store.md` lines 32–34: `audit_store.py` → `store.py` on all three;
line 80: `payload/tools/audit_store.py` → `payload/tools/dispatch/store.py`.

`audit-digest.md` lines 38–39: `audit_digest.py` → `digest.py` on both;
line 63: `payload/tools/audit_digest.py` → `payload/tools/dispatch/digest.py`.

In all four, sweep the remaining in-prose mentions of the old file names to the
new ones. The kebab-case tool names (`audit-dispatch`, `audit-run`,
`audit-store`, `audit-digest`) stay — those are registry row IDs, not paths.

- [ ] **Step 4: Fix the pre-existing typo in `repo-audit-action.md`**

Line 79 reads `` Shares the read-only-scanner allowlist shape with `audit-run.sh` `` —
neither the real filename (`audit_run.sh`, underscore) nor this file's own
kebab-case tool-name convention. It becomes `` with `audit-run` ``, matching
lines 77–83 around it. This is a pre-existing grammar/naming defect noticed
while working nearby, fixed per the standing "fix mistakes you notice" rule.

- [ ] **Step 5: Update the observability prose**

`payload/observability/alerts/repo-audit-silent.yaml` lines 9 and 23:
`payload/tools/audit_run.sh's _emit_run_record()` →
`payload/tools/dispatch/run.sh's _emit_run_record()`, and `audit_dispatch.py` →
`dispatch.py`.

`payload/observability/alerts/cost-per-day.yaml` line 15: `audit_run.sh` →
`dispatch/run.sh`.

`payload/observability/dashboards/run-timelines.json` lines 3 and 24, and
`scheduler-liveness.json` lines 3 and 8: `audit_run.sh` → `dispatch/run.sh`
inside the `"description"` strings. These are prose, not dereferenced paths, so
the change is accuracy only — but a doc that names a file that no longer exists
is a defect, not a nit.

- [ ] **Step 6: Lint the registry and re-run the full suite**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop
python3 payload/tools/lint_registry.py payload/registry
bash payload/tools/tests/run_all.sh > /tmp/agent-loop-phase5/final.log 2>&1; echo "exit=$?"
tail -20 /tmp/agent-loop-phase5/final.log
```

Expected: `OK (0 error(s))` from the linter, and 0 failed from the suite.

- [ ] **Step 7: Commit**

```bash
cd /Users/ryanhurst/dev/claude-agent-loop
git add ARCHITECTURE.md INSTALL.md \
        payload/registry/guides/audit-dispatch.md payload/registry/guides/audit-run.md \
        payload/registry/guides/audit-store.md payload/registry/guides/audit-digest.md \
        payload/registry/guides/repo-audit-action.md \
        payload/observability/alerts/cost-per-day.yaml \
        payload/observability/alerts/repo-audit-silent.yaml \
        payload/observability/dashboards/run-timelines.json \
        payload/observability/dashboards/scheduler-liveness.json
git commit
```

Subject: `docs(dispatch): repoint architecture, install, and registry guides at tools/dispatch/`.

---

## Rollback

Each of the three commits reverts independently with `git revert <sha>`, in
reverse order. Reverting Task 1 alone restores the four files to
`payload/tools/`, restores the four `link-file` MANIFEST lines, and restores the
plist's original `ProgramArguments` — the nightly job's path and its shipped
file move together in both directions, which is the property the spec's
"same commit" requirement exists to guarantee.
