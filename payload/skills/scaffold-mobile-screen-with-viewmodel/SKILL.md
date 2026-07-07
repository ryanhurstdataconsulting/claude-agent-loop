---
name: scaffold-mobile-screen-with-viewmodel
description: Use when a mobile codebase (Jetpack Compose, SwiftUI, or React Native) needs a new screen, feature module, or view — generates the screen composable/view plus its ViewModel or state-holder, navigation wiring, and a unit test for the presentation logic. Triggers include "add a screen for X", "new feature module", a request for MVVM/MVI scaffolding, a bare view with no state layer, or a screen whose business logic is tangled directly into UI code with no testable seam.
---

# scaffold-mobile-screen-with-viewmodel

## Overview
Generates a new mobile screen as a paired unit: a declarative view (Compose, SwiftUI, or a
React Native component) and a ViewModel-equivalent state holder that owns its business logic,
loading/error states, and navigation events. The one job this skill owns is keeping UI and
state cleanly separated from the first commit, so the state layer is unit-testable without a
UI test harness.

## When to use
- A new screen, tab, or feature module is requested in an app already using MVVM, MVI, or a
  comparable unidirectional-data-flow pattern.
- An existing screen has business logic embedded directly in the view (a `Composable` calling
  a repository directly, a `UIViewController` doing network calls) and needs to be split out.
- A request mentions "ViewModel", "state holder", "presenter", or asks for a screen "wired to
  navigation."
- The codebase has an established navigation graph (Jetpack Navigation, SwiftUI
  `NavigationStack`, React Navigation) that the new screen must register with.

## Workflow
1. **Identify the platform and pattern already in use.** Do not introduce a new architecture
   pattern into an existing app — grep for the nearest sibling screen and match its shape
   (file naming, DI mechanism, state-emission style: `StateFlow`/`LiveData` on Android,
   `@Observable`/`@Published` on iOS, a hook or Redux-style store on React Native).
2. **Define the state contract first.** Write the UI-state data class/struct (`data class
   FooUiState(val isLoading: Boolean, val items: List<Item>, val error: String?)` or the
   SwiftUI/RN equivalent) before writing any view code — this is the seam the unit test
   targets.
3. **Scaffold the state holder.**
   - Compose/Android: a `ViewModel` exposing `StateFlow<FooUiState>`, injected dependencies via
     the project's existing DI (Hilt/Koin), one-shot events via a `Channel`/`SharedFlow` for
     navigation and snackbars (never expose navigation as direct state — it replays on
     rotation).
   - SwiftUI: an `@Observable` (or `ObservableObject` on older targets) class owning
     `@Published`/tracked state, injected dependencies via initializer, not singletons.
   - React Native: a hook (`useFooScreen`) or a store slice, matching whatever the app already
     uses for cross-screen state.
4. **Scaffold the view.** The view reads state and dispatches intents/events only — no direct
   service or repository calls from the view layer. Keep loading, error, and empty states as
   explicit branches, not implicit.
5. **Wire navigation.** Register the screen in the existing nav graph/route table; pass
   arguments through the platform's typed navigation mechanism, not raw strings, when the
   project supports it.
6. **Write the state-holder unit test.** Cover: initial state, a successful load transition, an
   error transition, and one user-intent-triggered transition. Use the project's existing test
   doubles/fakes for the data layer rather than hitting a real network or database.
7. **Skip UI/snapshot tests unless the project already has that harness wired** — this skill's
   job stops at a testable state layer; hand off to a full UI-test-authoring skill if
   screenshot or interaction tests are also required.

## Checklist / quality gate
- [ ] State holder is unit-testable without instantiating the view or a UI test framework.
- [ ] No network, database, or file-system call happens directly inside the view.
- [ ] Navigation is triggered via a one-shot event, not stored as persistent state.
- [ ] Loading, error, and empty states are all explicitly represented and reachable in tests.
- [ ] The new screen matches the naming and DI conventions of its nearest existing sibling.
- [ ] Unit test covers at least: initial state, success path, error path, one intent.

## References
- [Android Developer Roadmap](https://roadmap.sh/android)
- [iOS Developer Roadmap](https://roadmap.sh/ios)
- Android architecture guidance: [Guide to app architecture — developer.android.com](https://developer.android.com/topic/architecture)
- Apple's state-and-data-flow guidance: [Managing model data in your app — developer.apple.com](https://developer.apple.com/documentation/swiftui/managing-model-data-in-your-app)

## Composition
Feeds into `set-up-fastlane-release-pipeline` once a screen is ready to ship. Pairs with
`write-unit-tests-with-coverage-target` for the state-holder test suite and with
`implement-offline-first-sync` when the new screen's state holder needs local persistence and
reconciliation rather than a simple network fetch. For screens with complex conflict-prone
data, hand off to `implement-offline-first-sync` before finalizing the state contract.
