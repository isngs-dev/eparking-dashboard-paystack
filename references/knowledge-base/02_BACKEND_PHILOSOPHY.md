# Backend Philosophy

## Core Principles

### 1. FastAPI as the Foundation
FastAPI provides automatic OpenAPI/Swagger documentation, Pydantic validation for request/response models, dependency injection for cross-cutting concerns, and async support for high-concurrency workloads.

**Reusable Insight:** Choose a framework that gives you validation, documentation, and dependency injection out of the box. These reduce boilerplate and enforce consistency.

### 2. Dependency Injection Pattern
FastAPI dependency injection is used for authentication claims extraction, repository instance provisioning, database session management, and tenant context propagation.

**Reusable Insight:** Use dependency injection for anything that is needed across multiple endpoints, has different implementations (dev vs prod), needs setup/teardown lifecycle, or carries request-scoped context.

### 3. Repository Pattern with Protocol
Define the contract via Protocol, implement for each backend, switch via environment variable. All methods require tenant-scoped credentials (AuthClaims).

**Reusable Insight:**
- Protocol defines the interface, not the implementation
- Switch implementations via environment variable
- All methods require tenant-scoped credentials
- No method should work without tenant context

### 4. Async-First Database Access
Using asyncpg directly (no ORM) gives full control over SQL queries, no ORM abstraction overhead, explicit transaction management, and better performance for read-heavy workloads.

**Reusable Insight:** For read-heavy dashboards and analytics, raw async SQL often outperforms ORMs. Use an ORM only when you need complex relationship management or write-heavy workflows.

### 5. Multi-Tenancy Enforcement
Tenant isolation is enforced at multiple layers: Request contains JWT with tenant claims, dependency extracts claims, repository methods require claims, SQL queries filter by tenant_id, response strips internal tenant fields (`to_client_visit_dict` / `to_public_dict`).

The role model is three-tier: **PLATFORM_ADMIN** (cross-tenant, explicit `tenant_scope(claims) is None` path), **CLIENT_ADMIN** (company-scoped to a `tenant_ids` list in the JWT), and **TENANT_USER** (a single `tenant_id` plus `project_ids`). The `tenant_scope()` helper translates claims into the allowed-tenants argument every repository lookup takes, and project lookups use the composite `(tenant_id, project_id)` key so two tenants sharing a project_id can never cross-leak.

**Key Rules:**
- Tenant ID is NEVER accepted from user input
- Tenant ID is established at ingestion time and is immutable
- Every repository method requires AuthClaims / an explicit tenant scope
- Client-facing responses strip internal tenant-scoped fields

**Reusable Insight:** Multi-tenancy is a data access concern, not an API concern. Enforce it where data is accessed, not where it is exposed.

### 6. Structured Logging
JSON structured logging with correlation ID per request, log levels (DEBUG, INFO, WARNING, ERROR), contextual fields (tenant_id, user_id, endpoint), and machine-parseable format for log aggregation.

**Reusable Insight:** Log in JSON format from day one. It costs nothing extra and makes debugging in production dramatically easier.

### 7. Settings Management
Configuration lives in a frozen `Settings` dataclass populated from environment variables in `load_settings()`, with development-safe defaults. In production, load-time validation rejects dev-default or short (<32 char) `JWT_SECRET` / `SECRET_ENCRYPTION_KEY`, rejects identical values for the two, and requires the postgres repository backend.

**Reusable Insight:** Fail fast on startup if required configuration is missing or weak. Don't discover missing config at runtime — and treat "secret still set to its dev default" as missing.

## Data Access Patterns

### Cache-Aside Pattern with Stale-While-Revalidate
Cache keys include tenant context (`t:{tenant_id}:p:{project_id}:...`). TTLs are tuned per endpoint. The hot endpoints use a **stale-while-revalidate (SWR)** envelope (`{"v": value, "soft": ts}`) with a soft TTL and a hard TTL: warm requests past the soft TTL are served the stale value instantly while exactly one background task (single-flight via Redis `SET NX` lock) refreshes it — no thundering herd on the database.

Bulk invalidation is **set-based, not SCAN-based**: every key written for a tenant is registered in a `t:{tenant_id}:keys` Redis SET, so invalidating a tenant after ingestion is O(that tenant's keys) instead of a full-keyspace scan.

**Reusable Insight:** Cache-aside is the simplest effective caching pattern; SWR + a single-flight lock is the cheap upgrade that removes both tail latency and cache stampedes. Track keys per invalidation scope in a SET — `SCAN` on a shared Redis punishes every tenant for one tenant's invalidation.

### Connection Pooling
- PgBouncer in transaction mode
- Pool size tuned to workload
- Connection timeout handling
- Graceful connection recovery

**Reusable Insight:** Always use connection pooling for PostgreSQL. PgBouncer in transaction mode is the sweet spot for most web applications.

## Background Processing

### Celery for Async Tasks
Celery handles scheduled data ingestion, manual refresh triggers, retry logic with exponential backoff, and task monitoring and logging.

**Reusable Insight:**
- Use Celery for anything that takes more than 1 second
- Configure retry policies for external API calls
- Monitor task queues for backlog
- Use Celery Beat for cron-like scheduling

### Task Design Principles
- Idempotent tasks (safe to retry)
- Atomic operations (all or nothing)
- Clear success/failure states
- Detailed logging for debugging

**Reusable Insight:** Design every background task as if it will be retried 3 times. Because it will be.

## Error Handling

### Custom Exception Hierarchy
AppException base class with NotFoundError (404), AuthorizationError (401/403), RateLimitError (429), ValidationError (422).

### Centralized Error Handler
Single middleware catches all exceptions and maps to appropriate HTTP status codes, includes correlation ID in response, logs full error details server-side, and returns user-friendly messages to clients.

**Reusable Insight:** Never let framework default error responses reach clients. Always wrap with your own error handler that includes correlation IDs and consistent formatting.

## Security Philosophy

### Defense in Depth
1. Network Level: Nginx security headers, CORS
2. Application Level: Rate limiting, input validation
3. Authentication Level: JWT with httpOnly cookies
4. Authorization Level: RBAC, tenant isolation
5. Data Level: AES encryption for secrets, PBKDF2 for passwords

**Reusable Insight:** Each layer should assume the layers above it have been compromised. Defense in depth means no single point of failure.

### Password Handling
- PBKDF2-SHA256 with 120,000 iterations, 16-byte random salt per password
- Timing-attack resistant comparison (`hmac.compare_digest`)
- Minimum 8-character length enforced by Pydantic `field_validator` on create, update, and reset
- Password reset via single-use, time-limited tokens — only the PBKDF2 hash of the token is stored, redemption always returns a generic response, a dummy hash verification equalizes timing for unknown emails, and the consuming UPDATE re-asserts `consumed_at IS NULL` so concurrent redeems cannot both succeed

**Reusable Insight:** Never roll your own crypto. Use well-tested primitives for hashing and encryption — and remember that reset flows leak through *behavior* (response text, status codes, timing), not just storage.

### Token Revocation
JWTs are stateless, so logout works via a Redis blacklist keyed on the token's `jti` claim, with TTL equal to the token's remaining lifetime. Redis clients for the blacklist are **pooled per process** (one client per URL, with 2s socket timeouts) — creating a client per request is a connection leak under load.

**Reusable Insight:** Any per-request external client construction (`redis.from_url`, new HTTP sessions) is a scalability bug waiting to surface. Create once, reuse, and always set socket timeouts so a hung dependency degrades instead of stalling the event loop.

### Secret Encryption
- AES-256-GCM for encrypting provider secrets (key derived via SHA-256, 12-byte random nonce per encryption, auth tag verified on decryption)
- `SECRET_ENCRYPTION_KEY` is a **separate** env var from `JWT_SECRET`; production startup validation rejects duplicates
- Decrypted secrets are never echoed back through the API (`get_provider_connection` returns a `has_client_secret` boolean)

**Reusable Insight:** Encrypt sensitive configuration at rest and keep encryption keys separate from signing keys — compromise of one must not compromise the other. Plan the key-rotation path (decrypt-with-old, re-encrypt-with-new) before you need it.

## Beyond This Dashboard

Backend patterns relevant to this file's topics that this system doesn't currently use:

- **ORM with escape hatches:** the no-ORM choice is right for a read-heavy dashboard, but for write-heavy domains, SQLAlchemy 2.0 (async) or SQLModel gives you the unit-of-work pattern, identity map, and relationship loading while still allowing raw SQL for hot reads. The real decision axis is *who owns transactions* — an explicit unit-of-work object beats scattering `BEGIN/COMMIT` either way.
- **Repository + Unit of Work:** this repo's Protocol covers reads and single-call mutations. When mutations span multiple aggregates (create user + assign projects + write audit row), a Unit of Work abstraction (one transaction, many repository calls) keeps atomicity out of route handlers.
- **Transactional outbox:** if the backend ever needs to emit events (webhooks, notifications) alongside DB writes, write the event to an `outbox` table in the same transaction and have a relay publish it — this removes the "DB committed but event lost" dual-write failure mode.
- **Read-through / write-through caching:** cache-aside makes callers own the cache; read-through libraries (or Postgres materialized views) push that ownership down. **Negative caching** (caching "not found" briefly) protects against repeated lookups of missing keys — relevant for public endpoints like `/auth/settings/public/{key}`.
- **Task queues beyond Celery:** arq or Dramatiq are lighter async-native options; Temporal adds durable, resumable workflows when a pipeline step must survive process crashes mid-run. Choose Celery when you want maturity + beat scheduling; choose Temporal when a "refresh" is really a multi-hour saga.
- **Structured concurrency for fan-out:** for endpoints that aggregate several repository calls, `asyncio.TaskGroup` (3.11+) gives parallel fetching with correct cancellation — the async analogue of the "parallelize everything" case study in the frontend guide.
- **Password hashing beyond PBKDF2:** Argon2id (memory-hard) is the current OWASP first choice; scrypt second. PBKDF2-SHA256 at 120k iterations remains acceptable (FIPS-friendly), but if you start a new system, Argon2id via `argon2-cffi` costs nothing extra.
