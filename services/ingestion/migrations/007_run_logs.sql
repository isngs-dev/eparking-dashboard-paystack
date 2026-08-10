-- 007_run_logs.sql
-- Sprint 2: audit trail for ingestion / transform / reclassify runs.

CREATE TABLE IF NOT EXISTS eparking.run_logs (
    id              BIGSERIAL PRIMARY KEY,
    run_type        TEXT NOT NULL,
    status          TEXT NOT NULL,
    window_from     TIMESTAMPTZ,
    window_to       TIMESTAMPTZ,
    rows_fetched    INT,
    rows_upserted   INT,
    error_message   TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_run_logs_run_type_started_at
    ON eparking.run_logs (run_type, started_at);
