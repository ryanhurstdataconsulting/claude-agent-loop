---
name: containerize-service-for-deployment
description: Use when a service needs a Dockerfile and a container build wired into CI — "containerize this app," "add a Dockerfile," "this build image is huge," or a container failing its orchestrator's health check on deploy. Produces a multi-stage Dockerfile, a health-check endpoint, and a minimal-base-image setup, rather than a single-stage image that ships build tooling and dev dependencies to production. Also triggers on a reported container CVE from an outdated base image, a container running as root, or a slow CI build from a poorly ordered Dockerfile.
---

# containerize-service-for-deployment

## Overview
Produces a production-ready container image for a service — a multi-stage
Dockerfile, a health-check endpoint, and a minimal base image — instead of a
single-stage image that ships compilers, dev dependencies, and root-level
processes to production. The one job it owns: the image that runs in
production contains only what production needs to run.

## When to use
- A service has no Dockerfile yet and needs one for deployment.
- An existing image is too large, builds too slowly, or fails a
  vulnerability scan because of an outdated or bloated base image.
- An orchestrator (Kubernetes, ECS, etc.) reports failing health checks on a
  container that otherwise runs fine locally.
- A security review flags a container running as root or with unnecessary
  build tooling present in the runtime image.

## Workflow
1. **Use a multi-stage build, always.** One stage compiles/builds with the
   full toolchain (compilers, dev dependencies, package managers); a
   separate, final stage copies only the built artifact and runtime
   dependencies into a clean base image. The build stage's tooling never
   reaches the shipped image.
   ```dockerfile
   FROM node:20 AS build
   WORKDIR /app
   COPY package*.json ./
   RUN npm ci
   COPY . .
   RUN npm run build

   FROM node:20-slim AS runtime
   WORKDIR /app
   COPY --from=build /app/dist ./dist
   COPY --from=build /app/node_modules ./node_modules
   COPY package.json ./
   USER node
   EXPOSE 3000
   HEALTHCHECK --interval=30s --timeout=3s CMD node healthcheck.js || exit 1
   CMD ["node", "dist/index.js"]
   ```
2. **Choose the smallest base image that still works.** Prefer a `-slim` or
   `-alpine` variant, or a distroless image, over the full base — fewer
   packages mean a smaller attack surface and fewer CVEs to track. Pin the
   base image to a specific tag (and, for anything security-sensitive, a
   digest) rather than `latest`, so a rebuild does not silently change what
   ships.
3. **Order Dockerfile instructions from least to most frequently changing**
   to maximize layer-cache reuse: install system dependencies first, then
   copy dependency manifests (`package.json`, `requirements.txt`,
   `go.mod`) and install dependencies, and copy application source code
   last. A Dockerfile that copies the whole source tree before installing
   dependencies invalidates the dependency-install cache on every code
   change.
4. **Run as a non-root user.** Create or reuse a non-privileged user in the
   final stage and switch to it before `CMD`/`ENTRYPOINT`. A container
   running as root that gets compromised gives an attacker root inside the
   container by default.
5. **Add a real health-check endpoint**, not a placeholder. It should verify
   the process can actually serve traffic (e.g., a database connection
   check for readiness) and be cheap to call frequently. Distinguish
   liveness (is the process alive at all) from readiness (can it serve
   traffic right now) if the orchestrator supports both — restarting a
   container that is merely warming up, rather than actually dead, causes
   more outages than it prevents.
6. **Keep secrets out of the image entirely.** No secret value baked into a
   layer via `ENV`, `ARG`, or a copied file — even a later layer that
   deletes the file leaves it recoverable from an earlier layer. Inject
   secrets at runtime via the orchestrator's secret-management mechanism or
   environment injection, not the build.
7. **Set explicit resource behavior**: a `.dockerignore` that excludes
   `node_modules`, `.git`, build artifacts, and local env files from the
   build context, and (at the orchestrator level, not in the Dockerfile
   itself) memory/CPU requests and limits sized from real profiling, not a
   guess.
8. **Scan the built image** for known vulnerabilities in CI before it is
   allowed to deploy, and fail the build on criticals rather than only
   reporting them after the fact.

## Checklist / quality gate
- [ ] Build uses multi-stage; the final image contains no compiler, dev
      dependency, or build-only tooling.
- [ ] Base image is a minimal variant, pinned to a specific tag or digest,
      not `latest`.
- [ ] Dockerfile instruction order maximizes cache reuse (dependencies
      before source code).
- [ ] Container runs as a non-root user.
- [ ] A real health-check endpoint exists and is wired to the
      orchestrator's liveness/readiness probes.
- [ ] No secret value is present in any image layer.
- [ ] `.dockerignore` excludes local artifacts and secrets from the build
      context.
- [ ] The built image passes a vulnerability scan in CI before deploy.

## References
- [Backend Developer Roadmap — roadmap.sh](https://roadmap.sh/backend) (Containerization)
- [Docker docs — Multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker docs — Best practices for writing Dockerfiles](https://docs.docker.com/build/building/best-practices/)

## Composition
Feeds a CI/CD pipeline-setup skill for the build → scan → push → deploy
stages, and pairs with `add-structured-logging-and-tracing` so the
containerized service emits logs/traces the orchestrator's log driver can
collect. The health-check endpoint this skill adds is also the natural target
for a readiness probe in a Kubernetes hardening or platform golden-path skill.
