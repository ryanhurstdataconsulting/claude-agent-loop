---
name: integrate-crash-reporting-and-monitoring
description: Use when a mobile app needs crash reporting and performance monitoring added or upgraded — SDK integration for tools such as Sentry, Crashlytics, Datadog, or Instabug, wiring symbol/dSYM upload for readable Android/iOS stack traces, or configuring alert thresholds. Triggers include "add crash reporting", symbolicated stack traces coming back blank or as raw addresses, missing dSYM/mapping-file uploads in a release pipeline, "we're flying blind on crashes in production", or a request to set up alerting for crash-free-session-rate regressions.
---

# integrate-crash-reporting-and-monitoring

## Overview
Integrates a crash-reporting and performance-monitoring SDK into a mobile app end to end: SDK
initialization, symbol upload wiring so stack traces are human-readable, and alert-threshold
configuration. The one job this skill owns is turning raw crashes into actionable,
symbolicated, alertable signal — not the release pipeline that ships the build itself.

## When to use
- An app has no crash-reporting SDK integrated, or crashes are only visible through app-store
  crash reports (typically incomplete and lagging days behind).
- Crash reports arrive with unsymbolicated stack traces — raw memory addresses on iOS, obscured
  method names after R8/ProGuard minification on Android.
- A release pipeline builds and ships without uploading `dSYM` files (iOS) or a mapping file
  (Android `mapping.txt`), so every crash from that build is unreadable after the fact.
- No alerting exists for crash-free-session-rate or crash-free-user-rate regressions after a
  release — issues surface from user complaints instead of monitoring.
- A migration between crash-reporting vendors is requested.

## Workflow
1. **Confirm the chosen SDK and platform scope.** Common choices: Sentry, Firebase Crashlytics,
   Datadog RUM, Instabug. Match whichever the project (or its ecosystem — e.g., an app already
   on Firebase) already leans toward rather than introducing a second vendor.
2. **Initialize the SDK as early as possible in the app lifecycle** — `Application.onCreate()`
   on Android, `application(_:didFinishLaunchingWithOptions:)` on iOS, before any other
   third-party SDK that might crash during its own init — so early-launch crashes are still
   captured.
3. **Wire symbol upload into the build, not as a manual step:**
   - iOS: automate `dSYM` upload as a build-phase script or a Fastlane action
     (`upload_symbols_to_crashlytics`, or the vendor's equivalent) so every archived build's
     symbols land in the crash tool automatically — a build shipped without its `dSYM` produces
     permanently unsymbolicated crashes for that version.
   - Android: upload the R8/ProGuard `mapping.txt` per build variant, tagged with the matching
     `versionCode`/`versionName` so the crash tool can match incoming crash reports to the
     right mapping file.
4. **Set release/version tagging on every event.** Tag crashes and performance events with the
   app version and build number so regressions can be bisected to a specific release, not just
   "sometime this month."
5. **Scrub PII before it reaches the crash tool.** Configure the SDK's `beforeSend`/scrubbing
   hook to strip user identifiers, auth tokens, and free-text user input from breadcrumbs and
   error context before upload — do this at integration time, not as a retrofit.
6. **Configure alert thresholds**, not just dashboards: a crash-free-session-rate drop below an
   agreed floor (commonly 99%+ for a mature app) on a fresh release should page or notify
   automatically, scoped to the release's rollout window rather than an all-time average that
   dilutes a spike.
7. **Verify end to end with a forced test crash** on a debug/staging build before relying on the
   integration — confirm the event appears in the dashboard, symbolicated, tagged with the
   correct release.

## Checklist / quality gate
- [ ] SDK initializes before any other third-party SDK that could crash during startup.
- [ ] Symbol/mapping-file upload is automated inside the build or release pipeline, not a
      manual post-build step a human can forget.
- [ ] A forced test crash appears in the dashboard, fully symbolicated, with the correct
      release/build tag.
- [ ] PII scrubbing is configured before any real user traffic reaches the SDK.
- [ ] An alert threshold exists for crash-free-session-rate regression on new releases, not
      only a static dashboard.
- [ ] Crash and performance events are both tagged with app version and build number.

## References
- Mobile CI/CD and monitoring integration pattern: [CI/CD requirements for mobile applications — CircleCI](https://circleci.com/blog/ci-cd-requirements-for-mobile/)
- [Sentry mobile documentation](https://docs.sentry.io/platforms/)
- [Firebase Crashlytics documentation](https://firebase.google.com/docs/crashlytics)

## Composition
Commonly wired as a step inside the lanes built by `set-up-fastlane-release-pipeline` (symbol
upload alongside the build/sign/upload chain). Shares its telemetry-tagging discipline with the
cross-cutting `add-structured-logging-and-tracing` skill — reuse the same release/version
tagging convention across crash reports, logs, and traces so an incident can be correlated
across all three. Feeds evidence into `facilitate-incident-postmortem` when a crash spike
triggers an incident review.
