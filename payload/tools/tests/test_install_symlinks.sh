#!/bin/bash
# test_install_symlinks.sh — sandboxed end-to-end tests for the MANIFEST-driven
# install.sh v2 and uninstall.sh.
#
# Everything runs against a throwaway $HOME created with mktemp; the real $HOME
# is NEVER touched. Installs run with a stripped PATH (no `claude` CLI, which
# forces the fragment marketplace branch) and </dev/null (so Step 4's prompt
# stays non-interactive). macOS bash-3.2 portable — no mapfile, no `declare -A`,
# no `set -e` (one failing assertion must not abort the rest).
#
# Style mirrors the other bash suites here: `set -u`, a fails counter,
# PASS/FAIL lines, non-zero exit when anything fails.
#
# Run: bash test_install_symlinks.sh

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
INSTALL="$REPO/install.sh"
UNINSTALL="$REPO/uninstall.sh"
MANIFEST="$REPO/payload/MANIFEST"
VERSION_FILE="$REPO/VERSION"

fails=0
pass() { printf 'PASS - %s\n' "$1"; }
fail() { printf 'FAIL - %s\n' "$1"; fails=$((fails + 1)); }

# One sandbox root; every scenario gets its own $HOME beneath it. A single trap
# tears the whole tree down, even on early failure.
SANDBOX_ROOT="$(mktemp -d 2>/dev/null || mktemp -d -t calinstall)"
trap 'rm -rf "$SANDBOX_ROOT"' EXIT INT TERM

new_home() {
  d="$SANDBOX_ROOT/$1"
  rm -rf "$d"
  mkdir -p "$d"
  printf '%s' "$d"
}

run_install()   { env HOME="$1" PATH=/usr/bin:/bin bash "$INSTALL" </dev/null 2>&1; }
run_uninstall() { h="$1"; shift; env HOME="$h" PATH=/usr/bin:/bin bash "$UNINSTALL" "$@" </dev/null 2>&1; }

manifest_links() {
  while IFS= read -r line; do
    set -- $line
    [ "$#" -eq 0 ] && continue
    case "$1" in
      link-dir|link-file) printf '%s\n' "$2" ;;
    esac
  done < "$MANIFEST"
}

manifest_seeds() {
  while IFS= read -r line; do
    set -- $line
    [ "$#" -eq 0 ] && continue
    case "$1" in
      copy-if-absent) printf '%s\t%s\n' "$2" "${3:-$2}" ;;
    esac
  done < "$MANIFEST"
}

plugin_count() { python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("enabledPlugins",{})))' "$1" 2>/dev/null; }
mp_count()     { python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("extraKnownMarketplaces",{})))' "$1" 2>/dev/null; }

if [ ! -f "$INSTALL" ]; then
  echo "FAIL - install.sh not found at $INSTALL (RED: build it first)"
  exit 1
fi

# ===========================================================================
echo "== Scenario 1: fresh install =="
H="$(new_home fresh)"
C="$H/.claude"
run_install "$H" >/dev/null
S="$C/settings.json"

link_count="$(manifest_links | wc -l | tr -d ' ')"
[ "$link_count" -gt 0 ] 2>/dev/null && pass "manifest_links yields >0 entries (assertions below aren't vacuous)" \
  || fail "manifest_links yielded 0 entries — loop below would pass vacuously"

link_fail=0
for rel in $(manifest_links); do
  d="$C/$rel"
  if [ -L "$d" ] && [ -e "$d" ] && [ "$(readlink "$d")" = "$REPO/payload/$rel" ]; then
    :
  else
    fail "link not a repo-resolving symlink: $rel"; link_fail=1
  fi
done
[ "$link_fail" -eq 0 ] && pass "all MANIFEST link entries are repo symlinks"

seed_fail=0
while IFS="$(printf '\t')" read -r src dest; do
  d="$C/$dest"
  if [ -e "$d" ] && [ ! -L "$d" ]; then :; else fail "seed missing or is a symlink: $dest"; seed_fail=1; fi
done < <(manifest_seeds)
[ "$seed_fail" -eq 0 ] && pass "all copy-if-absent seeds present as real files"

[ -d "$C/metrics/state" ] && pass "metrics/state created" || fail "metrics/state missing"
[ -d "$C/learning/digests" ] && pass "learning/digests created" || fail "learning/digests missing"

[ "$(cat "$C/learning/.installed-version" 2>/dev/null)" = "$(cat "$VERSION_FILE")" ] \
  && pass ".installed-version matches VERSION" || fail ".installed-version mismatch"

grep -qF "$C/hooks/inject-resource-loop.sh" "$S" 2>/dev/null \
  && pass "SessionStart hook path under sandbox HOME" || fail "hook path missing/wrong"
[ "$(plugin_count "$S")" = "11" ] && pass "11 plugins enabled" || fail "expected 11 plugins, got $(plugin_count "$S")"
[ "$(mp_count "$S")" = "2" ] && pass "2 marketplaces" || fail "expected 2 marketplaces, got $(mp_count "$S")"

n="$(grep -cF 'BEGIN AGENT-LOOP' "$C/CLAUDE.md" 2>/dev/null)"
[ "$n" = "1" ] && pass "exactly one AGENT-LOOP block" || fail "expected 1 AGENT-LOOP block, got ${n:-none}"

# ===========================================================================
echo "== Scenario 2: idempotent re-run =="
before="$(readlink "$C/hooks/inject-resource-loop.sh" 2>/dev/null)"
run_install "$H" >/dev/null
after="$(readlink "$C/hooks/inject-resource-loop.sh" 2>/dev/null)"
[ -n "$before" ] && [ "$before" = "$after" ] && pass "link unchanged after re-run" || fail "link changed on re-run"
[ "$(grep -cF "$C/hooks/inject-resource-loop.sh" "$S" 2>/dev/null)" = "1" ] \
  && pass "no duplicate hook group" || fail "hook duplicated on re-run"
[ "$(grep -cF 'BEGIN AGENT-LOOP' "$C/CLAUDE.md" 2>/dev/null)" = "1" ] \
  && pass "still one AGENT-LOOP block" || fail "sentinel block duplicated on re-run"
[ "$(plugin_count "$S")" = "11" ] && pass "still 11 plugins" || fail "plugin count drifted on re-run"

# ===========================================================================
echo "== Scenario 3: local override preserved =="
H="$(new_home override)"
C="$H/.claude"
mkdir -p "$C/agents"
printf 'LOCAL OVERRIDE FILE\n' > "$C/agents/sql-safety-reviewer.md"
mkdir -p "$C/skills/token-efficiency"
printf 'LOCAL OVERRIDE DIR\n' > "$C/skills/token-efficiency/LOCAL.md"
OUT="$(run_install "$H")"
printf '%s\n' "$OUT" | grep -qF 'local override shadows framework: agents/sql-safety-reviewer.md' \
  && pass "warns on file override" || fail "no warning for file override"
printf '%s\n' "$OUT" | grep -qF 'local override shadows framework: skills/token-efficiency' \
  && pass "warns on dir override" || fail "no warning for dir override"
{ [ ! -L "$C/agents/sql-safety-reviewer.md" ] && [ "$(cat "$C/agents/sql-safety-reviewer.md")" = "LOCAL OVERRIDE FILE" ]; } \
  && pass "override file untouched (real, content intact)" || fail "override file was clobbered"
{ [ ! -L "$C/skills/token-efficiency" ] && [ -f "$C/skills/token-efficiency/LOCAL.md" ]; } \
  && pass "override dir untouched (real, content intact)" || fail "override dir was clobbered"
[ -L "$C/skills/aws-local-emulation" ] && pass "sibling entry still symlinked" || fail "sibling entry not linked"

printf '%s\n' "$OUT" | grep -qE 'shadowed:[[:space:]]*2\b' \
  && pass "summary reports 2 shadowed entries" || fail "summary did not report 2 shadowed entries"
printf '%s\n' "$OUT" | grep -qF 'SHADOWED FRAMEWORK ENTRIES' \
  && pass "shadowed banner printed" || fail "no shadowed banner printed"
printf '%s\n' "$OUT" | grep -qF 'NOT active' \
  && pass "banner states shadowed entries are not active" || fail "banner missing NOT-active sentence"
banner_section="$(printf '%s\n' "$OUT" | sed -n '/SHADOWED FRAMEWORK ENTRIES/,/^[[:space:]]*$/p')"
printf '%s\n' "$banner_section" | grep -qF 'agents/sql-safety-reviewer.md' \
  && pass "banner lists the file override path" || fail "banner does not list the file override path"
printf '%s\n' "$banner_section" | grep -qF 'skills/token-efficiency' \
  && pass "banner lists the dir override path" || fail "banner does not list the dir override path"
printf '%s\n' "$OUT" | tail -5 | grep -qF 'shadowed' \
  && pass "final message reflects the shadowed count" || fail "final message does not mention shadowed entries"

# ===========================================================================
echo "== Scenario 4: seed divergence survives re-install =="
H="$(new_home seed)"
C="$H/.claude"
run_install "$H" >/dev/null
printf '| my-local-scale | a>b | test | diverged seed row |\n' >> "$C/learning/SCALES.md"
run_install "$H" >/dev/null
grep -qF 'my-local-scale' "$C/learning/SCALES.md" && pass "seed edit survived re-install" || fail "seed edit clobbered"
[ ! -L "$C/learning/SCALES.md" ] && pass "seed still a real file" || fail "seed became a symlink"

# ===========================================================================
echo "== Scenario 5: existing user config preserved =="
H="$(new_home userconf)"
C="$H/.claude"
mkdir -p "$C"
printf '%s\n' '{"model":"opus","enabledPlugins":{"some-foreign-plugin@x":true}}' > "$C/settings.json"
printf '# User Config\nMy custom instructions.\n' > "$C/CLAUDE.md"
run_install "$H" >/dev/null
S="$C/settings.json"
python3 -c 'import json,sys; s=json.load(open(sys.argv[1])); sys.exit(0 if s.get("model")=="opus" and s.get("enabledPlugins",{}).get("some-foreign-plugin@x") is True else 1)' "$S" \
  && pass "user model + foreign plugin preserved" || fail "user settings lost"
[ "$(plugin_count "$S")" = "12" ] && pass "foreign + 11 framework plugins = 12" || fail "expected 12 plugins, got $(plugin_count "$S")"
grep -qF 'My custom instructions.' "$C/CLAUDE.md" && pass "user CLAUDE.md text preserved" || fail "user CLAUDE.md text lost"
grep -qF 'BEGIN AGENT-LOOP' "$C/CLAUDE.md" && pass "AGENT-LOOP block appended to user CLAUDE.md" || fail "AGENT-LOOP block not appended"

# ===========================================================================
echo "== Scenario 6: uninstall removes only ours =="
H="$(new_home uninstall)"
C="$H/.claude"
run_install "$H" >/dev/null
printf 'diverged-marker\n' >> "$C/learning/SCALES.md"
mkdir -p "$C/metrics/state"; printf '{}\n' > "$C/metrics/state/harvest.cursor.json"

# Pre-condition: install merged all four of our hook groups across events.
for cmd in \
  "$C/hooks/inject-resource-loop.sh" \
  "$C/hooks/harvest-metrics.sh" \
  "$C/hooks/precompact-event.sh"; do
  grep -qF "$cmd" "$C/settings.json" 2>/dev/null \
    && pass "installed hook command present: $(basename "$cmd")" \
    || fail "install did not merge hook command: $cmd"
done
# harvest-metrics.sh is wired under BOTH SubagentStop and SessionEnd.
[ "$(grep -cF "$C/hooks/harvest-metrics.sh" "$C/settings.json" 2>/dev/null)" = "2" ] \
  && pass "harvest hook merged under two events (SubagentStop + SessionEnd)" \
  || fail "harvest hook not merged under both events"

# Plant a FOREIGN hook group that uninstall must preserve: a new event plus a
# second command riding alongside ours in an event we own.
FOREIGN="/opt/vendor/foreign-hook.sh"
python3 - "$C/settings.json" "$FOREIGN" <<'PY'
import json, sys
path, foreign = sys.argv[1], sys.argv[2]
s = json.load(open(path))
s.setdefault("hooks", {})
s["hooks"]["Notification"] = [{"hooks": [{"type": "command", "command": foreign}]}]
s["hooks"].setdefault("SubagentStop", []).append(
    {"hooks": [{"type": "command", "command": foreign}]})
json.dump(s, open(path, "w"), indent=2)
PY

run_uninstall "$H" >/dev/null; urc=$?
[ "$urc" -eq 0 ] && pass "uninstall exits 0" || fail "uninstall exit $urc"

# All four of our hook groups are gone; the foreign hook and its event survive.
for cmd in \
  "$C/hooks/inject-resource-loop.sh" \
  "$C/hooks/harvest-metrics.sh" \
  "$C/hooks/precompact-event.sh"; do
  grep -qF "$cmd" "$C/settings.json" 2>/dev/null \
    && fail "our hook left behind after uninstall: $(basename "$cmd")" \
    || pass "our hook removed across all events: $(basename "$cmd")"
done
grep -qF "$FOREIGN" "$C/settings.json" 2>/dev/null \
  && pass "foreign hook preserved by uninstall" || fail "foreign hook wrongly removed"

link_count="$(manifest_links | wc -l | tr -d ' ')"
[ "$link_count" -gt 0 ] 2>/dev/null && pass "manifest_links yields >0 entries (assertions below aren't vacuous)" \
  || fail "manifest_links yielded 0 entries — loop below would pass vacuously"

un_fail=0
for rel in $(manifest_links); do
  [ -L "$C/$rel" ] && { fail "symlink not removed: $rel"; un_fail=1; }
done
[ "$un_fail" -eq 0 ] && pass "all repo symlinks removed by uninstall"
[ "$(grep -cF 'BEGIN AGENT-LOOP' "$C/CLAUDE.md" 2>/dev/null)" = "0" ] \
  && pass "AGENT-LOOP block removed" || fail "sentinel block left behind"
grep -qF "$C/hooks/inject-resource-loop.sh" "$C/settings.json" 2>/dev/null \
  && fail "hook group left behind" || pass "SessionStart hook group removed"
grep -qF 'diverged-marker' "$C/learning/SCALES.md" 2>/dev/null && pass "learning seed edit intact" || fail "learning seed removed"
[ -f "$C/learning/SCALES.md" ] && pass "SCALES.md still present" || fail "SCALES.md removed"
{ [ -d "$C/metrics/state" ] && [ -f "$C/metrics/state/harvest.cursor.json" ]; } && pass "metrics untouched" || fail "metrics removed"
[ -f "$C/learning/.installed-version" ] && pass "version marker left (learning untouched)" || fail "version marker removed from learning/"
run_uninstall "$H" >/dev/null; urc2=$?
[ "$urc2" -eq 0 ] && pass "second uninstall exits cleanly" || fail "second uninstall exit $urc2"

# ===========================================================================
echo "== Scenario 7: --restore-backups restores pre-install files =="
H="$(new_home restore)"
C="$H/.claude"
mkdir -p "$C"
SEED_SETTINGS="$SANDBOX_ROOT/seed_settings.json"
SEED_CLAUDE="$SANDBOX_ROOT/seed_claude.md"
printf '%s\n' '{"model":"sonnet","enabledPlugins":{"foreign@x":true}}' > "$C/settings.json"
cp "$C/settings.json" "$SEED_SETTINGS"
printf '# Pre-existing\nUntouched user content.\n' > "$C/CLAUDE.md"
cp "$C/CLAUDE.md" "$SEED_CLAUDE"
run_install "$H" >/dev/null
run_uninstall "$H" --restore-backups >/dev/null
diff -q "$C/settings.json" "$SEED_SETTINGS" >/dev/null 2>&1 && pass "settings.json restored from backup" || fail "settings.json not restored"
diff -q "$C/CLAUDE.md" "$SEED_CLAUDE" >/dev/null 2>&1 && pass "CLAUDE.md restored from backup" || fail "CLAUDE.md not restored"

# ===========================================================================
echo "== Scenario 8: broken symlink repaired on re-install =="
H="$(new_home brokenlink)"
C="$H/.claude"
run_install "$H" >/dev/null
target_rel="hooks/inject-resource-loop.sh"
rm -f "$C/$target_rel"
ln -s /nonexistent/path "$C/$target_rel"
run_install "$H" >/dev/null
{ [ "$(readlink "$C/$target_rel")" = "$REPO/payload/$target_rel" ] && [ -e "$C/$target_rel" ]; } \
  && pass "broken symlink repaired to repo target" || fail "broken symlink not repaired"

# ===========================================================================
echo "== Scenario 9: malformed MANIFEST line is skipped, not fatal =="
# Exercises the REAL install.sh against a real MANIFEST, copied to a scratch
# repo dir with one line corrupted (a known verb, `link-dir`, missing its
# path argument). Under the old code this expands an unset $2 with `set -u`
# and the whole script dies mid-loop, silently skipping every step after it.
SCRATCH_REPO="$SANDBOX_ROOT/repo-malformed"
rm -rf "$SCRATCH_REPO"
mkdir -p "$SCRATCH_REPO"
cp -R "$REPO/install.sh" "$REPO/VERSION" "$REPO/payload" "$SCRATCH_REPO/"
printf '\nlink-dir\n' >> "$SCRATCH_REPO/payload/MANIFEST"
H="$(new_home malformed)"
C="$H/.claude"
OUT="$(env HOME="$H" PATH=/usr/bin:/bin bash "$SCRATCH_REPO/install.sh" </dev/null 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && pass "install exits 0 despite malformed MANIFEST line" || fail "install aborted (exit $rc) on malformed MANIFEST line"
printf '%s\n' "$OUT" | grep -qF "MANIFEST: 'link-dir' missing path" \
  && pass "warns about the malformed line" || fail "no warning printed for the malformed MANIFEST line"
[ -f "$C/learning/.installed-version" ] \
  && pass "later step ran: .installed-version written" || fail "later step did not run: .installed-version missing"
grep -qF 'BEGIN AGENT-LOOP' "$C/CLAUDE.md" 2>/dev/null \
  && pass "later step ran: CLAUDE.md sentinel present" || fail "later step did not run: CLAUDE.md sentinel missing"

# ===========================================================================
echo "== Scenario 10: --restore-backups with no backup present warns and strips in place =="
H="$(new_home norestorebackup)"
C="$H/.claude"
run_install "$H" >/dev/null
[ -f "$C/settings.json.bak-agentloop" ] && fail "test setup invalid: a backup exists (expected none on a fresh install)"
[ -f "$C/CLAUDE.md.bak-agentloop" ] && fail "test setup invalid: a backup exists (expected none on a fresh install)"
UOUT="$(run_uninstall "$H" --restore-backups)"; urc=$?
[ "$urc" -eq 0 ] && pass "uninstall --restore-backups exits 0 with no backups present" || fail "uninstall exit $urc"
printf '%s\n' "$UOUT" | grep -qF "$C/CLAUDE.md.bak-agentloop" \
  && printf '%s\n' "$UOUT" | grep -qF 'no backup found' \
  && pass "warns: no CLAUDE.md backup found, stripping in place" || fail "missing 'no backup found' warning for CLAUDE.md"
printf '%s\n' "$UOUT" | grep -qF "$C/settings.json.bak-agentloop" \
  && printf '%s\n' "$UOUT" | grep -qF 'no backup found' \
  && pass "warns: no settings.json backup found, stripping in place" || fail "missing 'no backup found' warning for settings.json"
[ "$(grep -cF 'BEGIN AGENT-LOOP' "$C/CLAUDE.md" 2>/dev/null)" = "0" ] \
  && pass "CLAUDE.md still stripped in place despite missing backup" || fail "CLAUDE.md not stripped"

# ===========================================================================
echo "---"
if [ "$fails" -eq 0 ]; then
  echo "test_install_symlinks: ALL OK"
  exit 0
else
  echo "test_install_symlinks: $fails failure(s)"
  exit 1
fi
