---
name: threat-model-on-diff
description: Use when a pull request, design document, or code diff touches authentication, authorization, data handling, a trust boundary, or an external integration and needs a security-specialized pass beyond general code review. Triggers include a request to "threat-model this change," a new endpoint that accepts external input, a change to session/token handling, a new third-party integration, or a diff that crosses a service, tenant, or privilege boundary. Produces a STRIDE-based threats-and-mitigations table scoped to the diff, not a whole-system audit.
---

# threat-model-on-diff

## Overview
Runs a STRIDE-based threat-modeling pass scoped to a single diff, pull request, or design document rather than an entire system. It owns one job: turn "does this change introduce a security risk" into a concrete, reviewable threats-and-mitigations table with a recommendation for the earliest point in the pipeline each threat should be caught.

## When to use
- A PR or design doc touches authentication, session/token handling, authorization checks, or role/permission logic.
- A change adds or modifies a trust boundary: a new external integration, a new API endpoint accepting untrusted input, a new inter-service call, a new file upload or deserialization path.
- A change handles sensitive data (PII, credentials, payment data, health data) — new storage, new logging, a new export path.
- Someone explicitly asks to "threat-model this," "review this for security," or "what could go wrong with this change."
- A design review is happening before implementation and the design touches any of the above.

Do not use for a whole-codebase or whole-system audit — that is a broader security review scope; this skill is deliberately bounded to a diff or design.

## Workflow

1. **Scope the diff.** Identify exactly what changed: new/modified endpoints, new data flows, new dependencies, new configuration. Read the diff plus enough surrounding context (the file the diff lives in, its immediate callers) to understand the trust boundaries it touches. Do not attempt to threat-model the whole file or system.

2. **Enumerate trust boundaries crossed.** For each boundary the diff introduces or modifies, note:
   - What crosses it (a request, a message, a file, a query)
   - Who or what is on each side (anonymous user vs. authenticated user, service A vs. service B, tenant X vs. tenant Y)
   - What the code currently assumes about data crossing that boundary

3. **Apply STRIDE per boundary.** For each trust boundary, walk the six categories and note whether each applies, and if so, how:
   - **S — Spoofing**: can an actor impersonate another identity? (missing/weak auth check, predictable tokens, trusting a client-supplied identity field)
   - **T — Tampering**: can data be modified in transit or at rest without detection? (unsigned payloads, missing integrity checks, client-side-only validation)
   - **R — Repudiation**: can an actor deny having performed an action? (no audit log, no non-repudiable record of a state change)
   - **I — Information Disclosure**: does data leak to an unauthorized party? (verbose errors, missing field-level authorization, logging sensitive fields, over-broad API responses)
   - **D — Denial of Service**: can an actor exhaust a resource? (unbounded loops, missing rate limits, unbounded payload sizes, expensive operations reachable pre-auth)
   - **E — Elevation of Privilege**: can an actor gain permissions they should not have? (missing authorization check present in a sibling endpoint, insecure direct object reference, privilege check that trusts client input)

4. **Rate and prioritize.** For each identified threat, note a rough severity (informed by likelihood × impact, not a full CVSS pass — that belongs to `vulnerability-triage-and-disclosure`) and whether it is a blocking finding (must fix before merge) or a follow-up (track, don't block).

5. **Recommend the earliest catch point.** For each threat, name where in the SDLC it is cheapest to catch: design review, this code review, a SAST rule, a DAST test, a runtime control (WAF rule, rate limiter). A threat that recurs across PRs is a signal to push the control upstream (a lint rule, a shared middleware) rather than re-flagging it every time.

6. **Produce the table.** Output a threats-and-mitigations table: Trust Boundary | STRIDE Category | Threat | Existing Mitigation (if any) | Recommended Mitigation | Earliest Catch Point | Severity. Keep it scoped to what the diff actually touches — do not pad it with generic advice unrelated to the change.

7. **Run alongside, not instead of, general code review.** This skill is a security-specialized layer. It does not replace a functional code review pass; flag security findings distinctly so they are triaged with appropriate urgency rather than mixed into style feedback.

Gotcha: threat modeling loses value as a one-time gate late in the cycle. Where possible, run this on the design document or early draft PR, not only at merge time — the whole point is to catch a missing authorization check before it ships, not to document it after.

## Checklist / quality gate
- Every trust boundary the diff introduces or modifies has been enumerated.
- All six STRIDE categories have been considered for each boundary (even if the answer is "not applicable, because...").
- Each threat has a recommended mitigation and an earliest-catch-point recommendation, not just a description of the risk.
- Blocking findings are clearly distinguished from follow-up findings.
- The table is scoped to the diff — no generic, unattached security advice.
- If a finding is severe enough to need formal severity scoring and a remediation SLA, it is handed off to `vulnerability-triage-and-disclosure` rather than left informally rated here.

## References
- OWASP DevSecOps Guideline — Threat Modeling: https://owasp.org/www-project-devsecops-guideline/latest/00b-Threat-modeling (recommends threat modeling run "ideally during each sprint," not as a one-time gate)
- STRIDE threat model (Microsoft-originated, widely adopted): Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege

## Composition
Runs alongside a general `code-review` pass as a security-specialized layer, not a replacement for it. Findings that need formal CVSS-style severity scoring and a remediation SLA hand off to `vulnerability-triage-and-disclosure`. Recurring findings that indicate a missing pipeline control feed into `sast-dast-sca-pipeline-integration` (add a rule so the same class of issue is caught automatically next time) or `secrets-scanning-remediation` if the finding is a leaked credential.
