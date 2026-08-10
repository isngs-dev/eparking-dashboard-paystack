# Data Pipeline

## Ingestion Architecture

### Pipeline Stages
```
External API -> OAuth2 Client -> Extractor -> Transform -> Persistence -> PostgreSQL
                                    |
                                    v
                              Celery Worker (async)
```

### Stage 1: OAuth2 Client
- Handles authentication with external API
- Token refresh and management
- Rate limit awareness
- Retry logic with exponential backoff

**Reusable Insight:** External API clients should be resilient. Handle token expiration, rate limits, and network errors gracefully.

### Stage 2: Extractor
- Orchestrates resource pulls
- Manages pagination
- Handles partial failures
- Logs extraction metrics

**Reusable Insight:** Extraction should be idempotent. Running it twice should produce the same result as running it once.

### Stage 3: Transform
- Converts external API format to normalized schema
- Validates data integrity
- Handles missing or malformed data
- Enriches data with tenant context

**Reusable Insight:** Transformation is where data quality is enforced. Validate early, fail fast, log everything.

### Stage 4: Persistence
- UPSERT pattern (INSERT ... ON CONFLICT)
- Batch operations for performance
- Transaction boundaries for consistency
- Audit trail via run logs

**Reusable Insight:** UPSERT is the key to idempotent data loading. If the same data arrives twice, the second load is a no-op.

## Celery Task Design

### Task Categories
- **Scheduled tasks:** Run on a schedule (every 6 hours)
- **Manual tasks:** Triggered by user action
- **Retry tasks:** Failed tasks with retry logic

### Celery Beat Schedule
```python
# Interval-based, env-configurable (SCHEDULED_REFRESH_INTERVAL_MINUTES, default 360)
celery_app.conf.beat_schedule = {
    "scheduled-tenant-refresh": {
        "task": "services.ingestion.tasks.scheduled_refresh_all_tenants",
        "schedule": scheduled_refresh_interval_minutes * 60.0,
    },
}
```

The beat task fans out one `run_tenant_refresh` task per active tenant. A per-tenant Redis flag (`scheduled_refresh:{tenant_id}`, admin-toggleable via the API) lets operators pause scheduled refresh for a single tenant without touching the schedule.

**Reusable Insight:** Use Celery Beat for cron-like scheduling, fan out to one task per unit of work (tenant), and give operators a per-unit kill switch — pausing one tenant should never require redeploying the schedule.

### Retry Strategy
As implemented: `max_retries=3`, exponential backoff (`countdown=60 * 2^retries`), `acks_late=True` with `worker_prefetch_multiplier=1` so a crashed worker's task is redelivered. On final failure the run log records the error and a truncated trace.

Worth adding at larger scale (not implemented here): jitter on the backoff, a dead-letter queue for permanent failures, and alerting on repeated failures.

**Reusable Insight:** Every external call should have a retry policy. Network failures are inevitable; your pipeline should handle them. `acks_late` + prefetch 1 is the Celery incantation that makes "worker died mid-task" survivable.

## Data Quality

### Validation Rules
- Required fields must be present
- Data types must match schema
- Referential integrity (foreign keys)
- Business rule validation

### Error Handling
- Invalid rows are logged, not silently dropped
- Partial failures are reported
- Run logs track success/failure per resource
- Alerts on data quality issues

**Reusable Insight:** Data quality is not optional. Log every validation failure. Make it easy to diagnose and fix data issues.

## Idempotency

### UPSERT Pattern
```sql
INSERT INTO visits (...)
VALUES (...)
ON CONFLICT (tenant_id, visit_id)
DO UPDATE SET ...
```

### Idempotency Keys
- External API IDs as natural keys
- Composite keys for uniqueness
- Hash-based keys for complex data

**Reusable Insight:** Idempotency is the foundation of reliable data pipelines. Design every operation to be safe to retry.

## Monitoring

### Metrics
- Rows ingested per run (recorded in `dashboard.run_logs` with per-resource details)
- Prometheus `ingestion_duration_seconds` histogram labeled by tenant and status
- `last_sync_at` on the provider connection for freshness checks

### Logging
- Structured JSON logs
- A unique `run_id` per execution, persisted in the run log with status, timings, rows pulled, and error message/trace on failure
- Sentry (production only) with a reduced trace sample rate for Celery and `send_default_pii=False`

**Reusable Insight:** Monitor what matters: ingestion lag, error rates, and data freshness. Persist a run log row per execution — it doubles as the operator-facing sync history in the admin UI.

### Post-Load Cache Invalidation
After a successful load, the task invalidates the tenant's entire API cache using the set-based `t:{tenant_id}:keys` tracking SET (no keyspace SCAN), through a shared per-worker Redis client with socket timeouts.

**Reusable Insight:** The pipeline owns cache invalidation — the moment data changes is the only place that reliably knows it changed.

## Schema Management

### SQL-Based Schema
- Explicit schema definition (`dashboard_schema.sql`, all `CREATE ... IF NOT EXISTS`, auto-applied on first Postgres volume init)
- Incremental changes as plain numbered SQL files in `services/ingestion/migrations/` (e.g. `001_add_companies.sql`) — no migration framework
- Backward-compatible changes preferred

**Reusable Insight:** Schema changes should be backward-compatible. Add columns, don't remove them. Plain SQL migrations work fine at small scale; adopt a tracked migration tool (Alembic, sqitch, dbmate) once you need applied-version bookkeeping across multiple environments.

## Beyond This Dashboard

Pipeline techniques beyond this poll-transform-upsert design:

- **Incremental extraction with watermarks:** instead of re-pulling everything per run, persist a high-water mark (`updated_at` or an API change token) per resource and pull only deltas. Pair with the UPSERT loader unchanged. This is the single biggest cost/latency win when the upstream supports it.
- **Change Data Capture (CDC):** when you own the source database, Debezium-style CDC (logical replication → queue → consumer) replaces polling entirely and gets staleness to seconds.
- **ELT with a transform layer:** at analytics scale, land raw data first (append-only "bronze" tables) and transform inside the warehouse with dbt — you gain replayability (re-run transforms without re-extracting) and an audit trail of every raw payload.
- **Data contracts and expectations:** codify "what valid data looks like" with Great Expectations / Pandera-style assertions (row counts within tolerance, null-rate ceilings, enum membership) and fail the run — not just log — on contract breach. This dashboard's workbook-parity test is a hand-rolled version of the same idea.
- **Backfill as a first-class operation:** design tasks to accept an explicit date/ID range so historical re-loads are a parameterized run, not a code change. Idempotent UPSERTs make backfills safe; the missing piece is usually the parameterization.
- **Orchestrators beyond Celery Beat:** Airflow/Dagster/Prefect add dependency graphs between pipeline steps, per-step retries, and backfill UIs. Worth it when the pipeline becomes a DAG (extract → transform → aggregate → publish) rather than one linear task.
- **Poison-pill handling:** a dead-letter queue plus a quarantine table for rows that repeatedly fail transformation keeps one malformed record from blocking a whole tenant's refresh.
