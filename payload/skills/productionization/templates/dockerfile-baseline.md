# Dockerfile baseline patterns

> Illustrative only — select the actual base images, package manager
> commands, and runtime entrypoint from the stack Phase 1 (Inventory)
> identified. Every pattern below shares the same shape: multi-stage,
> pinned base images, non-root runtime user, minimal final image.

## Generic multi-stage shape

```dockerfile
FROM <builder-image>@sha256:<pinned-digest> AS build
WORKDIR /build
COPY <dependency-manifests> ./
RUN <deterministic-dependency-install>
COPY . .
RUN <build-and-test-command>

FROM <minimal-runtime-image>@sha256:<pinned-digest>
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY --from=build --chown=app:app /build/<runtime-output> ./
USER app
EXPOSE 8080
ENV PORT=8080
CMD ["<runtime>", "<entrypoint>"]
```

## Python (API/worker/pipeline)

- Builder image: `python:<version>-slim` pinned to a digest.
- Dependency install: `pip install --no-cache-dir -r requirements.txt`
  (or `poetry export` first, if the project uses Poetry/pyproject.toml).
- Runtime image: same slim base, copy only the installed site-packages
  and application source — never the build toolchain.
- Non-root user, `EXPOSE` the app's actual listen port from
  `productionization-intake.yaml`.

## Node/Next.js (web)

- Builder image: `node:<version>-slim` pinned to a digest.
- Dependency install: `npm ci` (never `npm install` in a build — it can
  resolve differently than the lockfile).
- Build: `npm run build` (Next.js standalone output mode keeps the final
  image small — check `next.config.mjs` for `output: "standalone"`).
- Runtime image: copy only `.next/standalone`, `.next/static`, and
  `public/` — never `node_modules` from the builder stage if standalone
  output is enabled.

## Verification checklist (any stack)

- [ ] Base images pinned to a digest, not a floating tag.
- [ ] Final image runs as a non-root user.
- [ ] `.dockerignore` excludes tests, `.git/`, local env files, and
      editor state.
- [ ] `docker build app/` succeeds from a clean checkout with no access
      to `agent/`, `evidence/`, or `scratch/`.
- [ ] Image has only the Linux capabilities it needs (no privileged mode).
