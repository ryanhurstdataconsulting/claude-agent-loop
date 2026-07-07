---
name: audit-app-store-review-compliance
description: Use before submitting a mobile app for App Store or Play Store review, or after a build was rejected — checks permission-usage justifications, the iOS privacy manifest and Play Data safety declaration, store-listing metadata, and cross-references the rejection reason against a lookup of common causes. Triggers include "get this ready for App Store submission", an App Store Connect or Play Console rejection email, "why was our build rejected", missing privacy-manifest/usage-description strings, or a request to check store-compliance before a release.
---

# audit-app-store-review-compliance

## Overview
Audits a mobile app against App Store and Play Store review guidelines before submission, and
triages an existing rejection against a lookup of common causes. The one job this skill owns is
the compliance checklist and rejection diagnosis — it does not draft store-listing marketing
copy or make the underlying product decision about a flagged feature.

## When to use
- A build is about to be submitted for the first time, or the first time on a given platform.
- An app was rejected and the rejection reason needs triage against known common causes before
  resubmitting blind.
- A new permission, SDK, or third-party tracking capability was added and its store-compliance
  impact (privacy manifest, usage-description string, data-safety declaration) has not been
  checked.
- Store guidelines have changed since the app's last submission — treat this checklist as
  needing a freshness check before each use, since platform policy shifts often.

## Workflow
1. **Verify every requested permission has a justification string and is actually used.** Both
   platforms reject apps requesting permissions (camera, location, contacts, background
   location, tracking) without a clear, honest in-context usage description. Remove any
   permission the app declares but does not use — an unused permission is itself a common
   rejection cause.
2. **iOS: confirm the privacy manifest (`PrivacyInfo.xcprivacy`) is present and accurate** for
   the app and for every third-party SDK that collects data — required-reason API usage,
   tracking domains, and data-collection categories must match what the app and its SDKs
   actually do, not a boilerplate copy from a template.
3. **Android: confirm the Play Console Data safety section matches the app's actual data
   collection and sharing behavior.** A mismatch between the declared behavior and the app's
   observed network/SDK behavior is a rejection and policy-strike risk, not just a review delay.
4. **Check for guideline-specific red flags before submission:**
   - Placeholder or broken functionality, dead links, or test/debug UI left reachable in the
     build under review.
   - Login-gated apps without a demo account provided to the reviewer.
   - In-app purchase or subscription flows not using the platform's required payment mechanism
     for digital goods.
   - Any web content, third-party engine, or embedded browser that could read as "not a native
     app experience" if the platform's guidelines restrict that.
   - Crashes or ANRs on first launch on the reviewer's likely test device/OS version — this is
     the single most common instant rejection.
5. **Cross-check store-listing metadata** (screenshots reflect the actual current build,
   age rating matches content, keywords/description do not overreach on claims) since metadata
   mismatches are reviewed alongside the binary.
6. **If triaging an existing rejection**, extract the exact guideline number/section cited and
   match it against the platform's published guideline text and the common-rejection-reason
   lookup rather than guessing at the underlying cause — resubmitting without addressing the
   cited section restarts the review clock for no gain.
7. **Re-run this checklist on every submission**, not just the first — a new SDK, a new
   permission, or a guideline update since the last approval can each independently trigger a
   fresh rejection.

## Checklist / quality gate
- [ ] Every declared permission is both used and has an honest, specific usage-description
      string.
- [ ] iOS privacy manifest reflects actual data collection for the app and all bundled SDKs.
- [ ] Android Data safety declaration matches observed data collection/sharing behavior.
- [ ] The submitted build has no dead links, placeholder content, or reachable debug UI.
- [ ] Login-gated flows include reviewer demo credentials or a bypass, as applicable.
- [ ] The build launches cleanly with no first-launch crash on a representative device/OS
      version.
- [ ] Store-listing screenshots and description match the current build's actual behavior.

## References
- fastlane `deliver` and `supply` documentation: [fastlane actions — docs.fastlane.tools](https://docs.fastlane.tools/actions/)
- [Mobile CI/CD with Fastlane — Maranatha Technologies](https://www.maranathatechnologies.com/blog/mobile-app-ci-cd-fastlane-deployment)
- [App Store Review Guidelines — developer.apple.com](https://developer.apple.com/app-store/review/guidelines/)
- [Play Console policy center — support.google.com](https://support.google.com/googleplay/android-developer/answer/9859455)

## Composition
Run this skill as the gate immediately before flipping on the `submit_for_review`/production
step in a pipeline built by `set-up-fastlane-release-pipeline`. Consumes the permission and
SDK inventory that `integrate-crash-reporting-and-monitoring` and
`implement-offline-first-sync` introduce, since new SDKs and permissions are common
compliance-drift sources between submissions.
