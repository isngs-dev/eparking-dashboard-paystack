# Security Patterns

## Authentication Architecture

### JWT-Based Authentication
- JWT claims: `iss`, `sub` (user ID), `email`, `tenant_id`, `role`, `project_ids`, `company_id`, `tenant_ids`, `jti` (unique token ID), `iat`, `exp`, and optional `aud`
- Tokens are signed with HS256; the decoder **pins the algorithm** (`alg != "HS256"` is rejected before anything else — no alg-confusion attacks) and compares signatures with `hmac.compare_digest`
- Issuer and expiry are always validated; audience is validated when `JWT_AUDIENCE` is configured
- Role-specific claim requirements are enforced at decode time (a TENANT_USER token without `tenant_id`, or a CLIENT_ADMIN token without `company_id`/`tenant_ids`, is rejected)
- Tokens are stored in httpOnly cookies (`httpOnly: true`, `secure` in production, `sameSite: "lax"`, 1h maxAge)

**Reusable Insight:** httpOnly cookies prevent XSS token theft. Never store tokens in localStorage or sessionStorage — and always pin the signing algorithm server-side; trusting the token header's `alg` is a classic JWT break.

### Token Lifecycle
1. User submits credentials (email + password); login failures return a generic "Invalid email or password"
2. Server validates credentials against database
3. Server generates JWT with claims (including a unique `jti`)
4. Frontend server action sets the httpOnly cookie with Secure, SameSite flags
5. The Next.js server layer attaches the token as a Bearer header on backend calls; browser JS never sees it
6. Backend validates token (signature, issuer, expiry, audience, blacklist) on each request
7. **Logout revokes server-side:** the frontend logout action calls `POST /auth/logout` (best-effort, 3s timeout) which adds the token's `jti` to a Redis blacklist with TTL equal to its remaining lifetime, then deletes the cookie

**Reusable Insight:** JWTs are stateless by design; a JTI-based Redis blacklist restores revocation. Crucially, logout must actually *call* the revocation endpoint — deleting only the cookie leaves the token valid until expiry (an audit finding here: the blacklist was dead code until logout was wired to it).

### Password Reset Flow (admin-issued, enumeration-safe)
1. An admin issues a reset token for a user (`POST /admin/users/{id}/password-reset`); the raw token is returned once to the admin, who relays it out-of-band
2. Only a PBKDF2 hash of the token is stored, with expiry and a `consumed_at` column — the raw token is never persisted or logged
3. The public redeem endpoint (`/auth/password-reset/redeem`) **always returns the same generic 200 response** — valid, invalid, expired, consumed, and unknown-email all look identical
4. For unknown emails, a dummy PBKDF2 verification runs so response *timing* can't be used to enumerate addresses
5. The consuming UPDATE re-asserts `consumed_at IS NULL` in its WHERE clause, so two concurrent redeems of the same token cannot both succeed (TOCTOU fix)
6. New passwords must pass the same minimum-length validation as account creation

**Reusable Insight:** Reset flows leak through status codes, message wording, timing, and race windows — not just storage. Single-use + time-limited + hashed-at-rest + constant response + constant-ish timing + atomic consume is the full checklist.

## Authorization

### Role-Based Access Control (RBAC)
- Roles (three-tier): **PLATFORM_ADMIN** (global), **CLIENT_ADMIN** (company-scoped to a `tenant_ids` list), **TENANT_USER** (one tenant + assigned `project_ids`)
- Legacy `ADMIN`/`CLIENT` role strings from older tokens/rows are migrated transparently at decode time
- Role is embedded in JWT claims; route guards (`require_platform_admin`, `require_client_admin_or_above`) run as FastAPI dependencies
- CLIENT_ADMIN cannot create or assign the PLATFORM_ADMIN role, and every tenant it touches is checked against its `tenant_ids`
- See `RBAC_MODEL.md` for the full model

**Reusable Insight:** RBAC should be enforced at the data access layer, not the UI layer. The UI can hide features, but the API must enforce access — including on *read* endpoints (an audit finding here: an admin GET missed its tenant-access check while the matching POST had one).

### Project-Level Authorization
- TENANT_USER access requires both the tenant match and project membership (`project_ids`)
- The `tenant_scope()` helper converts claims into the tenant filter every repository lookup takes; PLATFORM_ADMIN's cross-tenant access is an explicit `None`-scope path, never a default
- Authorization runs **before** cache reads, so a cache hit can never serve an unauthorized project

**Reusable Insight:** Authorization should be a filter, not a gate — and it must sit in front of every data source, including your cache.

## Encryption

### Password Hashing
- PBKDF2-SHA256 with 120,000 iterations
- Unique salt per password
- Timing-attack resistant comparison
- Minimum password length enforcement

**Reusable Insight:** PBKDF2 is a well-tested standard. Don't invent your own hashing algorithm. Use the crypto library, not a custom implementation.

### Secret Encryption (AES-256-GCM)
- Provider secrets (API keys, OAuth client secrets) encrypted at rest
- AES-256-GCM provides authenticated encryption; 12-byte random nonce per encryption, key derived via SHA-256 of `SECRET_ENCRYPTION_KEY`
- Decrypted secrets are never echoed through the API — connection reads return a `has_client_secret` boolean, never ciphertext or plaintext

**Reusable Insight:** Encrypt sensitive data at rest. Database breaches are common; encrypted data is useless to attackers. And treat "never returns the secret" as part of the API contract, not just the storage design.

### Key Management
- `SECRET_ENCRYPTION_KEY` is distinct from `JWT_SECRET`; production startup **fails** if either is a dev default, shorter than 32 chars, or if the two are identical
- No keys in code or configuration files
- Key rotation requires re-encryption of existing rows; the decrypt-with-old / re-encrypt-with-new migration path is documented next to the crypto helpers

**Reusable Insight:** Key management is the hardest part of encryption. Start simple (env vars) but enforce key separation and strength at startup, and write the rotation runbook before you need it.

## Network Security

### Security Headers
Applied by API middleware on every response:
- Strict-Transport-Security (HSTS, 1 year, includeSubDomains)
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Content-Security-Policy: `default-src 'self'`
- Referrer-Policy: strict-origin-when-cross-origin

**Reusable Insight:** Security headers are free protection. A reverse proxy is the tidiest place for them, but setting them in application middleware (as here) means they hold even when someone bypasses the proxy in a dev or misconfigured environment.

### CORS Configuration
- Explicit allowed origins from `CORS_ALLOWED_ORIGINS` (comma-separated, no wildcard)
- Allowed methods and headers restricted to what the frontend actually uses — not `*`
- Credentials allowed for authenticated requests

**Reusable Insight:** CORS is a browser security feature. Restrict methods and headers too, not just origins — every wildcard is attack surface if the origin check is ever mis-set.

### Rate Limiting
- `/auth/login`: 10/min per IP, **fails closed** when Redis is down
- Admin writes: 60/hour (env-configurable), fails closed
- Global API: 100/min, falls back to per-worker in-memory limiting when Redis is down
- Redis sliding window with 2s socket timeouts (a *hung* Redis without timeouts would block the middleware on every request — effectively a self-DoS)
- Client IP derived safely: `X-Forwarded-For` is only honored for a configured number of trusted proxy hops

**Reusable Insight:** Rate limiting prevents abuse — but decide the Redis-down behavior per tier (closed for auth, open for convenience), set socket timeouts on the limiter's own dependency, and never key on a spoofable header.

### Open-Redirect Prevention
The post-login `callbackUrl` is sanitized before `redirect()`: it must start with `/` and protocol-relative `//` values are rejected; anything else falls back to `/dashboard`.

**Reusable Insight:** Any user-influenced redirect target is a phishing vector. Allowlist same-origin paths; never pass raw query-string URLs to a redirect.

## Input Validation

### Pydantic Validation
- All request bodies validated against schemas — including admin endpoints (an audit finding replaced a raw `dict` body with a Pydantic model)
- Invalid requests return 422 with details
- Custom validators for business rules: password minimum length (8) on create/update/reset, role membership against the enum, `#RRGGBB` regex for brand color, tenant-existence and project–tenant-membership checks on user assignment
- Query-level inputs validated too: sort/direction allowlists, search length cap, cursor decode validation, filter JSON parsed into a typed model

**Reusable Insight:** Validate at the boundary — bodies, query params, cursors, everything. "It's an admin endpoint" is not an exemption; admin endpoints are exactly where raw-dict laziness creeps in.

### SQL Injection Prevention
- Parameterized queries throughout (asyncpg `$1`, psycopg `%s`)
- The only f-string SQL fragments interpolate allowlist-validated values (sort direction) or index placeholders — never user text

**Reusable Insight:** Parameterized queries are the primary defense. Where dynamic SQL is unavoidable (ORDER BY direction, column names), interpolate only values checked against a hardcoded allowlist.

### XSS Prevention
- React auto-escapes output
- `dangerouslySetInnerHTML` is used only for controlled `<style>`/bootstrap-script injection whose dynamic value (brand color) is validated server-side against a strict hex regex at the write path
- CSP headers as defense in depth
- localStorage carries only non-sensitive UI preferences (theme, sidebar state) — never tokens

**Reusable Insight:** React handles XSS prevention by default. When you must bypass it, make the injected value pass through server-side validation so the sink can only ever receive a known-safe shape.

## Audit and Logging

### Audit Trail
- Login/logout events logged
- Admin actions logged
- Data refresh events logged
- Failed authentication attempts logged

**Reusable Insight:** Log security-relevant events. You can't investigate what you didn't log.

### Sensitive Data Handling
- Passwords, tokens, and secrets never logged (verified by audit grep of all `logger`/`print` call sites)
- PII minimized in logs; Sentry runs with `send_default_pii=False`
- Error responses carry only a generic message plus a correlation ID — no stack traces
- The readiness probe reports `"error"` without exception text (connection errors can embed host/port/db/user)
- `to_public_dict` strips `hashed_password` and other internal fields from every user-facing response

**Reusable Insight:** Logs, error responses, health probes, and crash reporters are all exfiltration channels. Sweep every one of them — not just the logger — for secrets and PII.

## Beyond This Dashboard

Security patterns not (yet) used here that belong in the toolbox for the next system:

- **Refresh-token rotation:** the 1-hour single-token model forces hourly re-login or long-lived access tokens. The standard upgrade: short access token (5–15 min) + httpOnly refresh token that is *rotated on every use*, with reuse detection revoking the whole session family (catches stolen refresh tokens).
- **Asymmetric JWTs (RS256/EdDSA) + JWKS:** HS256 means every verifier holds the signing secret. With multiple services or third-party verifiers, sign with a private key and publish public keys at a JWKS endpoint with `kid`-based rotation.
- **Server-side sessions as the JWT alternative:** an opaque session ID in a cookie + Redis session store gives instant revocation and no claim-staleness, at the cost of a lookup per request. For a single first-party app, this is often *simpler* than JWT + blacklist.
- **MFA / WebAuthn:** TOTP is table stakes for admin accounts; WebAuthn/passkeys remove the phishable factor entirely. Prioritize for PLATFORM_ADMIN-class roles.
- **Argon2id for new systems:** memory-hard, GPU-resistant; OWASP's current first recommendation over PBKDF2.
- **Envelope encryption + KMS:** instead of one env-var key, encrypt each secret with a data key, and the data key with a KMS-held master key (AWS KMS, GCP KMS, Vault transit). Rotation becomes re-wrapping data keys, not re-encrypting every row.
- **CSP beyond `default-src 'self'`:** for apps with inline styles/scripts, nonce- or hash-based CSP (`script-src 'nonce-…'`) plus `frame-ancestors`, `object-src 'none'`, and CSP reporting endpoints.
- **CSRF hardening:** `SameSite=lax` covers most cases; for state-changing cross-site-exposed endpoints add double-submit tokens or origin-header verification (Next.js server actions do origin checking for you).
- **Account-level brute-force defense:** IP rate limiting misses distributed (botnet) credential stuffing; add per-account counters with progressive delays or lockout, plus breached-password checks (haveibeenpwned k-anonymity API) at registration/reset.
- **Dependency and supply-chain scanning:** `pip-audit`/`npm audit` in CI, lockfile pinning, and Dependabot/Renovate — the audit process here is manual today.
- **Tamper-evident audit logs:** hash-chained or append-only (WORM) audit trails for admin actions, if compliance ever requires proving logs weren't edited.
