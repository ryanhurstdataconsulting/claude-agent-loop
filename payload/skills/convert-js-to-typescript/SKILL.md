---
name: convert-js-to-typescript
description: Use for an incremental TypeScript migration of a JavaScript file, module, or whole project. Applies a strictness ladder for tsconfig settings, an any-elimination workflow, and type-narrowing patterns for common runtime shapes (API responses, form data, event handlers). Triggers include "convert this to TypeScript", a `.js` file sitting next to `.ts` siblings, a `// @ts-check` comment already present, an `any`-heavy file flagged in review, or a project adding TypeScript for the first time.
---

# convert-js-to-typescript

## Overview
Migrates JavaScript to TypeScript incrementally and safely — file by file, with a
strictness ladder that ratchets up over time instead of an all-or-nothing rewrite that
stalls halfway. Owns the conversion mechanics and type-safety ratchet, not the decision
of whether to adopt TypeScript in the first place.

## When to use
- A specific `.js`/`.jsx` file needs converting because it sits in a directory that is
  otherwise `.ts`/`.tsx`, or a PR explicitly asks for the conversion.
- A project is adopting TypeScript for the first time and needs an incremental
  onboarding path rather than a single giant migration PR.
- A file already has `// @ts-check` with JSDoc types and is ready to become a real
  `.ts` file.
- Code review flags a file as `any`-heavy and asks for tightening.

## Workflow
1. **Never do a whole-repo big-bang conversion.** Convert one file or one module
   boundary at a time, each as its own commit, so a type error introduced by the
   migration is trivially bisectable and the codebase stays shippable throughout.
2. **Start permissive, then ratchet up — the strictness ladder:**
   - **Rung 0:** rename `.js` → `.ts` (or `.jsx` → `.tsx`), fix only what's needed to
     compile with `strict: false`. This alone catches typos and obvious shape
     mismatches for free.
   - **Rung 1:** enable `noImplicitAny` for the converted file/directory (via a
     per-file `// @ts-nocheck` removal or a tsconfig `include` scoping) and add real
     types to every parameter and return value that TypeScript can't infer.
   - **Rung 2:** enable `strictNullChecks` and resolve every resulting error by
     narrowing (guard clauses, optional chaining) rather than blanket non-null
     assertions (`!`).
   - **Rung 3:** enable full `strict: true` for the file/module, then, once the whole
     project reaches this rung, flip `strict: true` at the project-wide tsconfig root.
   Do not jump straight to `strict: true` on a large legacy file — the error count
   becomes unreviewable and the migration stalls.
3. **Eliminate `any` deliberately, not by suppressing it.** For each `any`: prefer a
   concrete interface/type when the shape is known; `unknown` plus a type guard when
   the shape is genuinely dynamic (parsed JSON, third-party callback payloads); a
   named union when the value is one of a small closed set. Reserve `// eslint-disable
   @typescript-eslint/no-explicit-any` with an inline reason comment for the rare case
   where none of the above applies — never as the default escape hatch.
4. **Type common runtime shapes with narrowing, not casts:**
   - API responses: define the response interface from the actual contract (OpenAPI
     spec if one exists — see the API-contract-design pattern), then validate with a
     runtime schema (Zod, io-ts) at the network boundary rather than trusting a type
     assertion (`as ResponseType`) on untrusted data.
   - Form/event data: type event handlers with the framework's specific event type
     (`React.ChangeEvent<HTMLInputElement>`, not `any` or a bare `Event`) so `target`
     is correctly narrowed.
   - Nullable/optional fields: prefer `field?: string` plus an explicit guard at the
     point of use over a non-null assertion at the point of declaration.
5. **Verify the compiler and the tests together.** A conversion that compiles but
   silently changes runtime behavior (a coerced `==` now failing under stricter type
   narrowing, for instance) is worse than no conversion — run the existing test suite,
   not just `tsc --noEmit`, after every converted file.

## Checklist / quality gate
- [ ] Conversion was done file-by-file or module-by-module, each its own commit — not
      a single repo-wide rewrite.
- [ ] The file compiles at the target strictness rung with zero new suppressions
      beyond ones that carry an inline justification comment.
- [ ] No blanket `any` remains where a concrete type, `unknown`+guard, or union would
      work.
- [ ] External/untrusted data (API responses, form input, third-party callbacks) is
      validated at the boundary, not just cast.
- [ ] The existing test suite passes after conversion, confirming no runtime behavior
      change slipped in alongside the type change.

## References
- [Frontend Developer Roadmap](https://roadmap.sh/frontend) — "TypeScript is not a
  senior-only skill anymore"

## Composition
Feeds typed interfaces to `integrate-rest-api-client` (the typed fetch wrapper needs a
converted response type to be useful) and to `scaffold-react-component-with-tests` when
scaffolding new components in an already-converted, `.ts`-only directory.
