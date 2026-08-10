-- 011_unmapped_enum_value.sql
-- Sprint 4: add the 'unmapped' label to revenue_stream_enum, in its own
-- migration file. Split from the fee_categories seed insert (012) on
-- purpose -- Postgres forbids using a freshly ALTER TYPE ... ADD VALUE'd
-- enum label in the same transaction it was added in, and the migration
-- runner (app/migrate.py) wraps each file in one transaction.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'revenue_stream_enum' AND n.nspname = 'eparking'
          AND e.enumlabel = 'unmapped'
    ) THEN
        ALTER TYPE eparking.revenue_stream_enum ADD VALUE 'unmapped';
    END IF;
END
$$;
