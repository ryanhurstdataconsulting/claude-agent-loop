---
name: backstage-catalog-entity-authoring
description: Use when registering a new service, API, library, resource, or system in a Backstage-style software catalog — writing or fixing a catalog-info.yaml, wiring ownership and team metadata, linking dependsOn/providesApis/consumesApis relations, or scaffolding TechDocs for a component. Triggers include "add this to the service catalog," a missing or invalid catalog-info.yaml, an orphaned entity with no owner in the catalog UI, or a component that exists in the repo but is invisible in Backstage.
---

# backstage-catalog-entity-authoring

## Overview
Backstage catalog entity authoring produces a correct, discoverable `catalog-info.yaml` (or equivalent entity descriptor) for a service, API, resource, or system, with accurate ownership and relationship metadata. The one job it owns: making sure a component that exists in code also exists — correctly and fully linked — in the organization's software catalog.

## When to use
- A new repository, service, or API is created and needs to appear in the internal software catalog.
- An existing catalog entity is missing ownership, is orphaned (`spec.owner` unset or pointing at a defunct team), or has stale `dependsOn`/`providesApis` links.
- A component is invisible in the catalog UI despite existing in source control — usually a missing or malformed `catalog-info.yaml`.
- TechDocs are requested for a component that has documentation in-repo but no `techdocs-ref` wiring.
- A golden-path template (see `golden-path-template-authoring`) needs its catalog-registration step filled in.

## Workflow
1. **Determine the entity kind first.** Backstage's catalog model distinguishes `Component`, `API`, `Resource`, `System`, `Domain`, and `Location` — do not default everything to `Component`. A database is a `Resource`; a REST/GraphQL interface is an `API`; a logical grouping of components is a `System`.
2. **Set required metadata precisely:**
   - `metadata.name` — unique, kebab-case, stable (renaming breaks existing links; treat as a near-permanent identifier).
   - `metadata.description` — one sentence, human-readable, no jargon a new hire wouldn't understand.
   - `spec.owner` — must resolve to an actual `Group` or `User` entity already in the catalog, not a free-text team name that doesn't exist as an entity. A dangling owner reference is the single most common catalog-hygiene failure.
   - `spec.type` — the catalog's controlled vocabulary for that kind (e.g., `service`, `website`, `library` for a `Component`); check the organization's existing taxonomy before inventing a new type value.
3. **Wire relationships explicitly, not implicitly.** `spec.dependsOn` for runtime dependencies, `spec.providesApis`/`spec.consumesApis` for API contracts, `spec.subcomponentOf`/`spec.system` for hierarchy. These relations are what make the catalog's dependency graph and impact-analysis views useful — an entity with no relations is a catalog entry, not a catalog citizen.
4. **Scaffold TechDocs when in-repo docs exist.** Add the `backstage.io/techdocs-ref: dir:.` annotation (or the correct path) and confirm an `mkdocs.yml` exists at that path; a `techdocs-ref` pointing at nothing produces a broken docs tab, which is worse than no docs tab.
5. **Validate before merge.** Run the entity through `catalog-info.yaml` schema validation (the Backstage catalog processor rejects malformed entities silently in some configurations) and confirm the referenced `owner`, `system`, and API entities already exist or are registered in the same batch.
6. **Confirm discoverability**, not just correctness — check that the catalog's `Location` or discovery config actually picks up the new file's path; a perfectly valid `catalog-info.yaml` that the catalog never scans is functionally invisible.

## Checklist / quality gate
- [ ] Entity `kind` matches what is actually being described (`Component` vs. `API` vs. `Resource` vs. `System`).
- [ ] `metadata.name` is unique, stable, kebab-case.
- [ ] `spec.owner` resolves to a real, already-registered `Group`/`User` entity.
- [ ] `spec.type` matches the organization's existing controlled vocabulary.
- [ ] `dependsOn`/`providesApis`/`consumesApis` reflect actual runtime relationships, not left empty by default.
- [ ] TechDocs annotation, if present, points at a path with a valid `mkdocs.yml`.
- [ ] Entity passes catalog schema validation and is confirmed picked up by the discovery/location config.

## References
- Backstage software catalog documentation — https://backstage.io/docs/features/software-catalog/
- Backstage software templates documentation — https://backstage.io/docs/features/software-templates/

## Composition
Consumed by `golden-path-template-authoring` as the catalog-registration step of a new scaffold. Pairs with `adr-authoring` when a `System`-level entity's boundaries need a documented rationale, and with `self-service-iac-module-catalog` when the entity being registered is infrastructure rather than application code.
