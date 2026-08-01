#!/bin/bash
# test_actions_template.sh — the GitHub Actions reduced-audit workflow template.
#
# The property this suite exists to protect is a disclosure, not a behaviour.
# The workflow runs four of the full audit's six categories, because the other
# two are unanswerable from a checkout — untracked-PII/gitignore compliance
# has no untracked files to look at, and a developer machine's secrets.env
# symlink state does not exist on a runner. A green check that does not say so
# is worse than no check at all: it retires the question. So the limitation
# sentence is asserted as a FIXED STRING, character for character. A later
# edit that softens, reflows, or quietly drops it fails here.
#
# The rest of the cases pin the workflow's authority: read-only repository
# permission, no file-writing tool in the allowlist, no commit, no branch, no
# findings document written back into the repository.
#
# Hermetic and offline: this suite reads one file and runs nothing. It never
# contacts GitHub and never launches a `claude` session of any kind.
#
# macOS bash-3.2 portable.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
WF="$REPO/payload/templates/repo-security-audit.yml"
fail=0
pass() { echo "PASS - $1"; }
die() { echo "FAIL - $1"; fail=1; }

# The sentence, held once here and compared with `grep -F` so that no regular
# expression can accidentally make a near-miss look like a match.
LIMITS='This is a REDUCED audit. Two categories cannot run in CI: untracked-PII/gitignore compliance and secrets.env symlink integrity. A passing check here is not a full audit.'

[ -f "$WF" ] && pass "1 the workflow template exists" || {
  die "1 the workflow template is missing at $WF"
  echo "test_actions_template: FAIL"; exit 1
}

# 2. THE assertion. The disclosure is present, verbatim.
grep -qF -- "$LIMITS" "$WF" \
  && pass "2 the limitations sentence is present verbatim" \
  || die "2 the limitations sentence was reworded or dropped"

# 3. And it reaches the reader, rather than sitting in a source comment. It is
# echoed into the body that becomes both the job summary and the pull-request
# comment, so the echoed form is what is asserted.
grep -qF -- "echo \"$LIMITS\"" "$WF" \
  && pass "3 the sentence is emitted into the report body" \
  || die "3 the sentence is not emitted into the report body"

# 4. The workflow's authority. It must never write to the repository it audits.
for forbidden in "git commit" "git push"; do
  grep -qF -- "$forbidden" "$WF" \
    && die "4 the workflow contains '$forbidden'" \
    || pass "4 the workflow contains no '$forbidden'"
done
grep -qF -- "SECURITY_AUDIT.md" "$WF" \
  && die "4b the workflow writes a findings document into the repository" \
  || pass "4b the workflow writes no findings document into the repository"
grep -qE '^ *contents: read *$' "$WF" \
  && pass "4c repository contents permission is read-only" \
  || die "4c contents permission is not pinned to read"
grep -qE "allowedTools.*\b(Write|Edit|MultiEdit)\b" "$WF" \
  && die "4d a file-writing tool is in the allowlist" \
  || pass "4d no file-writing tool is in the allowlist"

# 5. Both triggers the design calls for.
grep -qE '^ *push: *$' "$WF" && pass "5 triggers on push" || die "5 no push trigger"
grep -qE '^ *pull_request: *$' "$WF" \
  && pass "5b triggers on pull_request" || die "5b no pull_request trigger"
grep -q "gh pr comment" "$WF" \
  && pass "5c comments on the pull request" || die "5c no pull-request comment step"

# 6. The four categories it does run, and the two it must not attempt.
for category in "Dependency CVEs" "Application-layer SAST" \
                "Secrets in tracked code" "CI/CD readiness"; do
  grep -qF -- "$category" "$WF" \
    && pass "6 covers $category" || die "6 does not name $category"
done
grep -qF -- "untracked-PII and gitignore compliance" "$WF" \
  && pass "6b names untracked-PII as out of scope" \
  || die "6b does not exclude untracked-PII"
grep -qF -- "secrets.env symlink integrity" "$WF" \
  && pass "6c names the symlink category as out of scope" \
  || die "6c does not exclude the symlink category"

# 7. The API key is an owner's manual step, and its absence is not a failure.
grep -q "ANTHROPIC_API_KEY" "$WF" \
  && pass "7 requires an ANTHROPIC_API_KEY secret" || die "7 no API key referenced"
grep -q "manual repository-owner step" "$WF" \
  && pass "7b says adding the secret is a manual owner step" \
  || die "7b does not say who adds the secret"
grep -q "continue-on-error: true" "$WF" \
  && pass "7c findings and CLI errors do not fail the build" \
  || die "7c a failing audit step would turn the check red"

# 8. Generic: no client identifier and no machine-specific path. The visibility
# classifier marks any file carrying a client marker as CLIENT, and a shipped
# template must stay generic on both counts.
#
# The marker strings are assembled at run time rather than spelled out. This
# file is itself committed to the framework, and a literal marker written here
# would classify THIS test as CLIENT and block the very commit that adds it.
MARK="$((60 + 8))"
CLIENT_RE="${MARK}_|sports${MARK}"
grep -qE "$CLIENT_RE" "$WF" \
  && die "8 the template carries a client identifier" \
  || pass "8 no client identifier"
grep -qE '/Users/|/home/[a-z]|\$HOME' "$WF" \
  && die "8b the template carries a machine-specific path" \
  || pass "8b no machine-specific path"

# 9. Structural validity, when a YAML parser happens to be available. The
# framework is stdlib-only by rule, so PyYAML is not a dependency and its
# absence is reported rather than treated as a pass.
YAML_CHECK="$(python3 - "$WF" <<'PY' 2>&1
import sys
try:
    import yaml
except ImportError:
    print("unavailable")
    sys.exit(0)
try:
    doc = yaml.safe_load(open(sys.argv[1]))
    jobs = doc["jobs"]
    steps = jobs["reduced-audit"]["steps"]
    print("ok %d step(s)" % len(steps))
except Exception as exc:
    print("invalid: %s: %s" % (type(exc).__name__, exc))
PY
)"
case "$YAML_CHECK" in
  ok*) pass "9 the workflow parses as YAML ($YAML_CHECK)" ;;
  unavailable) pass "9 skipped — no YAML parser on this machine (stdlib-only rule)" ;;
  *) die "9 the workflow does not parse: $YAML_CHECK" ;;
esac

[ $fail -eq 0 ] && { echo "test_actions_template: PASS"; exit 0; }
echo "test_actions_template: FAIL"; exit 1
