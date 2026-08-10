# System Design

## Architecture Overview

### Layered Architecture Pattern

The system follows a clear layered architecture with strict boundaries:

`
+--------------------------------------------------+
|                    Client Layer                  |
|  (Next.js App Router, React Server Components)   |
+--------------------------------------------------+
|               Provider Abstraction Layer         |
|  (Strategy Pattern: REST / Sample / Direct API)  |
+--------------------------------------------------+
|                 API Gateway Layer                |
|  (Nginx: SSL termination, path-based routing)    |
+--------------------------------------------------+
|              Backend Service Layer               |
|  (FastAPI: REST API, Auth, Admin, Health)        |
+--------------------------------------------------+
|              Repository Layer                    |
|  (Protocol: InMemory / Postgres implementations) |
+--------------------------------------------------+
|              Data Layer                          |
|  (PostgreSQL, Redis)                             |
+--------------------------------------------------+
`

### Key Design Principles

#### 1. Separation of Concerns
- **Frontend** handles presentation and user interaction only
- **Backend** handles business logic, data access, and security
- **Ingestion** runs as a separate process (Celery workers)
- **Database** is never accessed directly by the frontend

#### 2. Strategy Pattern for Data Sources
The provider abstraction allows swapping data sources without changing UI code:
- **REST API Provider** - Production: calls backend API
- **Sample Data Provider** - Development: static data, no backend needed
- **Direct API Provider** - Alternative: calls external API directly

**Reusable Insight:** Define interfaces (Protocols/TypeScript interfaces) at the boundary. Implementations can be swapped via environment configuration.

#### 3. Repository Pattern for Data Access
- Define a Protocol/interface for all data operations
- Implement for each storage backend (memory, PostgreSQL, etc.)
- Switch implementations via configuration
- All methods accept tenant context as a required parameter

**Reusable Insight:** The repository pattern decouples business logic from storage details. Use language-native interface mechanisms (Python Protocol, TypeScript interface).

#### 4. Multi-Tenancy as First-Class Concern
- Tenant ID is established at data ingestion time
- Tenant ID is embedded in authentication tokens
- Every data access requires tenant-scoped credentials
- Tenant ID is never accepted from user input
- Data isolation is enforced at the repository layer, not the API layer

**Reusable Insight:** Multi-tenancy should be baked into the data access layer, not bolted on at the API layer. The repository should reject any request without proper tenant context.

#### 5. Server-First Architecture
- Data fetching happens on the server (React Server Components)
- Form submissions handled by server actions
- Session state stored in httpOnly cookies (not localStorage)
- Client JavaScript is minimized to interactive components only

**Reusable Insight:** With modern frameworks supporting server components, push as much logic to the server as possible. This reduces bundle size, improves security, and simplifies state management.

#### 6. Graceful Degradation with Explicit Boundaries
- Redis unavailable -> the **global** rate-limit path falls back to per-worker in-memory limiting; auth and admin paths **fail closed** (request denied) so an outage can never become an auth-bypass window
- Redis unavailable -> caching is disabled; requests compute fresh (and still fail loudly on DB errors)
- Replica database unavailable -> fall back to primary
- **BUT:** Never silently fall back from live data to sample data

**Reusable Insight:** Define which fallbacks are acceptable (infrastructure) and which are not (data integrity or security). Fallbacks that weaken a security control should fail closed, not open. Document these boundaries clearly.

## Component Communication Patterns

### Synchronous Communication
- Frontend -> Backend: REST API over HTTPS
- Backend -> Database: Async SQL (asyncpg)
- Backend -> Redis: Sync/async depending on context

### Asynchronous Communication
- Celery workers process ingestion tasks
- Redis acts as message broker
- Celery Beat schedules periodic tasks

**Reusable Insight:** Use async processing for anything that:
- Takes longer than a request cycle
- Is not user-facing
- Can be retried on failure
- Benefits from batching

## Configuration Management

### Environment Variable Strategy
- All configuration via environment variables
- A frozen `Settings` dataclass loaded once at startup (`load_settings()`), with development-safe defaults
- Production runs a fail-fast validation pass: weak/dev-default `JWT_SECRET` or `SECRET_ENCRYPTION_KEY`, duplicate keys, or a non-postgres repository backend raise `ValueError` before the app serves traffic
- Different env vars for dev vs prod

**Reusable Insight:** Whatever the mechanism (a validated dataclass, Pydantic Settings, or a Zod schema), validate configuration at startup and fail fast. The critical part is the production gate — reject dev defaults, short secrets, and duplicate keys before serving a single request.

### Configuration Categories
| Category | Examples | Validation |
|----------|----------|------------|
| Database | Host, port, credentials, pool size | Required, format validated |
| Redis | Host, port, password | Optional, graceful fallback |
| Security | JWT secret, encryption key | Required, minimum length |
| Feature Flags | Repository type, data provider | Enum validation |

## Scalability Considerations

### Horizontal Scaling
- Stateless API servers (multiple instances behind Nginx)
- Stateless frontend (Next.js standalone)
- Redis shared state for rate limiting and caching
- PostgreSQL connection pooling via PgBouncer

### Vertical Scaling Points
- Database: Connection pool size, work_mem, shared_buffers
- Redis: Max memory, eviction policy
- Celery: Worker concurrency, prefetch multiplier

**Reusable Insight:** Design for horizontal scaling from day one. Even if you start with a single instance, the architecture should support adding instances without code changes.

## Error Handling Philosophy

### Layered Error Handling
1. **Repository Layer:** Converts DB errors to domain exceptions
2. **Service Layer:** Adds business context to errors
3. **API Layer:** Converts to HTTP responses with correlation IDs
4. **Frontend Layer:** Displays user-friendly messages

### Error Categories
- **NotFoundError** (404) - Resource doesn't exist
- **AuthorizationError** (401/403) - Auth or permission issue
- **RateLimitError** (429) - Too many requests
- **ValidationError** (422) - Invalid input
- **InternalServerError** (500) - Unexpected failure

**Reusable Insight:** Never expose internal error details to clients. Always include a correlation ID for debugging. Log the full error server-side. This extends to infrastructure probes — the readiness endpoint reports `"error"`/`"degraded"` without raw exception text, because connection-error strings can leak hosts, ports, and database names.

## Beyond This Dashboard

Patterns worth knowing when architecting other dashboards, even though this system deliberately doesn't use them:

### Alternative Multi-Tenancy Models
This system uses **row-level tenancy** (shared schema, `tenant_id` column on every row). The other two mainstream models:

| Model | Isolation | Cost/Ops | When to choose |
|---|---|---|---|
| Row-level (this system) | Logical only — enforced in code/queries | Cheapest; one schema to migrate | Many small tenants, uniform schema |
| Schema-per-tenant | Namespace isolation; per-tenant migrations possible | Migration fan-out (N schemas); connection-pool complexity | Tens–hundreds of tenants needing per-tenant customization |
| Database-per-tenant | Hard isolation; per-tenant backup/restore/PITR | Most expensive; N databases to operate | Regulated tenants, noisy-neighbor concerns, per-tenant residency |

A useful middle path with row-level tenancy is **PostgreSQL Row-Level Security (RLS)**: `CREATE POLICY ... USING (tenant_id = current_setting('app.tenant_id'))` moves enforcement from application code into the database itself, so a forgotten `WHERE tenant_id = $1` cannot leak data. Caveat: RLS interacts awkwardly with transaction-mode PgBouncer (session settings don't persist), which is exactly why this system enforces tenancy in the repository layer instead.

### Alternative System Shapes
- **Modular monolith vs microservices:** this system is effectively a two-service modular monolith (API + ingestion workers sharing a `services/common` core). That is the right default; split into true microservices only when teams — not code — need independent deploy cadence.
- **CQRS-lite:** dashboards are read-heavy. A dedicated read model (pre-aggregated tables or materialized views refreshed by the ingestion pipeline) often beats caching raw queries. This pairs naturally with the existing Celery pipeline: transform → load → refresh aggregates → invalidate cache.
- **Event-driven ingestion:** where the upstream supports webhooks or a change feed, an event-driven pipeline (queue + consumer, with an **outbox pattern** for exactly-once handoff) replaces polling on a beat schedule and cuts data staleness from hours to seconds.
- **BFF (Backend-for-Frontend):** the Next.js server layer here already acts as a lightweight BFF (RSC fetches + server actions in front of FastAPI). Naming the pattern helps: keep per-frontend shaping in the BFF, keep domain rules in the backend.

### Scaling Patterns Not Yet Needed Here
- **Read replicas with explicit routing** (the settings already carry `read_replica_url`) — route only tolerant-of-lag reads to the replica, never auth or read-after-write paths.
- **Cell-based architecture / sharding by tenant** — when a single Postgres can no longer hold all tenants, shard whole tenants to cells rather than splitting tables.
- **Queue-level tenant fairness** — per-tenant Celery queues or rate-limited dispatch stop one huge tenant's refresh from starving the others.
