-- 005_revenue_split_config.sql
-- Sprint 2: effective-dated AICL/GSDS revenue split configuration. Split
-- basis is confirmed as gross (per Sprint 0 overview resolution) -- applies
-- to total_collection, not net of Paystack fees.

CREATE TABLE IF NOT EXISTS eparking.revenue_split_config (
    id              BIGSERIAL PRIMARY KEY,
    aicl_pct        NUMERIC(5, 4) NOT NULL,
    gsds_pct        NUMERIC(5, 4) NOT NULL,
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    CONSTRAINT revenue_split_config_pct_sum_1
        CHECK (aicl_pct + gsds_pct = 1.0),
    CONSTRAINT revenue_split_config_effective_range_valid
        CHECK (effective_to IS NULL OR effective_from <= effective_to),
    CONSTRAINT revenue_split_config_no_overlap EXCLUDE USING gist (
        daterange(effective_from, effective_to, '[]') WITH &&
    )
);

INSERT INTO eparking.revenue_split_config (aicl_pct, gsds_pct, effective_from, effective_to)
SELECT 0.30, 0.70, '2020-01-01', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM eparking.revenue_split_config
    WHERE effective_from = '2020-01-01' AND effective_to IS NULL
);
