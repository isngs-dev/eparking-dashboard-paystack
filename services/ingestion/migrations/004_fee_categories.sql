-- 004_fee_categories.sql
-- Sprint 2: fee_categories -- the amount-range -> category classification
-- lookup. This is the highest-stakes table in the schema: the EXCLUDE USING
-- gist constraint is a correctness guarantee (overlapping amount ranges
-- within an overlapping effective-date window are a loud insert failure,
-- never a silent ambiguity), not an optimization. Do not omit it.
--
-- See CLAUDE.md and .claude/skills/transform-classification/SKILL.md for the
-- confirmed business rules behind the seed data below -- these are settled
-- client decisions, not open questions.

CREATE TABLE IF NOT EXISTS eparking.fee_categories (
    id                  BIGSERIAL PRIMARY KEY,
    code                TEXT NOT NULL UNIQUE,
    revenue_stream      eparking.revenue_stream_enum NOT NULL,
    label               TEXT NOT NULL,
    vehicle_type        TEXT,
    amount_min          NUMERIC(12, 2) NOT NULL,
    amount_max          NUMERIC(12, 2) NOT NULL,
    counts_as_entry     BOOLEAN NOT NULL,
    is_revenue          BOOLEAN NOT NULL,
    components          JSONB,
    is_provisional      BOOLEAN NOT NULL DEFAULT false,
    known_limitation    TEXT,
    priority            INT NOT NULL DEFAULT 100,
    effective_from      DATE NOT NULL,
    effective_to        DATE,
    CONSTRAINT fee_categories_amount_range_valid CHECK (amount_min <= amount_max),
    CONSTRAINT fee_categories_effective_range_valid
        CHECK (effective_to IS NULL OR effective_from <= effective_to),
    -- Correctness guarantee: no two rows may claim overlapping amount
    -- ranges during an overlapping effective-date window. This is what
    -- prevents the ₦2,000 CARD_MONTHLY/Lorry ambiguity (and any future
    -- price collision) from being silently double-mapped.
    CONSTRAINT fee_categories_no_overlap EXCLUDE USING gist (
        numrange(amount_min, amount_max, '[]') WITH &&,
        daterange(effective_from, effective_to, '[]') WITH &&
    )
);

CREATE INDEX IF NOT EXISTS ix_fee_categories_effective
    ON eparking.fee_categories (effective_from, effective_to);

-- Seed: confirmed price list. Do not add a ₦2,000 "Lorry" row (would
-- violate the EXCLUDE constraint above and contradicts the confirmed
-- CARD_MONTHLY rule). Do not seed a rule for ₦25,000 (single unconfirmed
-- occurrence -- leave it to fall through to UNMAPPED at transform time,
-- handled in a later sprint).

INSERT INTO eparking.fee_categories
    (code, revenue_stream, label, vehicle_type, amount_min, amount_max,
     counts_as_entry, is_revenue, components, is_provisional, known_limitation,
     priority, effective_from, effective_to)
VALUES
    ('TEST_CHARGE', 'test_charge', 'Test / verification charge', NULL,
     0.01, 99.99, false, false, NULL, false, NULL, 100, '2020-01-01', NULL),

    ('TICKET_100', 'parking_ticket', 'Porter', 'Porter',
     100.00, 100.00, true, true, NULL, false, NULL, 100, '2020-01-01', NULL),

    ('TICKET_300', 'parking_ticket', 'Car (incl. dispatch riders)', 'Car',
     300.00, 300.00, true, true, NULL, false, NULL, 100, '2020-01-01', NULL),

    ('TICKET_600', 'parking_ticket', 'Pickup bus', 'Pickup bus',
     600.00, 600.00, true, true, NULL, false, NULL, 100, '2020-01-01', NULL),

    ('TICKET_1200', 'parking_ticket', 'Dyna/Canter', 'Dyna/Canter',
     1200.00, 1200.00, true, true, NULL, false, NULL, 100, '2020-01-01', NULL),

    ('CARD_MONTHLY', 'card_subscription', 'Monthly card - cab driver', NULL,
     2000.00, 2000.00, false, true, NULL, false,
     'CONFIRMED DELIBERATE RULE: ₦2,000 is ambiguous between the cab-driver monthly card and a Lorry ticket (both ₦2,000). Client decided ALL ₦2,000 classify as CARD_MONTHLY because Lorry traffic is very rare and cards are the reporting priority. Lorry ticket revenue is therefore knowingly reported as card revenue. Do not "fix" this without written client sign-off.',
     100, '2020-01-01', NULL),

    ('TICKET_3000', 'parking_ticket', 'Trailer', 'Trailer',
     3000.00, 3000.00, true, true, NULL, false, NULL, 100, '2020-01-01', NULL),

    ('CARD_ANNUAL', 'card_subscription', 'Annual card - shopkeeper', NULL,
     10500.00, 10500.00, false, true, NULL, false, NULL, 100, '2020-01-01', NULL),

    ('CARD_COMBO_12500', 'card_subscription', 'Annual + Monthly bundle', NULL,
     12500.00, 12500.00, false, true,
     '[{"code":"CARD_ANNUAL","amount":10500.00,"count":1},{"code":"CARD_MONTHLY","amount":2000.00,"count":1}]'::jsonb,
     false, NULL, 100, '2020-01-01', NULL)
ON CONFLICT (code) DO NOTHING;
