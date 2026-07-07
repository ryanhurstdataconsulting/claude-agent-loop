#!/bin/bash
# test_loop_autocommit.sh — sandboxed tests for the gated auto-commit path (P5).
#
# THE riskiest tool in the system: the only sanctioned path that lets the loop
# commit its own edits. Every scenario runs against throwaway git repos and a
# throwaway $HOME created with mktemp — the real $HOME and the real repo are
# NEVER committed to. Notifications are shimmed (a fake osascript records
# invocations; a fake uname always says Darwin) so no real macOS notification
# ever fires and the notify path is assertable on any platform.
#
# macOS bash-3.2 portable: no mapfile, no `declare -A`, no `set -e` (one failing
# assertion must not abort the rest). Written TDD-first: the tool does not exist
# yet, so every case fails RED until loop_autocommit.sh is built.
#
# Run: bash test_loop_autocommit.sh

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"                  # payload/tools (real)
AUTOCOMMIT="$TOOLS/loop_autocommit.sh"

fails=0
pass() { printf 'PASS - %s\n' "$1"; }
fail() { printf 'FAIL - %s\n' "$1"; fails=$((fails + 1)); }

SANDBOX="$(mktemp -d 2>/dev/null || mktemp -d -t calautoc)"
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

# --- notification shim (fake osascript + fake uname) -------------------------
SHIMBIN="$SANDBOX/bin"
NOTIFY_LOG="$SANDBOX/notify.log"
mkdir -p "$SHIMBIN"
: > "$NOTIFY_LOG"
cat > "$SHIMBIN/osascript" <<EOF
#!/bin/bash
printf '%s\n' "\$*" >> "$NOTIFY_LOG"
exit 0
EOF
cat > "$SHIMBIN/uname" <<'EOF'
#!/bin/bash
echo Darwin
EOF
chmod +x "$SHIMBIN/osascript" "$SHIMBIN/uname"

BODY="$SANDBOX/body.txt"
cat > "$BODY" <<'EOF'
(1) Task & Change
Synthetic body for the autocommit test.

(2) Tests created / modified
None — this is a fixture.

(3) Test results — evidence
n/a
EOF

# A fresh framework git repo with a payload/tools scaffold and one commit.
new_fw_repo() {
  fw="$SANDBOX/fw-$1"; rm -rf "$fw"; mkdir -p "$fw/payload/tools" "$fw/docs"
  git -C "$fw" init -q
  git -C "$fw" config user.email test@example.com
  git -C "$fw" config user.name "Test Bot"
  printf 'seed\n' > "$fw/README.md"
  git -C "$fw" add README.md >/dev/null 2>&1
  git -C "$fw" commit -qm init >/dev/null 2>&1
  printf '%s' "$fw"
}

# A fresh $HOME whose .claude is a git repo, with synthetic markers + themes.
new_home() {
  h="$SANDBOX/home-$1"; rm -rf "$h"; mkdir -p "$h/.claude/learning" "$h/.claude/notes"
  git -C "$h/.claude" init -q
  git -C "$h/.claude" config user.email test@example.com
  git -C "$h/.claude" config user.name "Test Bot"
  printf 'widgetco\nwidget-internal\n' > "$h/.claude/learning/CLIENT_MARKERS.txt"
  printf '| status | date | project | theme-tag | note | metrics-ref |\n|---|---|---|---|---|---|\n' \
    > "$h/.claude/learning/LOOP_THEMES.md"
  git -C "$h/.claude" add learning >/dev/null 2>&1
  git -C "$h/.claude" commit -qm init >/dev/null 2>&1
  printf '%s' "$h"
}

# Run the tool with notifications shimmed and the two repos overridden.
run_ac() {
  h="$1"; fw="$2"; shift 2
  env HOME="$h" LOOP_FRAMEWORK_REPO="$fw" NOTIFY_LOG="$NOTIFY_LOG" \
      PATH="$SHIMBIN:$PATH" bash "$AUTOCOMMIT" "$@" 2>&1
}

if [ ! -f "$AUTOCOMMIT" ]; then
  echo "FAIL - loop_autocommit.sh not found at $AUTOCOMMIT (RED: build it first)"
  exit 1
fi

# --- Case 1: happy-path framework commit ------------------------------------
FW="$(new_fw_repo happy)"; H="$(new_home happy)"
printf 'A generic note. 12 rows checked.\n' > "$FW/docs/note.md"
out="$(run_ac "$H" "$FW" -m "docs: add a note" -b "$BODY" -r H4 "$FW/docs/note.md")"; rc=$?
if [ "$rc" -eq 0 ]; then pass "happy: exit 0"; else fail "happy: exit $rc — $out"; fi
subj="$(git -C "$FW" log -1 --format=%s 2>/dev/null)"
case "$subj" in
  "loop: docs: add a note") pass "happy: subject has loop: prefix" ;;
  *) fail "happy: unexpected subject '$subj'" ;;
esac
LOG="$H/.claude/learning/AUTO_COMMITS.log"
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG" | tr -d ' ')" = "1" ]; then
  pass "happy: one AUTO_COMMITS.log line"
else
  fail "happy: expected 1 log line, got $([ -f "$LOG" ] && wc -l < "$LOG" || echo missing)"
fi
# Log line: 6 tab fields (ts,repo,sha,subject,rule,group); subject starts
# 'loop:'; rule-id is H4; field 6 is the 8-char group id (BI2).
nf="$(awk -F'\t' 'END{print NF}' "$LOG" 2>/dev/null)"
[ "$nf" = "6" ] && pass "happy: log line has 6 tab fields" || fail "happy: log NF=$nf"
rule="$(awk -F'\t' '{print $5}' "$LOG" 2>/dev/null)"
[ "$rule" = "H4" ] && pass "happy: rule-id logged" || fail "happy: rule-id='$rule'"
grp="$(awk -F'\t' '{print $6}' "$LOG" 2>/dev/null)"
sha_pref="$(git -C "$FW" rev-parse HEAD | cut -c1-8)"
[ "$grp" = "$sha_pref" ] && pass "happy: group id = sha prefix (group of one)" || fail "happy: group='$grp' sha_pref='$sha_pref'"
# The tool NEVER pushes: no origin was ever configured, and there is nothing to
# assert beyond the absence of a remote (git would have errored on push).
grep -q 'origin' "$FW/.git/config" && fail "happy: an origin was configured" || pass "happy: no push (no origin)"

# --- Case 2: explicit staging only (a dirty unrelated file stays unstaged) ---
FW="$(new_fw_repo staging)"; H="$(new_home staging)"
printf 'target generic content\n' > "$FW/docs/target.md"
printf 'unrelated dirty content\n' > "$FW/README.md"   # modifies the seeded file
run_ac "$H" "$FW" -m "docs: target only" -b "$BODY" "$FW/docs/target.md" >/dev/null 2>&1
# README.md must still be modified-but-unstaged after the commit.
if git -C "$FW" status --porcelain README.md | grep -q '^ M'; then
  pass "staging: unrelated file stayed unstaged"
else
  fail "staging: unrelated file state = '$(git -C "$FW" status --porcelain README.md)'"
fi
# Only docs/target.md landed in the commit.
files="$(git -C "$FW" show --name-only --format= HEAD | tr '\n' ' ')"
case "$files" in
  *README.md*) fail "staging: README.md leaked into the commit" ;;
  *docs/target.md*) pass "staging: only the explicit path committed" ;;
  *) fail "staging: unexpected committed files '$files'" ;;
esac

# --- Case 3: CLIENT-marked content bound for framework → exit 3, tree kept ----
FW="$(new_fw_repo client)"; H="$(new_home client)"
: > "$NOTIFY_LOG"
printf 'This doc mentions widgetco internals.\n' > "$FW/docs/leak.md"
out="$(run_ac "$H" "$FW" -m "docs: add leak" -b "$BODY" "$FW/docs/leak.md")"; rc=$?
[ "$rc" -eq 3 ] && pass "client: exit 3" || fail "client: exit $rc (expected 3) — $out"
if git -C "$FW" diff --cached --quiet; then pass "client: index clean after abort"; else fail "client: index dirty"; fi
grep -q 'widgetco' "$FW/docs/leak.md" && pass "client: working tree preserved" || fail "client: working tree lost the edit"
if grep -q 'autocommit-blocked' "$H/.claude/learning/LOOP_THEMES.md"; then
  row="$(grep 'autocommit-blocked' "$H/.claude/learning/LOOP_THEMES.md" | head -1)"
  case "$row" in
    "| NEW |"*) pass "client: blocked theme row appended (NEW)" ;;
    *) fail "client: blocked row not NEW-prefixed: '$row'" ;;
  esac
else
  fail "client: no autocommit-blocked theme row"
fi
if grep -qi 'gate blocked' "$NOTIFY_LOG"; then
  pass "client: gate-blocked notification fired"
else
  fail "client: no gate-blocked notification recorded"
fi

# --- Case 4: gated lane → exit 4 (settings.json, hooks/*.sh, CLAUDE sentinel) -
FW="$(new_fw_repo gated)"; H="$(new_home gated)"
printf '{}\n' > "$H/.claude/settings.json"
out="$(run_ac "$H" "$FW" -m "chore: touch settings" -b "$BODY" "$H/.claude/settings.json")"; rc=$?
[ "$rc" -eq 4 ] && pass "gated: settings.json → exit 4" || fail "gated: settings exit $rc — $out"
mkdir -p "$FW/payload/hooks"
printf '#!/bin/bash\necho hi\n' > "$FW/payload/hooks/foo.sh"
out="$(run_ac "$H" "$FW" -m "chore: touch hook" -b "$BODY" "$FW/payload/hooks/foo.sh")"; rc=$?
[ "$rc" -eq 4 ] && pass "gated: hooks/*.sh → exit 4" || fail "gated: hook exit $rc — $out"
printf '# Project\n<!-- BEGIN AGENT-LOOP -->\nblock\n<!-- END AGENT-LOOP -->\n' > "$H/.claude/CLAUDE.md"
out="$(run_ac "$H" "$FW" -m "docs: edit CLAUDE" -b "$BODY" "$H/.claude/CLAUDE.md")"; rc=$?
[ "$rc" -eq 4 ] && pass "gated: CLAUDE.md sentinel → exit 4" || fail "gated: sentinel exit $rc — $out"

# --- Case 5: mixed set → two commits (framework first, then local) -----------
FW="$(new_fw_repo mixed)"; H="$(new_home mixed)"
printf 'framework generic body\n' > "$FW/docs/fw.md"
printf 'local generic body\n' > "$H/.claude/notes/local.md"
out="$(run_ac "$H" "$FW" -m "chore: mixed change" -b "$BODY" \
        "$FW/docs/fw.md" "$H/.claude/notes/local.md")"; rc=$?
[ "$rc" -eq 0 ] && pass "mixed: exit 0" || fail "mixed: exit $rc — $out"
fsubj="$(git -C "$FW" log -1 --format=%s)"
lsubj="$(git -C "$H/.claude" log -1 --format=%s)"
case "$fsubj" in "loop: chore: mixed change [framework]") pass "mixed: framework commit suffixed" ;; *) fail "mixed: fw subject '$fsubj'" ;; esac
case "$lsubj" in "loop: chore: mixed change [local]") pass "mixed: local commit suffixed" ;; *) fail "mixed: local subject '$lsubj'" ;; esac
LOG="$H/.claude/learning/AUTO_COMMITS.log"
n="$(wc -l < "$LOG" | tr -d ' ')"
[ "$n" = "2" ] && pass "mixed: two AUTO_COMMITS.log lines" || fail "mixed: $n log lines (expected 2)"
# BI2: both ledger lines share ONE group id = the framework sha's first 8 chars.
g1="$(awk -F'\t' 'NR==1{print $6}' "$LOG")"
g2="$(awk -F'\t' 'NR==2{print $6}' "$LOG")"
fw_pref="$(git -C "$FW" rev-parse HEAD | cut -c1-8)"
if [ "$g1" = "$g2" ] && [ "$g1" = "$fw_pref" ]; then
  pass "mixed: both lines share the framework-sha group id"
else
  fail "mixed: group mismatch g1='$g1' g2='$g2' fw='$fw_pref'"
fi

# --- Case 6: scrub-gate finding → abort (generic per classify, dirty secret) --
FW="$(new_fw_repo scrub)"; H="$(new_home scrub)"
# A JWT-shaped token: no client marker, no structural signal → classify GENERIC,
# but the scrub gate must catch it and abort. Synthetic, not a real token.
printf 'token = eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.sig\n' > "$FW/docs/secret.md"
out="$(run_ac "$H" "$FW" -m "docs: add token" -b "$BODY" "$FW/docs/secret.md")"; rc=$?
[ "$rc" -ne 0 ] && pass "scrub: aborted (exit $rc)" || fail "scrub: expected non-zero exit"
if git -C "$FW" diff --cached --quiet; then pass "scrub: index clean after abort"; else fail "scrub: index dirty"; fi
grep -q 'autocommit-blocked' "$H/.claude/learning/LOOP_THEMES.md" && pass "scrub: blocked theme row" || fail "scrub: no blocked row"

# --- Case 7: new-resource detection fires the notify stub --------------------
FW="$(new_fw_repo newres)"; H="$(new_home newres)"
: > "$NOTIFY_LOG"
printf '#!/usr/bin/env python3\nprint("generic tool, 12 rows")\n' > "$FW/payload/tools/newtool.py"
out="$(run_ac "$H" "$FW" -m "feat(tool): newtool" -b "$BODY" "$FW/payload/tools/newtool.py")"; rc=$?
[ "$rc" -eq 0 ] && pass "newres: exit 0" || fail "newres: exit $rc — $out"
if grep -qi 'new resource' "$NOTIFY_LOG"; then
  pass "newres: new-resource notification fired"
else
  fail "newres: no new-resource notification recorded ($(cat "$NOTIFY_LOG"))"
fi

# --- Case 8 (AC1): CLIENT marker in the commit BODY → framework blocked -------
# The message channel (subject + -b body) is committed content too. A GENERIC
# file whose commit BODY names a client must be REFUSED before anything lands.
FW="$(new_fw_repo msgbody)"; H="$(new_home msgbody)"
: > "$NOTIFY_LOG"
printf 'A perfectly generic note. 12 rows.\n' > "$FW/docs/clean.md"   # file is GENERIC
LEAKBODY="$SANDBOX/leakbody.txt"
cat > "$LEAKBODY" <<'EOF'
(1) Task & Change
Quoted a metric record for widgetco to justify the change.

(2) Tests created / modified
None — fixture.

(3) Test results — evidence
n/a
EOF
out="$(run_ac "$H" "$FW" -m "docs: add a clean note" -b "$LEAKBODY" "$FW/docs/clean.md")"; rc=$?
[ "$rc" -eq 3 ] && pass "msgbody: framework commit blocked on body marker (exit 3)" || fail "msgbody: exit $rc (expected 3) — $out"
# Nothing committed: HEAD is still the seed 'init'.
hsubj="$(git -C "$FW" log -1 --format=%s)"
[ "$hsubj" = "init" ] && pass "msgbody: nothing committed (HEAD still init)" || fail "msgbody: a commit landed ('$hsubj')"
grep -q 'autocommit-blocked' "$H/.claude/learning/LOOP_THEMES.md" && pass "msgbody: blocked theme row" || fail "msgbody: no blocked row"
grep -qi 'gate blocked' "$NOTIFY_LOG" && pass "msgbody: gate-blocked notification fired" || fail "msgbody: no notification"

# --- Case 9 (BC1): pathspec commit does NOT sweep a pre-staged file ----------
# A file staged before autocommit runs (human or concurrent loop) must NOT ride
# into the loop commit, and must remain staged/untouched afterward.
FW="$(new_fw_repo pathspec)"; H="$(new_home pathspec)"
printf 'loop target generic\n' > "$FW/docs/target.md"
printf 'PRESTAGED_MARKER_ABC pre-staged unrelated content\n' > "$FW/docs/prestaged.md"
git -C "$FW" add -- docs/prestaged.md >/dev/null 2>&1        # stage it up front
out="$(run_ac "$H" "$FW" -m "docs: commit target only" -b "$BODY" "$FW/docs/target.md")"; rc=$?
[ "$rc" -eq 0 ] && pass "pathspec: exit 0" || fail "pathspec: exit $rc — $out"
files="$(git -C "$FW" show --name-only --format= HEAD | tr '\n' ' ')"
case "$files" in
  *prestaged.md*) fail "pathspec: pre-staged file was swept into the loop commit" ;;
  *docs/target.md*) pass "pathspec: only the explicit path committed" ;;
  *) fail "pathspec: unexpected committed files '$files'" ;;
esac
# prestaged.md must remain STAGED (index status 'A') and untouched on disk.
if git -C "$FW" status --porcelain docs/prestaged.md | grep -q '^A'; then
  pass "pathspec: pre-staged file remained staged/untouched"
else
  fail "pathspec: pre-staged status = '$(git -C "$FW" status --porcelain docs/prestaged.md)'"
fi
grep -q 'PRESTAGED_MARKER_ABC' "$FW/docs/prestaged.md" && pass "pathspec: pre-staged content intact on disk" || fail "pathspec: pre-staged content changed"

# --- Case 10 (AC2): framework SOURCES of gated artifacts → exit 4 ------------
FW="$(new_fw_repo sources)"; H="$(new_home sources)"
mkdir -p "$FW/payload/fragments" "$FW/payload/hooks"
printf '{"hooks":{}}\n' > "$FW/payload/fragments/settings.fragment.json"
out="$(run_ac "$H" "$FW" -m "chore: edit settings fragment" -b "$BODY" "$FW/payload/fragments/settings.fragment.json")"; rc=$?
[ "$rc" -eq 4 ] && pass "sources: fragments/settings.fragment.json → exit 4" || fail "sources: fragment exit $rc — $out"
printf '# Starter\n<!-- BEGIN AGENT-LOOP -->\nx\n<!-- END AGENT-LOOP -->\n' > "$FW/payload/fragments/CLAUDE.starter.md"
out="$(run_ac "$H" "$FW" -m "docs: edit starter" -b "$BODY" "$FW/payload/fragments/CLAUDE.starter.md")"; rc=$?
[ "$rc" -eq 4 ] && pass "sources: fragments/CLAUDE.starter.md → exit 4" || fail "sources: starter exit $rc — $out"
printf '#!/usr/bin/env python3\nprint("hook")\n' > "$FW/payload/hooks/foo.py"
out="$(run_ac "$H" "$FW" -m "chore: python hook" -b "$BODY" "$FW/payload/hooks/foo.py")"; rc=$?
[ "$rc" -eq 4 ] && pass "sources: hooks/foo.py → exit 4" || fail "sources: hook.py exit $rc — $out"
# A normal skill SKILL.md still commits (no false positive).
mkdir -p "$FW/payload/skills/demo"
printf '# Demo skill\n\nA generic skill. 12 rows.\n' > "$FW/payload/skills/demo/SKILL.md"
out="$(run_ac "$H" "$FW" -m "feat(skill): demo" -b "$BODY" "$FW/payload/skills/demo/SKILL.md")"; rc=$?
[ "$rc" -eq 0 ] && pass "sources: normal SKILL.md still commits (exit 0)" || fail "sources: SKILL.md exit $rc — $out"

# --- Case 11 (AI4): a NUL-byte (binary) framework path → blocked -------------
FW="$(new_fw_repo binary)"; H="$(new_home binary)"
printf 'head\0tail generic\n' > "$FW/docs/blob.md"      # contains a NUL byte
out="$(run_ac "$H" "$FW" -m "docs: add blob" -b "$BODY" "$FW/docs/blob.md")"; rc=$?
[ "$rc" -ne 0 ] && pass "binary: NUL-byte framework path refused (exit $rc)" || fail "binary: expected non-zero exit"
if git -C "$FW" diff --cached --quiet; then pass "binary: index clean after abort"; else fail "binary: index dirty"; fi
hsubj="$(git -C "$FW" log -1 --format=%s)"
[ "$hsubj" = "init" ] && pass "binary: nothing committed" || fail "binary: a commit landed ('$hsubj')"

# --- Case 12 (BI1): honest exit codes on a failing commit -------------------
# (a) single-lane commit failure → non-zero, nothing committed, staged cleaned.
FW="$(new_fw_repo failsingle)"; H="$(new_home failsingle)"
mkdir -p "$FW/.git/hooks"
printf '#!/bin/sh\nexit 1\n' > "$FW/.git/hooks/pre-commit"; chmod +x "$FW/.git/hooks/pre-commit"
printf 'generic single\n' > "$FW/docs/single.md"
out="$(run_ac "$H" "$FW" -m "docs: single" -b "$BODY" "$FW/docs/single.md")"; rc=$?
[ "$rc" -ne 0 ] && pass "bi1-single: non-zero exit on commit failure ($rc)" || fail "bi1-single: false success (exit 0)"
hsubj="$(git -C "$FW" log -1 --format=%s)"
[ "$hsubj" = "init" ] && pass "bi1-single: nothing committed" || fail "bi1-single: a commit landed ('$hsubj')"
if git -C "$FW" diff --cached --quiet; then pass "bi1-single: staged paths cleaned"; else fail "bi1-single: index left dirty"; fi
# (b) mixed commit, LOCAL lane fails after framework committed → PARTIAL + exit 6.
FW="$(new_fw_repo failmixed)"; H="$(new_home failmixed)"
: > "$NOTIFY_LOG"
mkdir -p "$H/.claude/.git/hooks"
printf '#!/bin/sh\nexit 1\n' > "$H/.claude/.git/hooks/pre-commit"; chmod +x "$H/.claude/.git/hooks/pre-commit"
printf 'framework generic\n' > "$FW/docs/fw.md"
printf 'local generic\n' > "$H/.claude/notes/local.md"
out="$(run_ac "$H" "$FW" -m "chore: mixed partial" -b "$BODY" "$FW/docs/fw.md" "$H/.claude/notes/local.md")"; rc=$?
[ "$rc" -ne 0 ] && pass "bi1-partial: non-zero exit ($rc)" || fail "bi1-partial: false success (exit 0)"
fsubj="$(git -C "$FW" log -1 --format=%s)"
case "$fsubj" in "loop: chore: mixed partial"*) pass "bi1-partial: framework half committed" ;; *) fail "bi1-partial: framework not committed ('$fsubj')" ;; esac
FW_SHA="$(git -C "$FW" rev-parse HEAD)"
LOG="$H/.claude/learning/AUTO_COMMITS.log"
if grep -q 'PARTIAL' "$LOG" && grep -q "$FW_SHA" "$LOG"; then
  pass "bi1-partial: PARTIAL line logged with the orphaned framework sha"
else
  fail "bi1-partial: no PARTIAL line naming $FW_SHA"
fi
case "$out" in *loop_rollback.sh*) pass "bi1-partial: rollback hint printed" ;; *) fail "bi1-partial: no rollback hint in output" ;; esac
grep -qi 'PARTIAL' "$NOTIFY_LOG" && pass "bi1-partial: PARTIAL notification fired" || fail "bi1-partial: no PARTIAL notification"

# --- Case 13 (AM1): a pre-staged secret in the index → staged re-scan aborts -
# Belt-and-suspenders: even though the loop commits only its own path, a secret
# already staged in the index must not slip through the staged re-scan.
FW="$(new_fw_repo toctou)"; H="$(new_home toctou)"
: > "$NOTIFY_LOG"
printf 'token = eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.sig\n' > "$FW/docs/leak.md"
git -C "$FW" add -- docs/leak.md >/dev/null 2>&1        # a secret staged out-of-band
printf 'clean generic target\n' > "$FW/docs/ok.md"
out="$(run_ac "$H" "$FW" -m "docs: add ok" -b "$BODY" "$FW/docs/ok.md")"; rc=$?
[ "$rc" -ne 0 ] && pass "am1: staged secret aborts the commit ($rc)" || fail "am1: expected non-zero exit"
hsubj="$(git -C "$FW" log -1 --format=%s)"
[ "$hsubj" = "init" ] && pass "am1: nothing committed" || fail "am1: a commit landed ('$hsubj')"
grep -q 'autocommit-blocked' "$H/.claude/learning/LOOP_THEMES.md" && pass "am1: blocked theme row" || fail "am1: no blocked row"

# --- Case 14 (BI3): a newline in -m must not split the ledger record ---------
# A raw newline in the subject would break the tab-delimited AUTO_COMMITS.log
# record (and the digest that parses it). The subject is collapsed to one line.
FW="$(new_fw_repo bi3)"; H="$(new_home bi3)"
printf 'generic bi3 content\n' > "$FW/docs/bi3.md"
run_ac "$H" "$FW" -m "docs: line one
line two of the subject" -b "$BODY" "$FW/docs/bi3.md" >/dev/null 2>&1
LOG="$H/.claude/learning/AUTO_COMMITS.log"
n="$(wc -l < "$LOG" | tr -d ' ')"
[ "$n" = "1" ] && pass "bi3: exactly one ledger line (no newline split)" || fail "bi3: $n ledger lines (expected 1)"
nf="$(awk -F'\t' 'END{print NF}' "$LOG")"
[ "$nf" = "6" ] && pass "bi3: single parseable 6-field record" || fail "bi3: NF=$nf"
subjfield="$(awk -F'\t' '{print $4}' "$LOG")"
case "$subjfield" in
  *"line one"*"line two"*) pass "bi3: subject collapsed to one line" ;;
  *) fail "bi3: subject field = '$subjfield'" ;;
esac

# --- Case 15 (AM2): a path with shell metacharacters must not inject ---------
# Path args flow through argv arrays, never `eval` on a constructed string, so a
# filename containing $(...) is treated as a literal path, never executed.
FW="$(new_fw_repo am2)"; H="$(new_home am2)"
weird="docs/od(\$(echo pwned)).md"        # literal $(...) in the filename
printf 'generic am2 content\n' > "$FW/$weird"
out="$(run_ac "$H" "$FW" -m "docs: weird path" -b "$BODY" "$FW/$weird")"; rc=$?
[ "$rc" -eq 0 ] && pass "am2: metachar-path commit succeeded (no injection/break)" || fail "am2: exit $rc — $out"
# The committed filename keeps the literal $(...) verbatim. Had the eval hole
# expanded it, the committed name would be `od(pwned).md` (no `$(echo )`
# wrapper) and this match would fail — so the verbatim check IS the no-injection
# proof.
files="$(git -C "$FW" show --name-only --format= HEAD | tr '\n' ' ')"
case "$files" in
  *'$(echo pwned)'*) pass "am2: literal metachar path committed verbatim (no injection)" ;;
  *) fail "am2: committed files '$files'" ;;
esac

# --- Case 16 (R1): body committed from the scanned snapshot, not a re-read -----
# The message channel is scanned once, up front. If the bodyfile is mutated
# AFTER that scan but BEFORE a commit, the committed message must still be the
# CLEAN scanned snapshot — commit_lane commits from the snapshot, never a fresh
# bodyfile re-read. Reproduced deterministically with a mixed commit: the
# framework repo's pre-commit hook injects a marker into the bodyfile while the
# framework lane is committing; the LOCAL lane (committed next) must NOT carry
# the marker. A re-read would leak it into the local commit body.
FW="$(new_fw_repo r1snap)"; H="$(new_home r1snap)"
R1BODY="$SANDBOX/r1body.txt"
cat > "$R1BODY" <<'EOF'
(1) Task & Change
A clean generic body for the R1 snapshot test. 12 rows checked.

(2) Tests created / modified
None — fixture.

(3) Test results — evidence
n/a
EOF
mkdir -p "$FW/.git/hooks"
cat > "$FW/.git/hooks/pre-commit" <<EOF
#!/bin/sh
printf 'INJECTED_MARKER_R1 post-scan mutation of the body\n' >> "$R1BODY"
exit 0
EOF
chmod +x "$FW/.git/hooks/pre-commit"
printf 'framework generic r1 body\n' > "$FW/docs/fw.md"
printf 'local generic r1 body\n' > "$H/.claude/notes/local.md"
out="$(run_ac "$H" "$FW" -m "chore: r1 snapshot" -b "$R1BODY" \
        "$FW/docs/fw.md" "$H/.claude/notes/local.md")"; rc=$?
[ "$rc" -eq 0 ] && pass "r1: mixed commit exit 0" || fail "r1: exit $rc — $out"
lbody="$(git -C "$H/.claude" log -1 --format=%B 2>/dev/null)"
case "$lbody" in
  *INJECTED_MARKER_R1*) fail "r1: local body carried the post-scan injection (re-read, not snapshot)" ;;
  *) pass "r1: local commit body is the clean scanned snapshot" ;;
esac
fbody="$(git -C "$FW" log -1 --format=%B 2>/dev/null)"
case "$fbody" in
  *INJECTED_MARKER_R1*) fail "r1: framework body carried the injection" ;;
  *) pass "r1: framework commit body clean" ;;
esac

echo "---"
if [ "$fails" -eq 0 ]; then echo "loop_autocommit tests: OK"; else echo "loop_autocommit tests: FAIL ($fails)"; fi
exit "$fails"
