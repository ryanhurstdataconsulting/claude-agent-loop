---
name: dockerfile-hardening
description: Use when writing a new Dockerfile or auditing an existing one for production readiness — a single-stage build that ships compilers and dev dependencies into the runtime image, a container running as root, a base image pinned to `:latest` instead of a digest, a vulnerability scanner flagging an outdated base image, a missing or incomplete `.dockerignore`, or a bloated image slowing down CI. Produces a hardened, multi-stage Dockerfile with a minimal or distroless final stage, a pinned base-image digest, a non-root user, and a vulnerability scan wired into the build, rather than an informal read-through. Also triggers on "harden this Dockerfile," a failed CIS Docker Benchmark check, a reported container CVE, or slow, poorly cached image builds.
---

# dockerfile-hardening

## Overview
Applies a fixed, checkable set of hardening rules to a Dockerfile so the
image that reaches production carries no more than production needs: no
build toolchain, no root process, no floating tags, and no known-vulnerable
packages left unscanned. The one job it owns: turning a working Dockerfile
into a hardened one, not designing a service's container strategy from
scratch.

## When to use
- A Dockerfile exists and needs a security/production-readiness pass before
  it ships or before a compliance review.
- A vulnerability scanner or CIS Docker Benchmark check flags an existing
  image.
- The image runs a process as root, uses `:latest` or another floating tag,
  or ships compilers, package managers, and dev dependencies into the
  runtime stage.
- CI build times or image sizes are creeping up because of poor layer-cache
  ordering or a missing `.dockerignore`.
- There is no Dockerfile at all yet — hand this off to
  `containerize-service-for-deployment` for the initial scaffold, then apply
  this checklist to the result.

## Workflow
1. **Convert to (or verify) a multi-stage build.** One stage builds with the
   full toolchain; a separate final stage copies only the built artifact and
   runtime dependencies into a clean base. Nothing from the build stage's
   `RUN apt-get install build-essential` (or equivalent) should reach the
   shipped image.
2. **Pick a minimal or distroless final base image.** Prefer
   `gcr.io/distroless/*`, an `-alpine`, or a `-slim` variant over a full
   OS image for the runtime stage — fewer packages mean a smaller attack
   surface and a smaller scan surface.
3. **Pin the base image by digest, never by a floating tag.**
   ```dockerfile
   # Bad — resolves to a different image on every rebuild
   FROM node:20-slim

   # Good — reproducible, and the digest itself is auditable
   FROM node:20-slim@sha256:3d1e...c9f2
   ```
   A tag like `:latest` or even `:20-slim` can point to a different image
   tomorrow; a digest cannot.
4. **Run as a non-root user.** Add a dedicated user in the final stage and
   switch to it before `CMD`/`ENTRYPOINT`:
   ```dockerfile
   RUN addgroup --system app && adduser --system --ingroup app app
   USER app
   ```
   Verify no `USER root` (or an absent `USER` directive, which defaults to
   root) survives into the final stage.
5. **Write a complete `.dockerignore`.** At minimum: `.git`, `node_modules`
   (or the language equivalent), test fixtures, `.env*`, CI config, and any
   local secrets or credentials files. A missing `.dockerignore` entry is
   the most common way a `.env` file or a `.git` directory with credential
   history ends up baked into a layer.
6. **Order layers for cache efficiency.** Copy dependency manifests
   (`package.json`/`requirements.txt`/`go.mod`) and install dependencies
   *before* copying source code, so a source-only change doesn't invalidate
   the dependency-install layer:
   ```dockerfile
   COPY package*.json ./
   RUN npm ci
   COPY . .
   ```
7. **Never bake secrets into a layer.** A secret passed via `ARG` or `ENV`
   persists in the image history even if a later layer removes the file.
   Use BuildKit's `--mount=type=secret` for build-time secrets, and inject
   runtime secrets at container start (orchestrator secret store, not the
   image).
8. **Wire a vulnerability scan into the build.** Add a Trivy (or equivalent)
   scan as a build or CI step that fails on high/critical findings in the
   final image, not just the build stage.
9. **Confirm the shrink.** Compare image size and `docker history` layer
   count before and after — a hardened multi-stage build should be
   materially smaller than the single-stage original.

## Checklist / quality gate
- [ ] Multi-stage build; the final stage contains no compilers, package
      managers, or dev dependencies.
- [ ] Base image pinned by digest, not a floating tag like `:latest`.
- [ ] Final base image is minimal or distroless.
- [ ] A non-root `USER` is set before `CMD`/`ENTRYPOINT`.
- [ ] `.dockerignore` excludes VCS metadata, local secrets, and build
      artifacts not needed in the image.
- [ ] No secret value appears in any image layer or build history
      (`docker history --no-trunc` checked, or build secrets used instead
      of `ARG`/`ENV`).
- [ ] Dependency-manifest layers are copied and installed before source
      code, for cache efficiency.
- [ ] A vulnerability scan (Trivy or equivalent) runs against the final
      image and gates the build on high/critical findings.
- [ ] Image size and layer count measured against the pre-hardening
      baseline.

## References
- [Docker build best practices](https://docs.docker.com/build/building/best-practices/)
- [Docker BuildKit build secrets](https://docs.docker.com/build/building/secrets/)
- [Trivy container image scanning](https://trivy.dev/)
- CIS Docker Benchmark (consult the current edition for the full control
  set; not independently verified against this checklist)

## Composition
Hands off from `containerize-service-for-deployment` when no Dockerfile
exists yet — that skill scaffolds the initial multi-stage build and health
check; this skill hardens what's already there. Feeds the image-scanning
stage into `sast-dast-sca-pipeline-integration` and the image-supply-chain
half of a `kubernetes-security-hardening` review. A hardened Dockerfile is a
common component of `golden-path-template-authoring`. Wire the Trivy step in
via `ci-pipeline-authoring`.
