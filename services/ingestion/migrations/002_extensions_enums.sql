-- 002_extensions_enums.sql
-- Sprint 2: extensions required by later EXCLUDE USING gist constraints, and
-- the revenue_stream_enum used by fee_categories / dashboard_transactions.

CREATE EXTENSION IF NOT EXISTS btree_gist;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'revenue_stream_enum' AND n.nspname = 'eparking'
    ) THEN
        CREATE TYPE eparking.revenue_stream_enum AS ENUM (
            'card_subscription',
            'parking_ticket',
            'test_charge'
        );
    END IF;
END
$$;
