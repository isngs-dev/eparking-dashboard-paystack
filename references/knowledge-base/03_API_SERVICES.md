# API Services

## REST API Design Philosophy

### Resource-Based URL Design
- URLs represent resources, not actions: /projects, /projects/ID/visits
- HTTP verbs convey intent: GET (read), POST (create/trigger), PATCH (update)
- Nested resources reflect relationships: /projects/ID/summary
- No verbs in URLs

**Reusable Insight:** RESTful URLs should be self-documenting. A developer should understand what an endpoint does by reading the URL and HTTP method alone.

### Keyset Pagination with Opaque Cursors
The visit list endpoint uses **keyset (seek) pagination**, not OFFSET: the cursor encodes the last row's `(visit_date, survey_id)` plus a direction, base64url-wrapped as an opaque token. The server peeks one extra row (`limit+1`) to derive `next_cursor`/`prev_cursor`. Sort column and direction are allowlisted (`_ALLOWED_SORT`/`_ALLOWED_DIR`), search length is capped, and filters are validated through a Pydantic model before touching SQL.

**Reusable Insight:** OFFSET pagination degrades linearly with depth and skips/duplicates rows under concurrent writes. Keyset pagination is O(1) per page and stable. Keep cursors opaque so clients can't construct them — and validate them on decode, since they're still user input.

### Pydantic Request/Response Models
Every endpoint uses Pydantic models for request validation (automatic 422 on invalid input), response serialization (consistent output shape), API documentation (auto-generated OpenAPI schema), and type safety across the codebase.

**Reusable Insight:** Define your API contract in code, not in documentation. Pydantic models serve as both validation and documentation.

### Dependency Injection for Cross-Cutting Concerns
FastAPI dependencies handle authentication (extract and validate JWT), authorization (check role and permissions), repository provisioning (select implementation), and database session management.

**Reusable Insight:** Dependencies are the ideal place for cross-cutting concerns. They run before the endpoint handler and can short-circuit the request.

## Caching Strategy

### Stale-While-Revalidate (SWR) on Top of Cache-Aside
The hot read endpoints use `get_swr`: values are stored in an envelope `{"v": value, "soft": ts}` with a **soft TTL** (freshness) and a **hard TTL** (Redis expiry). A warm request past the soft TTL is answered instantly from the stale value while a single background task refreshes the entry — a Redis `SET NX` lock (30s) guarantees single-flight so a burst of stale hits cannot stampede the database. A cold miss blocks once and propagates DB errors (no silent empty fallback).

**Authorization runs before any cache read** — a cache hit can never serve a project the caller isn't allowed to see.

### Cache Key Design
- Tenant-namespaced: `t:{tenant_id}:p:{project_id}:summary`
- Parameterized pages hash their query shape: `t:{tenant}:p:{project}:visits:{sha256(cursor|limit|dir|search|filters)[:16]}`
- Keys are keyed by the **project's own tenant** (not the caller's, which is null for cross-tenant admins) so tenant-scoped invalidation still matches
- Every write also registers the key in a `t:{tenant_id}:keys` SET for O(tenant-keys) bulk invalidation — no keyspace SCAN

### TTL Strategy (as implemented)
| Data Type | Soft TTL | Hard TTL | Rationale |
|-----------|----------|----------|-----------|
| Project summary | 5 minutes | 15 minutes | Changes only on ingestion, high read volume |
| Paginated visit pages | 2 minutes | 10 minutes | More dynamic, many key variants |
| Legacy full visit list | 2 minutes (plain TTL) | — | Transitional endpoint, hard-capped at 5000 rows |

**Reusable Insight:** TTLs should reflect data volatility. With SWR, split "how stale may a user see" (soft) from "how long may Redis hold it" (hard) — the gap between them is your latency shield.

### Cache Invalidation
- Set-based tenant-wide invalidation after ingestion completes (`invalidate_tenant` deletes every tracked key)
- Never invalidate on read paths
- The tracking SET carries its own 24h TTL as a self-healing bound

**Reusable Insight:** Cache invalidation is harder than caching. Keep invalidation logic close to the mutation point, and make the invalidation scope (here: a tenant) an explicit, cheap operation rather than a pattern scan.

## Rate Limiting

### Multi-Tier Rate Limiting
| Tier | Limit | Window | Redis down? | Purpose |
|------|-------|--------|-------------|---------|
| `/auth/login` | 10 requests | 1 minute | **Fail closed** (deny) | Prevent brute force |
| Admin writes (POST/PATCH/DELETE under `/admin/`) | 60 (env-configurable) | 1 hour | **Fail closed** | Prevent misuse |
| Global API | 100 requests | 1 minute | Fall back to per-worker in-memory | Prevent abuse |

### Implementation Strategy
- Redis sorted-set **sliding window** (ZREMRANGEBYSCORE + ZADD + ZCARD in a pipeline), one shared client per process with 2s socket timeouts
- A sentinel distinguishes "Redis down" from "limit exceeded" so the failure policy can differ per tier
- In-memory fallback only for the non-sensitive global path (documented caveat: N workers ⇒ effective limit N × limit)
- `Retry-After` header on 429 responses

**Reusable Insight:** Rate limiting is a security concern, not a performance concern — and the failure mode matters as much as the algorithm. Auth-protecting limiters must fail closed; convenience limiters may fail open.

### Rate Limit Key Design
- Keys are per client IP; when behind a reverse proxy, `TRUSTED_PROXY_COUNT` controls which `X-Forwarded-For` entry is trusted (defaulting to the socket peer to prevent header spoofing)
- Identity-based keying (user ID) is the natural next step for authenticated endpoints

**Reusable Insight:** Rate limit by identity when possible, by IP when not — and never trust `X-Forwarded-For` blindly; count your trusted proxy hops explicitly.

## Error Response Design

### Consistent Error Format
Error responses include error code (UPPER_SNAKE_CASE), user-friendly message, and correlation_id for debugging.

### Error Code Convention
- UPPER_SNAKE_CASE for machine parsing
- Stable across API versions
- Documented in API specification
- Mapped to HTTP status codes

**Reusable Insight:** Error codes are part of your API contract. Change them as carefully as you change endpoint URLs.

### Correlation ID Propagation
- Generated at request entry (Nginx or middleware)
- Propagated through all service layers
- Included in all log entries
- Returned in error responses

**Reusable Insight:** Correlation IDs are the single most useful debugging tool in distributed systems. Implement them from day one.

## Health and Readiness Endpoints

### /healthz
- Returns 200 if the service is running
- No dependencies checked
- Used by load balancers for liveness probes

### /readyz
- Returns per-dependency checks (`database`, `redis`) plus an overall `ok`/`degraded` status
- Database check goes **through the shared connection pool**, never a fresh connection — 100 concurrent orchestrator probes opening fresh connections is itself a connection-exhaustion risk
- Failures report only `"error"`; the raw exception text (which can contain host/port/db names) is logged server-side, never returned

### /metrics
- Prometheus metrics endpoint (`prometheus_client`)
- Implemented: cache hits/misses per endpoint, ingestion duration histogram per tenant/status, active-tenants gauge, JWT blacklist size gauge

**Reusable Insight:** Health and readiness are different. Liveness means the process is running; readiness means it can serve traffic. Separate them — and treat probe endpoints as unauthenticated surface area: no internals in their responses.

## Beyond This Dashboard

API-layer techniques not used in this system but worth reaching for elsewhere:

- **Idempotency keys for unsafe methods:** accept an `Idempotency-Key` header on POST endpoints (Stripe-style), store the first response keyed by it, and replay it on retries. Essential once clients auto-retry mutations over flaky networks.
- **Conditional requests (ETag / If-None-Match):** for summary-style endpoints, hashing the response into an ETag lets clients revalidate for free — a 304 costs no body transfer and composes with server-side caching.
- **API versioning strategy:** none is needed yet because frontend and backend deploy together. The moment third parties integrate, pick one deliberately: URL versioning (`/v1/...`, simplest), header versioning, or additive-only evolution with deprecation headers (`Sunset`, `Deprecation`).
- **Alternative rate-limit algorithms:** sliding-window ZSETs are accurate but O(log n) per request and memory-heavy under attack. **GCRA** (generic cell rate algorithm, as in `redis-cell`) and **token bucket** give O(1) checks with burst allowances; fixed-window counters are the cheapest when precision doesn't matter.
- **Request coalescing at the API layer:** the SWR single-flight lock dedupes *cache refreshes*; frameworks like dataloader-style batching dedupe *within one request* when a page fans out to many identical sub-fetches.
- **Problem Details (RFC 9457):** a standardized error body (`type`, `title`, `status`, `detail`, `instance`) instead of a bespoke shape — worth adopting for public APIs so generic clients can parse errors.
- **Contract-first tooling:** the auto-generated OpenAPI schema can drive typed frontend clients (openapi-typescript, orval) and contract tests (Schemathesis fuzzes every endpoint against its own schema) — closing the gap between the Pydantic models and the TypeScript types that mirror them by hand today.
- **GraphQL / RPC tradeoff:** GraphQL earns its complexity when many differently-shaped clients consume the same graph; a single first-party dashboard is exactly the case where REST + purpose-built endpoints stays simpler.
