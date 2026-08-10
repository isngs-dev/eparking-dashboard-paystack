-- 012_unmapped_fee_category.sql
-- Sprint 4: the UNMAPPED sentinel category. Any raw_transactions.amount that
-- matches no seeded fee_categories range must still resolve to a real
-- fee_category_id (never a bare NULL that could be quietly excluded by a
-- future `WHERE fee_category_id IS NOT NULL` mistake downstream) -- see
-- CLAUDE.md and .claude/skills/transform-classification/SKILL.md.
--
-- amount_min/amount_max are a placeholder range far outside any real amount
-- and are never used for range-matching -- the transform SQL resolves
-- UNMAPPED via a LEFT JOIN miss (COALESCE onto this row's id), not by
-- joining against this row's range. The EXCLUDE constraint still requires
-- *some* valid non-overlapping range, hence the negative placeholder.
--
-- is_revenue = false / counts_as_entry = false: safe default per the sprint
-- doc -- never count an unrecognized amount as revenue or an entry until a
-- human confirms what it actually is. revenue_stream = 'unmapped' (added in
-- migration 011) rather than NULL, so downstream grouping never needs a
-- NULL-handling special case for this row.

INSERT INTO eparking.fee_categories
    (code, revenue_stream, label, vehicle_type, amount_min, amount_max,
     counts_as_entry, is_revenue, components, is_provisional, known_limitation,
     priority, effective_from, effective_to)
VALUES
    ('UNMAPPED', 'unmapped', 'Unmapped / unrecognized amount', NULL,
     -1.00, -1.00, false, false, NULL, false,
     'Sentinel category for amounts matching no seeded fee_categories range. Never a silent drop -- surfaced on the admin unmapped-transactions report. A recurring UNMAPPED amount at meaningful volume is the signal of a missing price tier or an unconfirmed bundle (e.g. the one-off ₦25,000 charge seen once in the 28,672-row sample, deliberately left unseeded pending client confirmation -- see CLAUDE.md).',
     1000, '2020-01-01', NULL)
ON CONFLICT (code) DO NOTHING;
