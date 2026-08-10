-- 013_first_time_annual_and_ticket_quantity.sql
-- Client correction (confirmed, final) to two classification rules that were
-- previously modelled on a WRONG understanding. Sprint 2/4's migrations have
-- already run in production, so this is a new forward migration -- 004 and 012
-- are deliberately left untouched.
--
-- CORRECTION 1 -- ₦12,500 is NOT an "Annual + Monthly bundle".
--   It is ONE Annual card purchase by a FIRST-TIME customer:
--       ₦10,500 (the card, same price as any other annual card)
--     + ₦2,000  (a one-time first-time-registration fee)
--   The ₦2,000 here has NOTHING to do with the ₦2,000 cab-driver Monthly card
--   -- that is a coincidental amount collision, not a product relationship.
--   Consequence: a ₦12,500 transaction must contribute +1 annual_count and
--   +₦12,500 annual_amount, and NOTHING AT ALL to monthly_count/monthly_amount.
--   The registration fee stays inside the annual amount (it is revenue on the
--   annual card sale), which is why annual_amount is the full 12,500 and not
--   10,500.
--
-- CORRECTION 2 -- ₦25,000 is TWO first-time Annual purchases (2 x ₦12,500) on
--   one POS swipe. +2 annual_count, +₦25,000 annual_amount, nothing monthly.
--   Previously unseeded (fell through to UNMAPPED); now client-confirmed.
--
-- CORRECTION 3 -- ₦900 is THREE Car tickets (3 x ₦300) in one swipe -- a
--   batched multi-vehicle payment, NOT a new price tier. It must resolve to the
--   EXISTING TICKET_300/Car category with a quantity of 3, so it contributes
--   +3 to ticket/entry counts and +₦900 to Car ticket revenue from one row.
--
-- --------------------------------------------------------------------------
-- MECHANISM: why explicit seeded multiples, and not `amount % 300 = 0`
-- --------------------------------------------------------------------------
-- The obvious "generalizable" implementation is computed logic: if an amount
-- matches nothing and is an exact multiple of the ₦300 base, treat it as
-- amount/300 Car tickets. That was evaluated and REJECTED, because the live
-- data proves it is unsafe. The amounts currently sitting in UNMAPPED include:
--
--       ₦3,300   (4 rows)  -> would silently become 11 x Car
--       ₦6,000   (1 row)   -> would silently become 20 x Car
--       ₦300,000 (2 rows)  -> would silently become 1,000 x Car
--
-- None of those are client-confirmed as batched car payments, and ₦300,000 as
-- "1,000 cars" would inject a fabricated +1,000 vehicles into every occupancy
-- visual off a single transaction. A modulo rule cannot tell a genuine batched
-- payment from an unrelated large charge, and its failure mode is silent
-- over-reporting -- the exact class of bug this layer exists to prevent. The
-- UNMAPPED report exists precisely so a human confirms these one at a time.
--
-- Instead: `base_category_code` + `unit_quantity` columns on fee_categories.
-- A "known multiple" is its own seed row with its own exact amount range, but
-- it POINTS AT a base category (TICKET_300) and carries an explicit quantity.
-- This is generalizable in the way the client asked for -- ₦1,500 = 5 x Car
-- later is a one-line seed INSERT plus a reclassify, no code change and no new
-- deploy -- while keeping every new multiple a deliberate, confirmed decision.
-- It also composes correctly with the existing EXCLUDE USING gist constraint
-- and the transform's single amount-range LEFT JOIN: exact-amount matching
-- stays the ONLY matching mechanism, so precedence is settled structurally
-- rather than by an ordering rule in code. ₦600 keeps matching its own
-- TICKET_600/Pickup-bus row and is never reinterpreted as 2 x Car, because
-- there is no fallback path that could reinterpret it.

-- --------------------------------------------------------------------------
-- Schema: quantity support
-- --------------------------------------------------------------------------

-- fee_categories: a category may declare that one transaction of this amount
-- represents `unit_quantity` units of `base_category_code`'s tier.
ALTER TABLE eparking.fee_categories
    ADD COLUMN IF NOT EXISTS unit_quantity INT NOT NULL DEFAULT 1;

ALTER TABLE eparking.fee_categories
    ADD COLUMN IF NOT EXISTS base_category_code TEXT;

ALTER TABLE eparking.fee_categories
    DROP CONSTRAINT IF EXISTS fee_categories_unit_quantity_positive;
ALTER TABLE eparking.fee_categories
    ADD CONSTRAINT fee_categories_unit_quantity_positive CHECK (unit_quantity >= 1);

COMMENT ON COLUMN eparking.fee_categories.unit_quantity IS
    'How many units of the underlying tier one transaction at this amount represents. 1 for every ordinary tier. 3 for TICKET_300_X3 (₦900 = 3 Car tickets). Ticket/entry counts SUM this instead of COUNT(*)-ing rows.';

COMMENT ON COLUMN eparking.fee_categories.base_category_code IS
    'For batched multi-unit rows: the code of the tier being multiplied (e.g. TICKET_300). The transform resolves the transaction onto the BASE category id/code/vehicle_type, so a ₦900 batched payment reports as Car, not as a separate ₦900 pseudo-tier. NULL for ordinary categories.';

-- dashboard_transactions: denormalized quantity, so occupancy/ticket-count
-- queries never need to join fee_categories to count correctly.
ALTER TABLE eparking.dashboard_transactions
    ADD COLUMN IF NOT EXISTS ticket_quantity INT NOT NULL DEFAULT 1;

COMMENT ON COLUMN eparking.dashboard_transactions.ticket_quantity IS
    'Units represented by this single transaction row (default 1). ₦900 = 3 Car tickets -> ticket_quantity = 3, amount stays the actual ₦900 paid. Every ticket_count/entry_count aggregate must SUM(ticket_quantity), never COUNT(*).';

-- daily_revenue.ticket_count now means "vehicles/tickets", not "rows", so the
-- distinct row count is kept alongside it rather than being lost.
ALTER TABLE eparking.daily_revenue
    ADD COLUMN IF NOT EXISTS ticket_transaction_count INT NOT NULL DEFAULT 0;

COMMENT ON COLUMN eparking.daily_revenue.ticket_count IS
    'Number of TICKETS (vehicles) -- SUM(ticket_quantity), so a batched ₦900 3-car payment counts as 3. Not the number of transaction rows; see ticket_transaction_count.';

COMMENT ON COLUMN eparking.daily_revenue.ticket_transaction_count IS
    'Number of ticket TRANSACTION ROWS (COUNT(*)), retained alongside ticket_count now that the two can differ because of batched multi-vehicle payments.';

-- --------------------------------------------------------------------------
-- Seed corrections
-- --------------------------------------------------------------------------

-- 1. ₦12,500 -> one first-time annual card, no monthly contribution.
--
-- The `components` JSONB is KEPT as the mechanism rather than being replaced
-- with an `annual_price_override` column, deliberately: components is already
-- a general "this amount decomposes into N units of these card sub-types"
-- expression, and that is still exactly what is being expressed here -- only
-- the CONTENTS were wrong, not the shape. It still holds the ₦10,500 card and
-- the ₦2,000 registration fee as separate, auditable line items (so the
-- registration-fee revenue remains visible and reportable if the client later
-- asks to split it out), while the transform only ever rolls CARD_ANNUAL and
-- CARD_MONTHLY codes into the annual/monthly component columns. The fee is
-- tagged with the neutral code CARD_FIRST_TIME_FEE, which is deliberately NOT
-- CARD_MONTHLY, so it contributes to neither card sub-type total. Introducing
-- a bespoke override column would have meant two parallel decomposition
-- mechanisms for one concept.
--
-- annual_amount is stated explicitly as the full 12,500 so the Card Sales
-- visual and daily_revenue.card_annual_amount reconcile to cash collected.
UPDATE eparking.fee_categories
SET label = 'Annual card - first-time customer (incl. registration fee)',
    components = '[{"code":"CARD_ANNUAL","amount":12500.00,"count":1},{"code":"CARD_FIRST_TIME_FEE","amount":2000.00,"count":0}]'::jsonb,
    known_limitation = 'CONFIRMED RULE (client, corrected): ₦12,500 = ONE first-time Annual card = ₦10,500 card + ₦2,000 one-time registration fee. The ₦2,000 component is NOT the cab-driver Monthly card -- coincidental amount collision only. Counts as +1 annual, ₦12,500 annual amount, and NOTHING monthly. An earlier revision wrongly modelled this as an Annual+Monthly bundle; do not reintroduce that.'
WHERE code = 'CARD_COMBO_12500';

-- 2. ₦25,000 -> two first-time annual cards on one swipe.
-- Brand-new amount range; cannot collide with the EXCLUDE USING gist
-- constraint (nothing else covers 25,000).
-- The CARD_ANNUAL component carries count 2 and the full ₦25,000, so the row
-- yields annual_count = 2 / annual_amount = 25,000 / monthly = 0.
INSERT INTO eparking.fee_categories
    (code, revenue_stream, label, vehicle_type, amount_min, amount_max,
     counts_as_entry, is_revenue, components, is_provisional, known_limitation,
     priority, effective_from, effective_to, unit_quantity, base_category_code)
VALUES
    ('CARD_COMBO_ANNUAL_X2', 'card_subscription',
     'Annual card x2 - two first-time customers, one swipe', NULL,
     25000.00, 25000.00, false, true,
     '[{"code":"CARD_ANNUAL","amount":25000.00,"count":2},{"code":"CARD_FIRST_TIME_FEE","amount":4000.00,"count":0}]'::jsonb,
     false,
     'CONFIRMED RULE (client): ₦25,000 = TWO first-time Annual card purchases (2 x ₦12,500) paid on one POS swipe. Decomposes as 2 x ₦10,500 card + 2 x ₦2,000 registration fee, but ALL of it is Annual revenue: +2 annual_count, +₦25,000 annual_amount, nothing monthly. Previously fell through to UNMAPPED as an unconfirmed one-off.',
     100, '2020-01-01', NULL, 1, NULL)
ON CONFLICT (code) DO NOTHING;

-- 3. ₦900 -> 3 x Car ticket, resolved onto the TICKET_300 category.
-- Its own exact amount range (so the gist constraint still guarantees a single
-- unambiguous match), but base_category_code redirects the transform to report
-- it as TICKET_300/Car with unit_quantity = 3. vehicle_type is left NULL here
-- because the transform takes vehicle_type from the resolved BASE category.
INSERT INTO eparking.fee_categories
    (code, revenue_stream, label, vehicle_type, amount_min, amount_max,
     counts_as_entry, is_revenue, components, is_provisional, known_limitation,
     priority, effective_from, effective_to, unit_quantity, base_category_code)
VALUES
    ('TICKET_300_X3', 'parking_ticket',
     'Car x3 - batched multi-vehicle payment', NULL,
     900.00, 900.00, true, true, NULL, false,
     'CONFIRMED RULE (client): ₦900 = 3 x Car ticket (₦300) paid in one swipe -- a batched multi-vehicle payment, not a new price tier. Reports as TICKET_300/Car with ticket_quantity = 3: +3 tickets/entries and +₦900 Car revenue from one transaction row. Deliberately NOT implemented as generic `amount % 300 = 0` logic -- see this migration''s header for why (₦3,300/₦6,000/₦300,000 sit in UNMAPPED and must stay there).',
     100, '2020-01-01', NULL, 3, 'TICKET_300')
ON CONFLICT (code) DO NOTHING;
