---
name: implement-authn-authz
description: Use when a new endpoint or route needs securing, or a login/session flow needs to be added — "add login to this app," "protect this route," "only admins should be able to call this," a missing-auth finding from a security review, or a 401/403 that should exist but doesn't. Walks through OAuth2/JWT flow selection, password-hashing setup, a role-based-access-control (RBAC) middleware scaffold, and the session-vs-token trade-off, rather than hand-rolling authentication from scratch. Also triggers on "rotate our JWT secret," "add a refresh-token flow," or "why is this endpoint reachable without a token."
---

# implement-authn-authz

## Overview
Implements authentication (proving who a caller is) and authorization
(deciding what that caller may do) as a deliberate flow choice with a
password-hashing and RBAC scaffold, rather than a bespoke, unreviewed
auth implementation. The one job it owns: no endpoint is reachable by an
unauthenticated or under-privileged caller by omission.

## When to use
- A new application or service needs a login/session flow from scratch.
- A specific endpoint or route needs to be protected, or restricted to a
  role/permission it currently lacks.
- A security review or penetration test flags a missing or bypassable
  auth check.
- A token-refresh, logout, or session-expiry flow is missing or broken.
- Password storage needs review (a plaintext or weakly hashed password
  column is a stop-everything finding).

## Workflow
1. **Never store a password in a reversible form.** Hash with a modern,
   slow, salted algorithm — bcrypt, scrypt, or Argon2id — never MD5, SHA-1,
   or unsalted SHA-256. If an existing system already uses a legacy hash,
   plan a migration (re-hash on next successful login) rather than leaving
   it in place. This is non-negotiable regardless of the rest of the flow.
2. **Choose the authentication flow based on the client type, not habit:**
   - **Session cookies (server-side session store)** — simplest, works well
     for a traditional server-rendered app or a first-party SPA served from
     the same domain. Use `HttpOnly`, `Secure`, and `SameSite` cookie flags;
     the session is revocable server-side at any time, which tokens are not.
   - **JWT (stateless bearer token)** — fits multi-service or mobile/native
     clients where a shared session store is impractical. Trade-off: a JWT
     cannot be revoked before its expiry without an additional denylist
     mechanism, so keep access-token lifetimes short (minutes, not days) and
     pair with a refresh token.
   - **OAuth2 / OIDC** — use when a third party (or a separate identity
     provider) needs to authenticate the user, or when the system needs
     "log in with X." Do not hand-roll an OAuth2 authorization-code flow;
     use a maintained library for the client and, where possible, a managed
     identity provider rather than running your own OIDC server.
   - **API keys** — appropriate for service-to-service or third-party
     integration traffic, not for end-user login. Scope each key narrowly
     and make it revocable independent of any other key.
3. **Separate access tokens from refresh tokens when using JWTs.** Short-lived
   access token (minutes) does the actual authorization on each request;
   a longer-lived refresh token (stored more carefully — `HttpOnly` cookie
   or secure storage, never `localStorage` for a refresh token) is
   exchanged for a new access token. Rotate the refresh token on each use
   and detect reuse of an already-rotated token as a signal of theft.
4. **Build authorization as middleware, not inline `if` checks scattered
   through handlers.** A single RBAC (or ABAC, if permissions are more
   granular than roles) middleware/decorator that runs before the handler
   and rejects on a missing or insufficient permission keeps the check
   impossible to accidentally skip on a new route.
   - Default-deny: a new route with no explicit permission annotation should
     fail closed, not open.
   - Check authorization *after* authentication and *before* any side
     effect, including read-only ones that expose data the caller shouldn't
     see.
5. **Handle the failure paths explicitly:** wrong credentials, expired
   token, malformed token, and insufficient permission are distinct cases —
   test each one, and return `401` (not authenticated) versus `403`
   (authenticated but not authorized) correctly rather than collapsing both
   into one status code.
6. **Rate-limit authentication endpoints specifically.** Login, password
   reset, and token-refresh endpoints are brute-force targets independent of
   whatever general rate limiting the rest of the API has.
7. **Log authentication and authorization decisions**, especially failures —
   they are the primary signal for detecting credential-stuffing or
   privilege-escalation attempts, but never log the credential or token
   value itself.

## Checklist / quality gate
- [ ] Passwords are hashed with bcrypt/scrypt/Argon2id — never a fast or
      unsalted hash.
- [ ] Token/session lifetimes are explicit and short for access tokens; a
      refresh or re-authentication path exists for longer sessions.
- [ ] Authorization is enforced via middleware with a default-deny posture,
      not scattered inline checks.
- [ ] `401` vs. `403` is distinguished correctly in both code and tests.
- [ ] Login, password-reset, and refresh endpoints are rate-limited.
- [ ] Refresh-token rotation and reuse detection exist for any long-lived
      JWT flow.
- [ ] No credential, token, or secret value appears in logs.
- [ ] Tests cover the failure paths (expired, malformed, wrong role) as
      thoroughly as the happy path.

## References
- [Backend Developer Roadmap — roadmap.sh](https://roadmap.sh/backend) (Authentication/Authorization)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)

## Composition
Pairs with `scaffold-rest-endpoint-with-tests` — every new endpoint decides its
auth requirement as part of that scaffold, and calls back into this skill's
RBAC middleware rather than reinventing a check. Feeds a broader security-
review-checklist skill and should be re-run whenever that checklist flags an
auth gap.
