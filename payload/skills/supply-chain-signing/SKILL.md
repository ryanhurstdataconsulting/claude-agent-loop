---
name: supply-chain-signing
description: Use when generating a software bill of materials (SBOM), hardening a release pipeline's artifact integrity, wiring build provenance and artifact signing, or meeting a supply-chain compliance driver such as an SBOM mandate or a SLSA level target. Triggers include "generate an SBOM," "sign our release artifacts," "add provenance to the build," a compliance requirement referencing supply-chain security, a request for keyless/cosign signing, or a deploy-time gate that must reject unsigned or provenance-mismatched artifacts.
---

# supply-chain-signing

## Overview
Covers the full software supply-chain integrity chain for a release pipeline: generating an SBOM for every build, attaching SLSA build provenance, signing artifacts (preferably keylessly via OIDC-backed short-lived certificates), and gating deployment on verified signatures and matching provenance. This skill is jointly relevant to whoever defines the security policy and whoever operates the release pipeline it runs in — treat it as one shared skill, not two, since the steps are the same regardless of which side of that line is doing the work.

## When to use
- A request to generate a software bill of materials (SBOM) for a build or release.
- Hardening a release pipeline against supply-chain tampering (dependency substitution, build-system compromise, artifact tampering after build).
- A compliance driver requires an SBOM or a specific SLSA maturity level (for example, a regulatory or contractual mandate referencing supply-chain security).
- Setting up or maintaining artifact signing (cosign, Sigstore) on a release pipeline.
- A deploy-time gate needs to reject artifacts that are unsigned or whose provenance does not match the expected build.
- Rotating signing configuration or keeping a verify-on-deploy gate current as the pipeline evolves.

## Workflow

1. **Generate an SBOM on every build, not just at release time.** Use Syft (or an equivalent SBOM generator matched to the artifact type — container image, language package, binary) to produce a CycloneDX or SPDX-format SBOM as a build step. Attach it to the build artifact so it travels with every version produced, including intermediate/dev builds — retrofitting SBOMs only at release time leaves a visibility gap for everything else.

2. **Generate SLSA build provenance.** Provenance is a signed attestation of *how* an artifact was built: which source commit, which build system, which build definition/pipeline configuration produced it. Use the build platform's native provenance generation where available (many CI platforms now emit SLSA provenance attestations natively) or a dedicated generator otherwise. The provenance attestation is what lets a downstream consumer verify "this artifact really came from this pipeline running this source," not just "this artifact is signed by someone."

3. **Sign artifacts keylessly with cosign against short-lived OIDC-backed certificates.** Keyless signing avoids the operational burden and risk of long-lived private key management: the CI identity (via OIDC token from the CI platform) is used to request a short-lived signing certificate from a public certificate authority (Sigstore Fulcio), the artifact is signed, and the signature plus certificate are recorded in a public transparency log (Sigstore Rekor). This means signature validity does not depend on a key that could leak or need rotation — it depends on the CI identity and a timestamped transparency-log entry.

4. **Choose the target level deliberately, don't over-build day one.** SLSA is a graduated framework (roughly: build process is scripted and repeatable → build runs on a dedicated, isolated build service with generated provenance → provenance is non-forgeable and the build is fully hermetic/verified). Target the level that matches the actual threat model and any compliance driver — jumping straight to the highest level on a pipeline that does not need it burns effort better spent elsewhere.

5. **Add a verify-before-deploy gate.** At deployment time, verify:
   - The artifact's signature is valid and was issued to the expected CI identity.
   - The provenance matches the expected source repository, branch/tag, and build definition — not just "signed by someone with access."
   - The SBOM is present and, where a vulnerability gate exists, has been scanned (this is where `sast-dast-sca-pipeline-integration`'s SCA stage and this skill's SBOM output connect).
   
   Reject deployment if any check fails. A signing setup that produces signatures nobody verifies at deploy time provides no actual protection — it is the verify gate that closes the loop.

6. **Maintain the pipeline as it evolves.** Signing configuration (OIDC trust relationships, expected identities, provenance-matching rules) needs to stay current as the pipeline's build definitions, branch structure, or CI platform change. A verify gate checking against a stale expected-identity list will either false-positive-block legitimate releases or silently stop verifying anything meaningful. Review the signing/verify configuration whenever the pipeline topology changes.

7. **Meet the specific compliance driver's actual requirement, not a generic checklist.** If the trigger is a specific mandate (an SBOM requirement, a supply-chain executive order, a cyber-resilience regulation), confirm the SBOM format, delivery mechanism, and update cadence the mandate actually specifies — requirements vary on format (SPDX vs. CycloneDX) and on whether the SBOM must be delivered to a customer/regulator versus simply retained.

## Checklist / quality gate
- Every build (not only tagged releases) emits an SBOM in a standard format (SPDX or CycloneDX).
- Every release artifact has a SLSA provenance attestation naming its source commit and build definition.
- Artifacts are signed via short-lived OIDC-backed certificates (keyless), with signatures recorded in a transparency log — not via a long-lived static private key, unless there is a specific, documented reason keyless signing is unavailable.
- A verify-before-deploy gate exists and actually blocks deployment on a missing signature, an invalid signature, or a provenance mismatch — tested against a known-bad case (an unsigned or mismatched artifact) to confirm it rejects.
- The targeted SLSA level is explicit and matches the actual threat model or compliance driver, not assumed.
- Signing/verify configuration is reviewed after any change to the pipeline's build definitions or branch structure.

## References
- SLSA framework: https://jfrog.com/learn/grc/slsa-framework/
- Sigstore / cosign keyless signing overview: https://nathanberg.io/posts/supply-chain-security-ci-sbom-slsa-sigstore/
- Regulatory drivers commonly cited for SBOM/supply-chain requirements: a U.S. executive order on software supply-chain security, and the EU Cyber Resilience Act — confirm the specific mandate's format and delivery requirements before treating either as a generic checklist.

## Composition
Consumes the SCA scan stage from `sast-dast-sca-pipeline-integration` for vulnerability data against the SBOM. Runs inside a pipeline authored by `ci-pipeline-authoring`, typically as a stage jointly owned by security policy and release-pipeline operation. A signing-key or credential compromise discovered while operating this pipeline hands off to `secrets-scanning-remediation`; a finding severe enough to need formal disclosure hands off to `vulnerability-triage-and-disclosure`.
