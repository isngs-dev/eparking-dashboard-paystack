# Infrastructure

> **Status note:** the repo currently ships the **development** infrastructure (docker-compose with PostgreSQL, PgBouncer, and Redis; frontend and backend run locally). The production topology described further down — app Dockerfiles, Nginx, backup container — is the *target* architecture and is not yet in the repository. Sections are marked accordingly.

## Container Architecture

### Docker Multi-Stage Builds (target — no Dockerfiles in repo yet)
Frontend and backend should use multi-stage builds:
- **Stage 1: Dependencies** - Install packages
- **Stage 2: Builder** - Compile/build application
- **Stage 3: Runner** - Minimal runtime image (Next.js `standalone` output for the frontend)

**Reusable Insight:** Multi-stage builds produce smaller images. The builder stage has all tools; the runner stage has only what's needed.

### Non-Root Containers (target)
- Backend and frontend run as non-root users
- File permissions set explicitly

**Reusable Insight:** Never run containers as root. If a container is compromised, root access gives the attacker full control.

### Health Checks (implemented for data services)
- Database: `pg_isready` (compose healthcheck)
- PgBouncer: `pg_isready` against port 6432, gated on Postgres being healthy first
- Redis: `redis-cli ping`
- Backend exposes `/healthz` (liveness) and `/readyz` (readiness with per-dependency checks) for container/orchestrator probes

**Reusable Insight:** Health checks enable orchestrators to detect and restart unhealthy containers. Define them for every service, and use `depends_on: condition: service_healthy` to order startup.

## Docker Compose

### Development Compose (implemented)
- PostgreSQL 16 (host 5433), PgBouncer (host 5434), Redis 7 (host 6380)
- Backend (uvicorn :8010), frontend (:3000), Celery worker/beat run locally with hot reload
- The dashboard schema SQL is mounted into `/docker-entrypoint-initdb.d/` and applied automatically on first volume init
- Named volumes for Postgres and Redis persistence

### Production Compose (target)
- Target: PostgreSQL, PgBouncer, Redis, Backend, Frontend, Celery Worker, Celery Beat, Nginx, Backup — all containerized with network isolation and volume persistence

**Reusable Insight:** Development and production should use the same infrastructure, just different scale. Docker Compose bridges the gap — and mounting your schema into initdb makes "fresh database" a one-command operation.

## Reverse Proxy (Nginx) (target)

### Path-Based Routing
- /api/*, /auth/*, /admin/*, /metrics, /healthz, /readyz -> Backend
- /* -> Frontend

### SSL Termination
- Nginx handles SSL/TLS; backend receives plain HTTP
- Certificate management via Let's Encrypt
- HSTS headers enforced

**Reusable Insight:** Nginx is the edge of your system. It handles SSL, routing, compression, and caching. Keep it simple and well-configured.

### Security Headers
Currently set by **application middleware** (HSTS, X-Frame-Options, X-Content-Type-Options, CSP, Referrer-Policy on every FastAPI response); duplicating them at Nginx once it exists is fine — headers in the app survive proxy misconfiguration, headers in the proxy cover non-app responses.

**Reusable Insight:** Centralize security headers where they cannot be bypassed. If there's any path around your proxy (dev, direct port access), the app is the safer layer.

## Database Infrastructure

### PostgreSQL + PgBouncer (implemented)
- PgBouncer in **transaction mode** in front of Postgres
- Sizing (compose): `MAX_CLIENT_CONN=400`, `DEFAULT_POOL_SIZE=20`, `MAX_DB_CONNECTIONS=90` — staying under Postgres's default `max_connections=100`
- Each uvicorn worker keeps a small asyncpg pool (min 2 / max 10, configurable); PgBouncer multiplexes them onto the shared server connections
- **Transaction-pooling caveat:** no session state survives across transactions (no SET/LISTEN/advisory locks/named prepared statements). The app connects with `statement_cache_size=0` when `DB_VIA_PGBOUNCER=1`
- An optional `READ_REPLICA_URL` is plumbed through settings for read scaling

**Reusable Insight:** PgBouncer in transaction mode is the sweet spot for web applications — but it changes application behavior. Disable prepared-statement caching and avoid session state, or you'll chase phantom bugs.

### Backup Strategy (target)
- Automated backups via pg_dump in a scheduled backup container
- Retention policy configurable; restore procedure documented

**Reusable Insight:** Backups are useless without tested restores. Test your restore procedure regularly.

## Observability

### Prometheus Metrics (implemented)
Exposed at `/metrics` via `prometheus_client`:
- Cache hits/misses per endpoint
- Ingestion duration histogram per tenant/status
- Active-tenants gauge, JWT-blacklist-size gauge

Request count/latency histograms and DB pool stats are natural next additions.

**Reusable Insight:** Metrics answer "what is happening." Logs answer "why it happened." You need both.

### Structured Logging
- JSON format
- Correlation IDs
- Contextual fields
- Log levels (DEBUG, INFO, WARNING, ERROR)

**Reusable Insight:** Structured logs are queryable. Plain text logs are not. Use JSON from day one.

### Sentry Integration (implemented, production-gated)
- Initialized only when `APP_ENV=production` and a DSN is set
- `send_default_pii=False` — no emails/IPs shipped to Sentry
- Separate trace sample rates for the API (0.1) and Celery workers (0.05, via `CeleryIntegration`)

**Reusable Insight:** Sentry catches errors you didn't know about. Set it up before you need it — with PII off by default and sampling tuned per workload so background jobs don't drown out user-facing traces.

## Deployment Strategy

### Environment Parity
- Dev: Docker Compose (PostgreSQL + Redis)
- Staging: Same as production, smaller scale
- Production: Full Docker Compose stack

**Reusable Insight:** Environment parity reduces "works on my machine" issues. Use the same infrastructure everywhere.

### Configuration Management
- Environment variables for all configuration (loaded via a frozen `Settings` dataclass + optional `.env` file)
- No secrets in code or config files
- Production startup validation fails fast on weak/dev-default/duplicate secrets

**Reusable Insight:** Configuration should be injectable. If you can't change it without rebuilding, it's not configuration.

### Zero-Downtime Deployments (target)
- Blue-green or rolling deployments
- Database migrations backward-compatible
- Health checks (`/readyz`) before traffic switch — the API is verified stateless (all shared state in Redis/Postgres), so no session affinity is needed and round-robin load balancing is safe
- Rollback capability

**Reusable Insight:** Deployments should be boring. If they're exciting, something is wrong. Statelessness is the prerequisite — audit every module-level variable for hidden per-instance state before you scale out.

## Beyond This Dashboard

Infrastructure patterns beyond this stack's needs today:

- **Blue-green vs canary vs rolling:** blue-green (two full environments, atomic switch, instant rollback) suits small stacks like this; **canary** (route 1–5% of traffic to the new version, watch error rates, then ramp) needs a smarter router but catches bad releases with minimal blast radius; **rolling** is the k8s default and the cheapest, but rollback is slower. Pick based on how fast you can *detect* a bad release, not how fast you can deploy one.
- **Kubernetes vs Compose vs managed PaaS:** Compose-on-a-VM is right up to roughly "a few services, one box, occasional deploys." The step past that is usually a managed PaaS (Fly.io, Render, Railway, ECS) — full k8s pays off only with many services, multiple teams, or strict autoscaling needs.
- **Infrastructure as Code:** Terraform/OpenTofu (or Pulumi if you prefer a real language) for anything cloud-hosted — the compose file is IaC for containers, but DNS, TLS, buckets, and databases deserve the same treatment.
- **PITR backups:** `pg_dump` gives point-in-time-of-dump only. **WAL archiving** with pgBackRest or WAL-G gives point-in-time recovery to any second, plus verified restore testing — the standard once data loss tolerance drops below "one day."
- **OpenTelemetry:** instrument once (traces + metrics + logs with shared context) and export anywhere; distributed traces across Next.js → FastAPI → Postgres/Redis make correlation IDs visual. The correlation-ID middleware here is the manual precursor.
- **SLOs and error budgets:** define target availability/latency per endpoint class and alert on budget burn rate, not raw error counts — this turns "is it bad enough to page?" into arithmetic.
- **Secrets managers:** env vars are fine until you need rotation, audit, or per-service scoping — then Vault, AWS Secrets Manager, or SOPS-encrypted files in git.
- **CDN & edge:** static assets and the Next.js layer benefit from a CDN (CloudFront/Cloudflare); tenant-private API data should stay uncached at the edge (cross-tenant cache leakage risk — same reason this system rejected CDN caching for data).
