-- 006_app_settings.sql
-- Sprint 2: key/value config table. entry_count_basis is read at query time
-- (see transform-classification skill) -- never baked into the transform,
-- so flipping it never requires a backfill.

CREATE TABLE IF NOT EXISTS eparking.app_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    value_type      TEXT NOT NULL DEFAULT 'string',
    allowed_values  TEXT[],
    description     TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by      TEXT
);

INSERT INTO eparking.app_settings (key, value, value_type, allowed_values, description)
VALUES
    ('entry_count_basis', 'ticket_only', 'string',
     ARRAY['ticket_only', 'all_transactions'],
     'Basis for occupancy/entry-count visuals: ticket_only counts only fee_categories.counts_as_entry rows, all_transactions counts every successful transaction. Query-time setting, not baked into the transform.'),

    ('business_timezone', 'Africa/Lagos', 'string',
     NULL,
     'Timezone used to bucket transaction_date/transaction_hour/day_of_week on dashboard_transactions. Pending final client confirmation per Sprint 0 open items (assumed UTC+1, no DST).')
ON CONFLICT (key) DO NOTHING;
