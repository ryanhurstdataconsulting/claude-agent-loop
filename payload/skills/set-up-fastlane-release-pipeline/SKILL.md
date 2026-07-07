---
name: set-up-fastlane-release-pipeline
description: Use when a mobile app needs an automated build-sign-upload pipeline for the App Store or Play Store — authoring a Fastfile, wiring lanes for build/test/sign/upload, setting up match-based code signing, or configuring a beta-track (TestFlight/Internal Testing) versus production release flow. Triggers include "set up Fastlane", "automate our App Store release", manual TestFlight uploads, expired provisioning profiles, code-signing errors in CI, or a request to wire mobile release automation into an existing CI/CD pipeline.
---

# set-up-fastlane-release-pipeline

## Overview
Authors a Fastlane-based release pipeline that takes a mobile app from source to a signed,
uploaded build with no manual Xcode/Android Studio steps. The one job this skill owns is the
lane-based build → sign → upload → submit chain, including code-signing automation, not the
app's feature code itself.

## When to use
- A mobile app has no automated release path and store submissions are done by hand through
  Xcode Organizer or Android Studio's build menu.
- CI/CD exists for build and test but stops short of signing and store upload.
- Code-signing errors surface in CI ("no signing certificate found", "provisioning profile
  doesn't match", expired certificates) that a shared signing setup would prevent.
- A request to add a beta-distribution track (TestFlight, Play Internal/Closed Testing,
  Firebase App Distribution) alongside or ahead of production release.
- Multiple developers each manage their own local signing certificates — a `match`-style
  centralized signing setup is overdue.

## Workflow
1. **Confirm platform scope.** iOS only, Android only, or both — this changes which lanes and
   signing tooling apply (`match`/`sigh`/`cert` for iOS; a keystore + Gradle signing config for
   Android).
2. **Set up centralized code signing before writing lanes.**
   - iOS: use `match` backed by a private encrypted git repo or cloud storage — never commit
     raw `.p12`/provisioning-profile files to the app's own repository.
   - Android: reference an encrypted keystore stored in CI secrets, not the repo; wire it via
     `gradle.properties` injected at build time, never hardcoded.
3. **Define lanes in the `Fastfile`, one responsibility each:**
   ```ruby
   lane :test do
     # unit/UI test invocation, matching the project's existing test command
   end

   lane :beta do
     match(type: "appstore", readonly: true)
     increment_build_number
     build_app(scheme: "App")
     upload_to_testflight(skip_waiting_for_build_processing: true)
   end

   lane :release do
     match(type: "appstore", readonly: true)
     build_app(scheme: "App")
     upload_to_app_store(submit_for_review: false, automatic_release: false)
   end
   ```
   Keep `readonly: true` on `match` in CI — signing assets are provisioned ahead of time, not
   generated on the fly by a CI runner.
4. **Gate `submit_for_review`/`automatic_release` behind an explicit flag or a separate lane.**
   Automated build/sign/upload is safe to fully automate; the actual store-review submission
   and public release are a human go/no-go — do not wire that behind a green CI run without an
   explicit approval step.
5. **Wire environment- and lane-specific secrets** (API keys for App Store Connect, a Play
   Console service-account JSON, `match` decryption passphrase) through the CI platform's
   secret store, never through committed `.env` files.
6. **Add a beta-track lane distinct from the production lane** so internal/TestFlight builds
   can ship on every merge to a release branch while production submission stays a deliberate,
   separate trigger.
7. **Version bump automatically, tag manually or on merge.** Auto-increment the build number
   per lane run; let the marketing/semantic version bump be an explicit, reviewed step tied to
   a release branch or tag, not silent automation.
8. **Verify with a dry run** — `beta` lane targeting an internal test group before trusting the
   `release` lane against production.

## Checklist / quality gate
- [ ] No signing certificate, provisioning profile, or keystore is committed to the app repo.
- [ ] `match` (or equivalent) runs `readonly` in CI; signing assets are pre-provisioned.
- [ ] A beta/internal-testing lane exists and is distinct from the production-submission lane.
- [ ] Store submission (`submit_for_review`, production rollout) requires an explicit trigger,
      not an automatic one on every merge.
- [ ] All secrets (API keys, keystore passphrase, `match` passphrase) live in the CI secret
      store, not in the repository or a plaintext config file.
- [ ] Build numbers auto-increment without colliding across lanes/branches.

## References
- [fastlane.tools](https://fastlane.tools/)
- [fastlane match documentation](https://docs.fastlane.tools/actions/match/)
- [CI/CD requirements for mobile applications — CircleCI](https://circleci.com/blog/ci-cd-requirements-for-mobile/)
- [Mobile CI/CD with Fastlane — Maranatha Technologies](https://www.maranathatechnologies.com/blog/mobile-app-ci-cd-fastlane-deployment)

## Composition
Specializes the cross-cutting `set-up-cicd-pipeline-for-app` skill for the mobile platform;
reuse that skill's stage-ordering checklist (lint → test → build → deploy) and layer this
skill's signing/upload specifics on top. Hands off to `audit-app-store-review-compliance`
before flipping the `release` lane's `submit_for_review` flag on for the first time. Pairs with
`integrate-crash-reporting-and-monitoring` for symbol/dSYM upload, which is commonly added as a
step inside the same `beta`/`release` lanes.
