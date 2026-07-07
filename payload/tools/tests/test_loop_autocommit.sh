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
# Log line: 5 tab fields; subject field starts 'loop:'; rule-id field is H4.
nf="$(awk -F'\t' 'END{print NF}' "$LOG" 2>/dev/null)"
[ "$nf" = "5" ] && pass "happy: log line has 5 tab fields" || fail "happy: log NF=$nf"
rule="$(awk -F'\t' '{print $5}' "$LOG" 2>/dev/null)"
[ "$rule" = "H4" ] && pass "happy: rule-id logged" || fail "happy: rule-id='$rule'"
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

echo "---"
if [ "$fails" -eq 0 ]; then echo "loop_autocommit tests: OK"; else echo "loop_autocommit tests: FAIL ($fails)"; fi
exit "$fails"
