-- 010_daily_revenue.sql
-- Sprint 2: gold rollup, day-grain, mirrors the accounts team's Excel
-- report almost column-for-column. Split basis is gross (confirmed, see
-- Sprint 0 overview) -- aicl_amount/gsds_amount compute off total_collection.

CREATE TABLE IF NOT EXISTS eparking.daily_revenue (
    revenue_date                DATE PRIMARY KEY,

    ticket_count                 INT NOT NULL DEFAULT 0,
    ticket_amount                 NUMERIC(14, 2) NOT NULL DEFAULT 0,
    ticket_amount_by_vehicle      JSONB,

    card_annual_count             INT NOT NULL DEFAULT 0,
    card_annual_amount            NUMERIC(14, 2) NOT NULL DEFAULT 0,
    card_monthly_count            INT NOT NULL DEFAULT 0,
    card_monthly_amount           NUMERIC(14, 2) NOT NULL DEFAULT 0,
    card_total_amount             NUMERIC(14, 2) NOT NULL DEFAULT 0,

    total_collection              NUMERIC(14, 2) NOT NULL DEFAULT 0,

    split_config_id               BIGINT REFERENCES eparking.revenue_split_config (id),
    aicl_pct                      NUMERIC(5, 4),
    gsds_pct                      NUMERIC(5, 4),
    aicl_amount                   NUMERIC(14, 2) NOT NULL DEFAULT 0,
    gsds_amount                   NUMERIC(14, 2) NOT NULL DEFAULT 0,

    transaction_count_total       INT NOT NULL DEFAULT 0,

    rebuilt_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    classification_version        INT NOT NULL DEFAULT 1
);
