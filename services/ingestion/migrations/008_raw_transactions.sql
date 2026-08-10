-- 008_raw_transactions.sql
-- Sprint 2: bronze layer. Verbatim Paystack data, never queried by the
-- dashboard directly -- exists so classification rules can be replayed
-- without re-hitting the Paystack API. No settlement_date column:
-- settlement is explicitly out of scope (see CLAUDE.md).

CREATE TABLE IF NOT EXISTS eparking.raw_transactions (
    paystack_transaction_id    BIGINT PRIMARY KEY,
    reference                  TEXT NOT NULL,
    amount                     NUMERIC(12, 2) NOT NULL,
    amount_kobo                BIGINT,
    currency                   TEXT,
    status                     TEXT,
    channel                    TEXT,
    gateway_response           TEXT,
    source                     TEXT,
    source_identifier          TEXT,
    customer_email             TEXT,
    customer_code               TEXT,
    card_type                  TEXT,
    card_bank                  TEXT,
    card_last4                 TEXT,
    paid_at                    TIMESTAMPTZ,
    fees                       NUMERIC(12, 2),
    raw_payload                JSONB,
    ingest_source               TEXT,
    ingest_run_id               BIGINT REFERENCES eparking.run_logs (id),
    ingested_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_hash                    TEXT
);

-- Minimal indexes only, per Sprint 2 spec.
CREATE INDEX IF NOT EXISTS ix_raw_transactions_paid_at
    ON eparking.raw_transactions (paid_at);

CREATE INDEX IF NOT EXISTS ix_raw_transactions_ingest_run_id
    ON eparking.raw_transactions (ingest_run_id);
