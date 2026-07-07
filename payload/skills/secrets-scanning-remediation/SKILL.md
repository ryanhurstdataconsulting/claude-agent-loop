---
name: secrets-scanning-remediation
description: Use when a secret (API key, password, private key, token) has leaked into a git repository, or when setting up proactive secret scanning as a pre-commit hook and CI gate. Triggers include a committed `.env` file, a hardcoded credential found in a diff or code review, a secret-scanning alert from a platform (GitHub, GitLab), a request to "scan for secrets" or "set up gitleaks/TruffleHog," or a need to verify that a purge from git history actually removed a leaked credential from every ref.
---

# secrets-scanning-remediation

## Overview
Covers both sides of secret hygiene: setting up detection (pre-commit hook plus CI gate) before a leak happens, and running the full remediation playbook after one is found — rotate, purge, and migrate to a secrets manager. It owns making sure a leaked credential is dead everywhere, not just deleted from the latest commit.

## When to use
- A secret-scanning tool or a human reviewer flags a credential committed to a repository (current or historical commit).
- A `.env` file, key file, or config with embedded credentials was accidentally committed.
- Setting up secret scanning proactively on a repo that does not have it yet.
- Migrating a service from hardcoded or environment-file credentials to a secrets manager.
- Verifying that a previous "fix" (deleting the file in a new commit) actually removed the secret from git history — it did not, and this is the single most common mistake in this workflow.

## Workflow

### Detection setup (proactive)
1. **Install a pre-commit hook.** Wire `gitleaks` or `TruffleHog` to run on every commit, scanning the staged diff for credential patterns (API keys, private keys, high-entropy strings, known provider token formats). This catches the leak before it ever reaches a shared branch.
2. **Add a CI gate as the second line of defense.** The pre-commit hook is opt-in per developer machine and can be bypassed (`--no-verify`); a CI job running the same scanner against every push or PR is the enforcement backstop. Scan the full diff, not just the latest commit, on PR builds.
3. **Scan the full history once, at setup time.** A new hook only catches new secrets. Run a one-time full-history scan (`gitleaks detect` against the whole repo, not just the working tree) to surface anything already committed before the hook existed.
4. **Tune for signal, not noise.** Allowlist known-safe patterns (test fixtures with obviously fake keys, documentation examples) explicitly and narrowly — a blanket allowlist defeats the purpose.

### Remediation (after a leak is found)
1. **Treat the credential as compromised the moment it is found in git — regardless of whether the repo is public or private, and regardless of how old the commit is.** Git history is effectively permanent and forkable; assume the secret has been seen.
2. **Rotate the credential first, before anything else.** Generate a new credential at the source (the cloud provider, the API vendor, the database), and confirm the new one works, before touching git history. Purging history does not undo exposure if the old credential is still live — rotation is the step that actually neutralizes the risk.
3. **Update every consumer of the credential** to the new value before revoking the old one, to avoid an outage. Prefer migrating the consumer to pull the credential from a secrets manager (e.g., a cloud provider's secrets service, HashiCorp Vault) rather than re-hardcoding a new value in the same place the old one leaked from — otherwise this repeats.
4. **Revoke the old credential** once all consumers are confirmed migrated.
5. **Purge the secret from git history.** Use a history-rewrite tool (`git filter-repo` is the current recommended tool; `BFG Repo-Cleaner` is a common alternative) to strip the secret from every commit that contains it, not just delete the file going forward.
6. **Verify the purge actually worked — do not assume it did.** Search the rewritten history for the literal secret value (or its pattern) across all branches, tags, and reflog entries. A rewrite that misses a branch, a tag, or a fork leaves the secret recoverable. Also check any CI cache, build artifact, or log that might have captured the value independently of git.
7. **Force-push the rewritten history and coordinate with every collaborator** to re-clone or hard-reset their local copies — a stale local clone will silently reintroduce the purged commits on the next push. This step requires explicit team coordination; do not force-push a shared branch's history without it.
8. **Confirm the pre-commit hook and CI gate (from the detection setup above) are now in place** so the same class of leak cannot recur silently.

Gotcha: deleting the file in a new commit ("removed secret" commit message) is the most common false remediation. The secret is still in every prior commit's tree; anyone with clone access (or a cached fork) still has it. Rotation is the only step that actually closes the exposure; the history purge is cleanup, not the fix.

## Checklist / quality gate
- Pre-commit hook and CI gate are both installed, not just one.
- A full-history scan has been run at least once, not only forward-looking detection.
- For a found leak: the credential was rotated first, and confirmed working at the new value, before any history rewrite.
- Every known consumer of the credential was migrated before the old credential was revoked.
- The purge was verified by re-scanning the rewritten history across all branches, tags, and the reflog — not assumed successful.
- Collaborators were notified to re-sync their local clones after any force-push of rewritten history.
- Where feasible, the consumer was migrated to a secrets manager rather than a new hardcoded value.

## References
- gitleaks: https://github.com/gitleaks/gitleaks
- TruffleHog: https://github.com/trufflesecurity/trufflehog
- git filter-repo: https://github.com/newren/git-filter-repo
- BFG Repo-Cleaner: https://rtyley.github.io/bfg-repo-cleaner/
- OWASP DevSecOps Guideline (secrets-management dimension of the DSOMM): https://owasp.org/www-project-devsecops-maturity-model/

## Composition
The pre-commit hook and CI gate slot into a pipeline built by `ci-pipeline-authoring`; the CI-gate placement decision is shared with a release engineer's pipeline ownership. A leak severe enough to warrant a formal severity write-up (customer data exposure, production database credentials) hands off to `vulnerability-triage-and-disclosure`. Migrating a consumer to a secrets manager is often the trigger for a broader `iam-least-privilege-policy-authoring` pass on that credential's actual permission scope.
