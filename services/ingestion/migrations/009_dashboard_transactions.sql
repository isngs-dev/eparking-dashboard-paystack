-- 009_dashboard_transactions.sql
-- Sprint 2: silver layer, the physical denormalized table every API query
-- reads. Rebuilt from raw_transactions via a set-based transform keyed on
-- paystack_transaction_id (idempotent UPSERT) -- see
-- .claude/skills/transform-classification/SKILL.md.
--
-- Roughly 58% of the sample data is non-success, so the per-visual indexes
-- below are partial (WHERE status='success') to avoid needlessly large
-- unqualified indexes. Do not skip these.

CREATE TABLE IF NOT EXISTS eparking.dashboard_transactions (
    paystack_transaction_id        BIGINT PRIMARY KEY
        REFERENCES eparking.raw_transactions (paystack_transaction_id),
    reference                      TEXT NOT NULL,
    amount                         NUMERIC(12, 2) NOT NULL,

    fee_category_id                BIGINT REFERENCES eparking.fee_categories (id),
    fee_category_code              TEXT NOT NULL,
    revenue_stream                 eparking.revenue_stream_enum,
    vehicle_type                   TEXT,
    counts_as_entry                BOOLEAN NOT NULL,
    is_revenue                     BOOLEAN NOT NULL,
    is_provisional_class           BOOLEAN NOT NULL DEFAULT false,

    status                         TEXT,
    channel                        TEXT,

    terminal_id                    BIGINT REFERENCES eparking.pos_terminals (id),
    terminal_serial                TEXT,
    location_id                    BIGINT REFERENCES eparking.locations (id),
    location_name                  TEXT,

    paid_at                        TIMESTAMPTZ,
    transaction_date               DATE,
    transaction_hour                SMALLINT,
    day_of_week                    SMALLINT,
    iso_week                       SMALLINT,
    iso_year                       SMALLINT,
    month_start                    DATE,

    card_component_annual_count    INT NOT NULL DEFAULT 0,
    card_component_monthly_count   INT NOT NULL DEFAULT 0,
    card_component_annual_amount   NUMERIC(12, 2) NOT NULL DEFAULT 0,
    card_component_monthly_amount  NUMERIC(12, 2) NOT NULL DEFAULT 0,

    fees                           NUMERIC(12, 2),

    classified_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    classification_version         INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS ix_dtx_date_revenue_stream
    ON eparking.dashboard_transactions (transaction_date, revenue_stream)
    WHERE status = 'success' AND is_revenue;

CREATE INDEX IF NOT EXISTS ix_dtx_date_fee_category
    ON eparking.dashboard_transactions (transaction_date, fee_category_id)
    WHERE status = 'success';

CREATE INDEX IF NOT EXISTS ix_dtx_date_terminal
    ON eparking.dashboard_transactions (transaction_date, terminal_id)
    WHERE status = 'success';

CREATE INDEX IF NOT EXISTS ix_dtx_date_hour
    ON eparking.dashboard_transactions (transaction_date, transaction_hour)
    WHERE status = 'success';

CREATE INDEX IF NOT EXISTS ix_dtx_dow_date
    ON eparking.dashboard_transactions (day_of_week, transaction_date)
    WHERE status = 'success';

CREATE INDEX IF NOT EXISTS ix_dtx_status_date
    ON eparking.dashboard_transactions (status, transaction_date);

CREATE INDEX IF NOT EXISTS ix_dtx_classification_version_date
    ON eparking.dashboard_transactions (classification_version, transaction_date);
