# Backend Components

## Database and Scalability

- Database should handle 1000 users
- Optimised queries (keyset pagination, LIMIT caps — no unbounded reads)
- Proper indexing (composite keys on tenant_id + entity id)
- Less changes when data grows from 100 to 100k
- Connection pooling (PgBouncer transaction mode; per-worker asyncpg pools)

## Security

- Passwords should be stored securely (PBKDF2-SHA256, 120k iterations; min length enforced)
- HTTPS, TLS configuration and certificate rotation
- Authentication, authorization, roles, and permissions (JWT + 3-tier RBAC)
- Multi-tenancy and data isolation (tenant_id from verified claims only)
- PII handling, data retention and deletion policies
- Session management and token expiry (1h JWT + Redis JTI revocation on logout)
- Regulatory compliance (GDPR, HIPAA)
- API keys to be protected (AES-256-GCM at rest, never echoed back)
- Secrets management (key separation validated at startup)
- Validate user input
    - Input sanitisation and injection prevention (Pydantic at the edge; parameterized SQL)
- Rate limiting and abuse prevention (fail-closed on auth/admin paths)
- Dependency scanning and vulnerability patching
- Immune to bots, scrapers and attackers

## Performance

- Fast page load
- Optimised API
- Cache frequently accessed data
    - Cache strategy and invalidation (SWR soft/hard TTL; set-based tenant invalidation)
- How to handle traffic spikes (single-flight refresh locks prevent stampedes)
- RTO and RPO
- Accessibility

## Monitoring and Logs

- Logging is important (structured JSON + correlation IDs)
- Audit trails and tamper-evident logging
- Error tracking (Sentry, PII off, sampled)
- Performance monitoring (Prometheus /metrics; ingestion run logs)

## Recovery

- Able to roll back a bad deployment
- Disaster recovery plan
- Circuit breakers and fallback behavior (socket timeouts on every Redis client; explicit fail-open/fail-closed policy per path)
- Concurrency handling and race condition prevention (atomic token consumption; idempotent UPSERTs)

## Testing

- Unit, integration and end-to-end testing
- Regression testing (pin every fixed security bug with a test)
- Load and stress testing
- Chaos engineering and resilience testing
- Test coverage thresholds enforced in CI
- Code review process and standards
- Retry logic with backoff and idempotency (acks_late + prefetch 1 for workers)

## Beyond This Dashboard

Checklist items worth adding for larger systems, not covered above:

- SLOs and error budgets — define acceptable latency/availability per endpoint class; alert on budget burn, not raw errors
- Capacity planning — know your headroom (connections, Redis memory, worker throughput) before the spike
- Feature flags — decouple deploy from release; kill switches for risky paths
- Graceful shutdown and connection draining — finish in-flight requests before a pod/process dies
- Blue-green or canary release strategy with automated rollback triggers
- Data retention jobs — automated purging/archival, not just a written policy
- Backpressure — queue depth limits and load shedding when a dependency slows
- Zero-trust service-to-service auth (mTLS or signed service tokens) once there is more than one backend
- Idempotency keys on client-facing mutations, not only inside the pipeline
- Runbooks — one page per failure mode (Redis down, Postgres failover, queue backlog), written before the incident
