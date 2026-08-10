# Architectural Decision Records

## ADR-001: Server-First Architecture

### Context
Modern web frameworks support server-side rendering and server components. The question was whether to build a traditional SPA or a server-first application.

### Decision
Use Next.js App Router with React Server Components as the default. Client components only for interactivity.

### Consequences
**Positive:**
- Reduced client JavaScript bundle
- Simpler state management (no Redux needed)
- Better SEO and initial load performance
- Server-side security (no secrets in client)

**Negative:**
- Server infrastructure required
- More complex deployment
- Learning curve for RSC patterns

## ADR-002: Repository Pattern for Data Access

### Context
How should the application access data? Direct SQL in route handlers? An ORM? A repository abstraction?

### Decision
Use the Repository pattern with Protocol interface. Two implementations: InMemory (dev) and Postgres (prod). Switch via environment variable.

### Consequences
**Positive:**
- Easy to test with InMemory implementation
- Development without database
- Clear separation of concerns
- Easy to add new storage backends

**Negative:**
- More code to maintain
- Protocol must be kept in sync with implementations
- Slight performance overhead

## ADR-003: Multi-Tenancy at Data Access Layer

### Context
How should multi-tenancy be enforced? At the API layer? At the UI layer? At the data access layer?

### Decision
Enforce multi-tenancy at the repository layer. Every method requires AuthClaims with tenant_id. Tenant ID is never accepted from user input.

### Consequences
**Positive:**
- Impossible to access another tenant's data
- API layer doesn't need tenant checks
- Clear security boundary

**Negative:**
- Every method must accept claims
- Slightly more complex repository interface
- Testing requires mock claims

## ADR-004: JWT in httpOnly Cookies

### Context
Where should JWT tokens be stored? localStorage? sessionStorage? httpOnly cookies?

### Decision
Store JWT tokens in httpOnly cookies with Secure and SameSite flags.

### Consequences
**Positive:**
- XSS-resistant (JavaScript can't access cookie)
- Automatic with requests
- Secure flag prevents transmission over HTTP
- SameSite prevents CSRF

**Negative:**
- CSRF protection still needed (handled by Next.js)
- Cookie size limits
- Cross-origin requests more complex

## ADR-005: No ORM for Database Access

### Context
Should we use an ORM (SQLAlchemy, Prisma) or raw SQL for database access?

### Decision
Use raw async SQL (asyncpg) for read-heavy operations. Schema and migrations are plain SQL files (`dashboard_schema.sql` + numbered files in `services/ingestion/migrations/`) — no ORM or migration framework.

### Consequences
**Positive:**
- Full control over queries
- Better performance for reads
- No ORM abstraction overhead
- Explicit transaction management

**Negative:**
- More SQL to write and maintain
- No automatic relationship management
- Migration tooling separate from query code

## ADR-006: Celery for Background Processing

### Context
How should background tasks be handled? In-process threads? A task queue? Serverless functions?

### Decision
Use Celery with Redis broker for background tasks. Celery Beat for scheduled tasks.

### Consequences
**Positive:**
- Mature, well-tested library
- Retry logic built in
- Monitoring and management tools
- Scales horizontally

**Negative:**
- Additional infrastructure (Redis, Celery workers)
- More complex deployment
- Debugging distributed tasks harder

## ADR-007: shadcn/ui for Component Library

### Context
Should we use a component library (MUI, Chakra) or build our own? Or use shadcn/ui?

### Decision
Use shadcn/ui for UI primitives. Copy-paste pattern gives full control over component code.

### Consequences
**Positive:**
- Accessible by default (Radix UI)
- Fully customizable
- No library lock-in
- Tailwind CSS integration

**Negative:**
- More code to maintain
- Updates are manual
- No automatic component upgrades

## ADR-008: PgBouncer for Connection Pooling

### Context
How should PostgreSQL connections be managed? Direct connections? A connection pooler?

### Decision
Use PgBouncer in transaction mode for connection pooling. Current sizing: `MAX_CLIENT_CONN=400`, `DEFAULT_POOL_SIZE=20`, `MAX_DB_CONNECTIONS=90` (under Postgres's default 100).

### Consequences
**Positive:**
- Efficient connection multiplexing
- Protects database from connection storms
- Battle-tested

**Negative:**
- Additional infrastructure
- Configuration complexity
- **Not** fully transparent: no session state across transactions; the app must connect with `statement_cache_size=0` (gated by `DB_VIA_PGBOUNCER=1`)

## ADR-009: AES-256-GCM for Secret Encryption

### Context
How should provider secrets (API keys, OAuth tokens) be stored? Plain text? Encrypted? Hashed?

### Decision
Encrypt secrets at rest using AES-256-GCM. Key stored in environment variable.

### Consequences
**Positive:**
- Secrets useless if database is breached
- Authenticated encryption (tamper detection)
- Industry standard algorithm

**Negative:**
- Key management complexity
- Performance overhead (minimal)
- Key rotation requires re-encryption

## ADR-010: No Silent Fallbacks

### Context
Should the application fall back from live data to sample data when the backend is unavailable?

### Decision
Never silently fall back from live data to sample data. Explicit failures are better than hidden degradation.

### Consequences
**Positive:**
- Users know when something is wrong
- No data inconsistency
- Easier debugging

**Negative:**
- Worse user experience during outages
- Requires explicit error handling
- No graceful degradation for data

## ADR-011: Three-Tier RBAC with Company Scoping

### Context
The original two-role model (ADMIN / CLIENT) could not express "an agency admin who manages several tenants but not the whole platform."

### Decision
Adopt three roles: PLATFORM_ADMIN (global), CLIENT_ADMIN (scoped to a company's `tenant_ids`), TENANT_USER (one tenant + assigned `project_ids`). Companies own tenants. Legacy role strings are migrated transparently at JWT decode time (`ADMIN → PLATFORM_ADMIN`, `CLIENT → TENANT_USER`).

### Consequences
**Positive:**
- Delegated administration without platform-wide power
- Cross-tenant reads become an explicit, auditable code path (`tenant_scope() is None`)
- Old tokens and DB rows keep working during migration

**Negative:**
- Every admin endpoint needs a per-tenant access assertion, not just a role check
- Claims are larger (`company_id`, `tenant_ids`) and role-specific claim validation is required at decode

## ADR-012: Redis SWR Cache with Set-Based Invalidation

### Context
Dashboard reads are expensive and tolerate minutes-stale data; naive TTL caching produced either stale-forever or thundering-herd behavior, and SCAN-based invalidation punished all tenants on a shared Redis.

### Decision
Cache hot endpoints in Redis with a stale-while-revalidate envelope (soft TTL + hard TTL, single-flight refresh lock). Track every key per tenant in a `t:{tenant}:keys` SET; ingestion invalidates by deleting the set's members.

### Consequences
**Positive:**
- Warm requests never block on the database; stampedes are structurally impossible
- Invalidation is O(tenant's keys) and exact
- Multi-instance safe (all state in Redis)

**Negative:**
- Envelope format is bespoke (legacy/foreign values are treated as misses)
- Two TTLs per endpoint to tune instead of one
- Background refresh tasks must swallow-and-log errors (they run detached from any request)

## ADR-013: Fail-Closed Rate Limiting on Sensitive Paths

### Context
When Redis is down, an in-memory fallback rate limiter silently weakens to per-worker limits — acceptable for general traffic, unacceptable as a brute-force window on login.

### Decision
Auth and admin paths deny requests when Redis is unavailable (fail closed); only the global path falls back to per-worker in-memory limiting. The limiter distinguishes "Redis down" from "limit exceeded" via a sentinel so the policy can differ per tier.

### Consequences
**Positive:**
- A Redis outage can never become an auth-bypass or admin-abuse window
- Failure policy is explicit and per-tier

**Negative:**
- Redis availability now gates login availability (mitigated by 2s socket timeouts and clear 429 messaging)

## Beyond This Dashboard

On the practice of decision records, and the roads not taken:

- **Keep ADRs immutable and superseding.** Don't edit a decision that changed — write a new ADR that marks the old one "Superseded by ADR-NNN" (as ADR-011 effectively supersedes the two-role assumption baked into ADR-003's era). The history *is* the value.
- **Record the rejected options.** The strongest ADR sections above are the Negatives; the next improvement is a short "Options considered" list with one-line reasons for rejection — it stops the same debate from re-running in six months.
- **Common alternative decisions** for each slot in this stack, so future systems choose consciously: session cookies + Redis instead of JWT (instant revocation, simpler); schema-per-tenant or Postgres RLS instead of application-enforced row tenancy; SQLAlchemy 2.0 async instead of raw asyncpg (when writes get complex); Dramatiq/arq/Temporal instead of Celery; TanStack Query layered onto RSC when client-side interactivity grows; MUI/Chakra instead of shadcn/ui when you'd rather receive upgrades than own code.
- **Lightweight formats scale better.** MADR (Markdown ADR) template — Context / Decision / Status / Consequences — in the repo, reviewed in PRs like code. Tooling (adr-tools, log4brains) is optional; the discipline isn't.
- **Tie ADRs to enforcement.** The best decisions here are backed by mechanisms (startup validation for ADR-009's key separation, `.claude/rules/*` for ADR-010). An ADR with no test, lint rule, or startup check enforcing it is a wish, not a decision.
