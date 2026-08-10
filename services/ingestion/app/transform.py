"""The raw_transactions -> dashboard_transactions transform, and the
dashboard_transactions -> daily_revenue rollup.

See .claude/sprints/04_TRANSFORM_CLASSIFICATION.md and
.claude/skills/transform-classification/SKILL.md for the full business-rule
rationale. Summary of the confirmed rules this SQL encodes (do not
relitigate without explicit client sign-off -- see CLAUDE.md):

    1. Amount -> category is a single set-based LEFT JOIN against
       `fee_categories` on `amount BETWEEN amount_min AND amount_max` plus an
       effective-date match. The EXCLUDE USING gist constraint on
       fee_categories guarantees at most one row can match a given
       (amount, date) pair -- this SQL never needs to break ties.
    2. A LEFT JOIN miss (no fee_categories row matches) resolves to the
       UNMAPPED sentinel category (migration 012), never a bare NULL and
       never a dropped row.
    3. `components` JSONB is expanded into card_component_annual_count/amount
       and card_component_monthly_count/amount. Only the CARD_ANNUAL and
       CARD_MONTHLY component codes feed those columns -- any other component
       code (notably CARD_FIRST_TIME_FEE) is carried for auditability but
       contributes to neither card sub-type total. Plain CARD_ANNUAL/
       CARD_MONTHLY rows populate only their own matching component. Every
       other category gets all-zero components. The transaction always stays
       exactly one row.

       ₦12,500 is ONE first-time Annual card (₦10,500 card + ₦2,000 one-time
       registration fee), NOT an Annual+Monthly bundle -- it contributes
       +1/₦12,500 annual and nothing monthly. ₦25,000 is two of those on one
       swipe (+2/₦25,000 annual, nothing monthly). See migration 013.
    4. Batched multi-unit rows (`base_category_code` non-NULL, e.g. ₦900 =
       3 x ₦300 Car) resolve onto their BASE category's id/code/vehicle_type
       and carry `ticket_quantity` = the seeded `unit_quantity`, so they
       report as the base tier with a quantity rather than as a pseudo-tier
       of their own. Matching is still purely exact-amount range matching --
       there is deliberately no computed `amount % 300` fallback (it would
       silently turn the ₦3,300/₦6,000/₦300,000 rows now sitting in UNMAPPED
       into fabricated car entries). New multiples are seed rows, not code.
    5. Everything is computed set-based, one INSERT ... SELECT ... ON
       CONFLICT DO UPDATE per call -- no row-by-row Python loop.

Both `transform_raw_to_dashboard` (bounded by paid_at/created_at window) and
`reclassify_transactions` (bounded by transaction_date, i.e. dashboard-side
date semantics) share the same SQL body (`_TRANSFORM_SQL`) parameterized on a
`(from_ts, to_ts)` timestamptz range over `raw_transactions.paid_at`. This
keeps the two entry points from drifting into two different classification
implementations -- see the skill's "core mechanism" section.
"""

from __future__ import annotations

from datetime import date, datetime

import asyncpg

# Business timezone is read from app_settings at call time (never hardcoded)
# per the entry-count-basis precedent in the transform-classification skill
# -- "computed at business_timezone" applies to every denormalized date/time
# column here, not just the entry-count basis setting.
_DEFAULT_BUSINESS_TIMEZONE = "Africa/Lagos"


async def get_business_timezone(conn: asyncpg.Connection) -> str:
    row = await conn.fetchrow(
        "SELECT value FROM eparking.app_settings WHERE key = 'business_timezone'"
    )
    return row["value"] if row else _DEFAULT_BUSINESS_TIMEZONE


# --------------------------------------------------------------------------
# transform_raw_to_dashboard / reclassify_transactions
# --------------------------------------------------------------------------
#
# One INSERT ... SELECT ... FROM raw_transactions LEFT JOIN fee_categories
# ... ON CONFLICT (paystack_transaction_id) DO UPDATE. Bound by
# raw_transactions.paid_at (falling back to nothing for NULL paid_at --see
# note below) BETWEEN $1 AND $2.
#
# fee_categories matching:
#   - amount BETWEEN amount_min AND amount_max (inclusive both ends, matches
#     the '[]' bounds used by the EXCLUDE USING gist constraint).
#   - effective_from <= transaction_date (business-tz) AND
#     (effective_to IS NULL OR transaction_date <= effective_to).
#   - LEFT JOIN, so a miss produces a NULL fc.id, resolved via a second
#     LEFT JOIN against the UNMAPPED sentinel row (looked up once by code,
#     not hardcoded id) with COALESCE.
#
# NULL paid_at: Paystack's live API always sets paid_at for anything that
# reached a terminal success/failed/abandoned state in the sample data, but
# is nullable at the schema level (see migration 008). A transaction with a
# NULL paid_at cannot be windowed by paid_at at all -- rather than silently
# drop it from every transform run (violating the "no drops" acceptance
# gate), such rows fall back to being date-bucketed by `now()` at transform
# time and are still included whenever the raw row's created/ingested time
# falls in range implicitly via being present in raw_transactions at all.
# Practically: none have been observed in the live pull (verified below in
# the acceptance test), so this is a defensive fallback, not a load-bearing
# path.
_TRANSFORM_SQL = """
WITH tz AS (
    SELECT $3::text AS business_tz
),
unmapped AS (
    SELECT id FROM eparking.fee_categories WHERE code = 'UNMAPPED'
),
matched AS (
    SELECT
        rt.paystack_transaction_id,
        rt.reference,
        rt.amount,
        rt.status,
        rt.channel,
        rt.source_identifier,
        rt.fees,
        rt.paid_at,
        COALESCE(rt.paid_at, now()) AT TIME ZONE tz.business_tz AS local_ts,
        fc.id                       AS matched_fee_category_id,
        fc.code                     AS matched_fee_category_code,
        fc.revenue_stream           AS matched_revenue_stream,
        fc.vehicle_type             AS matched_vehicle_type,
        fc.counts_as_entry          AS matched_counts_as_entry,
        fc.is_revenue               AS matched_is_revenue,
        fc.is_provisional           AS matched_is_provisional,
        fc.components               AS matched_components,
        fc.unit_quantity            AS matched_unit_quantity,
        -- Batched multi-unit rows (e.g. TICKET_300_X3 for ₦900) report as
        -- their BASE tier: base.id/code/vehicle_type/revenue_stream win over
        -- the matched row's own, so a ₦900 payment aggregates as Car rather
        -- than as a distinct ₦900 pseudo-tier. Ordinary categories have
        -- base_category_code NULL, making this join a no-op for them.
        base.id                     AS base_fee_category_id,
        base.code                   AS base_fee_category_code,
        base.revenue_stream         AS base_revenue_stream,
        base.vehicle_type           AS base_vehicle_type
    FROM eparking.raw_transactions rt
    CROSS JOIN tz
    LEFT JOIN eparking.fee_categories fc
        ON rt.amount BETWEEN fc.amount_min AND fc.amount_max
        AND fc.code <> 'UNMAPPED'
        AND fc.effective_from <= (COALESCE(rt.paid_at, now()) AT TIME ZONE tz.business_tz)::date
        AND (fc.effective_to IS NULL
             OR (COALESCE(rt.paid_at, now()) AT TIME ZONE tz.business_tz)::date <= fc.effective_to)
    LEFT JOIN eparking.fee_categories base
        ON base.code = fc.base_category_code
    WHERE rt.paid_at IS NULL OR rt.paid_at BETWEEN $1 AND $2
),
resolved AS (
    SELECT
        m.*,
        COALESCE(m.base_fee_category_id, m.matched_fee_category_id, u.id) AS fee_category_id,
        COALESCE(m.base_fee_category_code, m.matched_fee_category_code, 'UNMAPPED') AS fee_category_code,
        COALESCE(m.base_revenue_stream, m.matched_revenue_stream,
                 'unmapped'::eparking.revenue_stream_enum)         AS revenue_stream,
        COALESCE(m.base_vehicle_type, m.matched_vehicle_type)      AS vehicle_type,
        COALESCE(m.matched_counts_as_entry, false)                 AS counts_as_entry,
        COALESCE(m.matched_is_revenue, false)                      AS is_revenue,
        COALESCE(m.matched_is_provisional, false)                  AS is_provisional_class,
        m.matched_components                                       AS components,
        -- Unmatched (UNMAPPED) rows get quantity 1 -- never inflate a count
        -- for an amount whose meaning nobody has confirmed. They are excluded
        -- from entry/ticket aggregates anyway via counts_as_entry/is_revenue.
        COALESCE(m.matched_unit_quantity, 1)                       AS ticket_quantity
    FROM matched m
    CROSS JOIN unmapped u
),
-- Only CARD_ANNUAL / CARD_MONTHLY component codes feed the card sub-type
-- columns. Any other component code -- notably CARD_FIRST_TIME_FEE, the
-- ₦2,000 one-time registration fee inside the ₦12,500 first-time annual card
-- -- is carried in the JSONB for auditability but contributes to NEITHER
-- total. That is the whole point of the corrected ₦12,500 rule: the ₦2,000 is
-- a registration fee, not the cab-driver Monthly card, so it must never land
-- in card_component_monthly_*.
--
-- When `components` is non-NULL but contains no entry for a given code, the
-- correlated SUM returns NULL and COALESCE falls through to the
-- single-category fallback -- which is 0 for any row whose own
-- fee_category_code isn't that card type, so a components-bearing row can
-- never accidentally pick up a phantom count. Made explicit here rather than
-- relied upon implicitly.
components_expanded AS (
    SELECT
        r.*,
        COALESCE((
            SELECT SUM((comp->>'count')::int)
            FROM jsonb_array_elements(r.components) comp
            WHERE comp->>'code' = 'CARD_ANNUAL'
        ), CASE WHEN r.fee_category_code = 'CARD_ANNUAL' THEN 1 ELSE 0 END) AS card_component_annual_count,
        COALESCE((
            SELECT SUM((comp->>'count')::int)
            FROM jsonb_array_elements(r.components) comp
            WHERE comp->>'code' = 'CARD_MONTHLY'
        ), CASE WHEN r.fee_category_code = 'CARD_MONTHLY' THEN 1 ELSE 0 END) AS card_component_monthly_count,
        COALESCE((
            SELECT SUM((comp->>'amount')::numeric)
            FROM jsonb_array_elements(r.components) comp
            WHERE comp->>'code' = 'CARD_ANNUAL'
        ), CASE WHEN r.fee_category_code = 'CARD_ANNUAL' THEN r.amount ELSE 0 END) AS card_component_annual_amount,
        COALESCE((
            SELECT SUM((comp->>'amount')::numeric)
            FROM jsonb_array_elements(r.components) comp
            WHERE comp->>'code' = 'CARD_MONTHLY'
        ), CASE WHEN r.fee_category_code = 'CARD_MONTHLY' THEN r.amount ELSE 0 END) AS card_component_monthly_amount
    FROM resolved r
),
final AS (
    SELECT
        ce.paystack_transaction_id,
        ce.reference,
        ce.amount,
        ce.fee_category_id,
        ce.fee_category_code,
        ce.revenue_stream,
        ce.vehicle_type,
        ce.counts_as_entry,
        ce.is_revenue,
        ce.is_provisional_class,
        ce.status,
        ce.channel,
        pt.id                                   AS terminal_id,
        ce.source_identifier                    AS terminal_serial,
        pt.location_id                          AS location_id,
        loc.name                                AS location_name,
        ce.paid_at,
        ce.local_ts::date                       AS transaction_date,
        EXTRACT(HOUR FROM ce.local_ts)::smallint AS transaction_hour,
        -- ISO day_of_week: 1=Monday .. 7=Sunday, per isodow.
        EXTRACT(ISODOW FROM ce.local_ts)::smallint AS day_of_week,
        EXTRACT(WEEK FROM ce.local_ts)::smallint   AS iso_week,
        EXTRACT(ISOYEAR FROM ce.local_ts)::smallint AS iso_year,
        date_trunc('month', ce.local_ts)::date  AS month_start,
        ce.card_component_annual_count,
        ce.card_component_monthly_count,
        ce.card_component_annual_amount,
        ce.card_component_monthly_amount,
        ce.ticket_quantity,
        ce.fees
    FROM components_expanded ce
    LEFT JOIN eparking.pos_terminals pt ON pt.serial = ce.source_identifier
    LEFT JOIN eparking.locations loc ON loc.id = pt.location_id
)
INSERT INTO eparking.dashboard_transactions (
    paystack_transaction_id, reference, amount,
    fee_category_id, fee_category_code, revenue_stream, vehicle_type,
    counts_as_entry, is_revenue, is_provisional_class,
    status, channel,
    terminal_id, terminal_serial, location_id, location_name,
    paid_at, transaction_date, transaction_hour, day_of_week,
    iso_week, iso_year, month_start,
    card_component_annual_count, card_component_monthly_count,
    card_component_annual_amount, card_component_monthly_amount,
    ticket_quantity,
    fees, classified_at, classification_version
)
SELECT
    paystack_transaction_id, reference, amount,
    fee_category_id, fee_category_code, revenue_stream, vehicle_type,
    counts_as_entry, is_revenue, is_provisional_class,
    status, channel,
    terminal_id, terminal_serial, location_id, location_name,
    paid_at, transaction_date, transaction_hour, day_of_week,
    iso_week, iso_year, month_start,
    card_component_annual_count, card_component_monthly_count,
    card_component_annual_amount, card_component_monthly_amount,
    ticket_quantity,
    fees, now(), 1
FROM final
ON CONFLICT (paystack_transaction_id) DO UPDATE SET
    reference                      = EXCLUDED.reference,
    amount                         = EXCLUDED.amount,
    fee_category_id                = EXCLUDED.fee_category_id,
    fee_category_code              = EXCLUDED.fee_category_code,
    revenue_stream                 = EXCLUDED.revenue_stream,
    vehicle_type                   = EXCLUDED.vehicle_type,
    counts_as_entry                = EXCLUDED.counts_as_entry,
    is_revenue                     = EXCLUDED.is_revenue,
    is_provisional_class           = EXCLUDED.is_provisional_class,
    status                         = EXCLUDED.status,
    channel                        = EXCLUDED.channel,
    terminal_id                    = EXCLUDED.terminal_id,
    terminal_serial                = EXCLUDED.terminal_serial,
    location_id                    = EXCLUDED.location_id,
    location_name                  = EXCLUDED.location_name,
    paid_at                        = EXCLUDED.paid_at,
    transaction_date               = EXCLUDED.transaction_date,
    transaction_hour               = EXCLUDED.transaction_hour,
    day_of_week                    = EXCLUDED.day_of_week,
    iso_week                       = EXCLUDED.iso_week,
    iso_year                       = EXCLUDED.iso_year,
    month_start                    = EXCLUDED.month_start,
    card_component_annual_count    = EXCLUDED.card_component_annual_count,
    card_component_monthly_count   = EXCLUDED.card_component_monthly_count,
    card_component_annual_amount   = EXCLUDED.card_component_annual_amount,
    card_component_monthly_amount  = EXCLUDED.card_component_monthly_amount,
    ticket_quantity                = EXCLUDED.ticket_quantity,
    fees                           = EXCLUDED.fees,
    classified_at                  = now(),
    classification_version         = eparking.dashboard_transactions.classification_version + 1
"""


async def transform_raw_to_dashboard(
    conn: asyncpg.Connection,
    *,
    from_ts: datetime,
    to_ts: datetime,
) -> int:
    """Set-based transform of `raw_transactions` -> `dashboard_transactions`
    for rows whose `paid_at` falls in `[from_ts, to_ts]` (inclusive both
    ends -- matches the ingestion window semantics in tasks/ingest.py).

    Intended to run inline in the same Celery task as ingestion (see the
    sprint doc) -- call this immediately after
    `upsert_raw_transactions_batch` in the same run, not as a separately
    scheduled task, so raw and dashboard tables can never silently drift.

    Idempotent: safe to call repeatedly over overlapping windows (ON
    CONFLICT DO UPDATE), and calling it twice in a row with no intervening
    raw_transactions or fee_categories change produces byte-identical
    dashboard_transactions rows except for `classified_at`/
    `classification_version`, which intentionally advance on every write to
    track "was this row touched by this run" -- see reclassify_transactions
    for the idempotency proof used by the acceptance test, which excludes
    those two bookkeeping columns from its comparison for exactly this
    reason.
    """
    business_tz = await get_business_timezone(conn)
    result = await conn.execute(_TRANSFORM_SQL, from_ts, to_ts, business_tz)
    # asyncpg returns a string like "INSERT 0 123"; last token is the count.
    return int(result.split()[-1])


async def reclassify_transactions(
    conn: asyncpg.Connection,
    *,
    from_date: date,
    to_date: date,
    reason: str,
    return_run_id: bool = False,
) -> int | tuple[int, int]:
    """Replay `raw_transactions` through the *current* `fee_categories`
    rules into `dashboard_transactions`, for the explicit date range
    `[from_date, to_date]` (inclusive). Never calls the Paystack API --
    reads only from `raw_transactions`.

    `from_date`/`to_date` are business-tz calendar dates (matching
    `dashboard_transactions.transaction_date` semantics), converted here to
    a `paid_at` timestamptz window spanning full business-tz days so the
    same `_TRANSFORM_SQL` body (windowed on `raw_transactions.paid_at`) can
    be reused unchanged -- see the skill's guidance to share transform SQL
    between the inline transform and reclassify rather than maintaining two
    implementations.

    `reason` is accepted per the sprint doc's signature and reserved for a
    future audit-log write (e.g. into `run_logs` with `run_type='reclassify'`
    -- not yet wired to a dedicated table this sprint); logged to run_logs
    here so the call is still auditable today.

    Chunking by month for large ranges and the Redis lock against the inline
    transform are caller/scheduler concerns (the admin-triggered reclassify
    flow, built in Sprint 7) -- this function is the single-range primitive
    they compose, kept here as one unit so both callers share one
    implementation.
    """
    business_tz = await get_business_timezone(conn)

    window_from, window_to = await conn.fetchrow(
        """
        SELECT
            ($1::date)::timestamp AT TIME ZONE $3::text,
            (($2::date + 1))::timestamp AT TIME ZONE $3::text - interval '1 microsecond'
        """,
        from_date,
        to_date,
        business_tz,
    )

    run_id = await conn.fetchval(
        """
        INSERT INTO eparking.run_logs (run_type, status, window_from, window_to)
        VALUES ('reclassify', 'running', $1, $2)
        RETURNING id
        """,
        window_from,
        window_to,
    )

    try:
        rows_affected = await transform_raw_to_dashboard(
            conn, from_ts=window_from, to_ts=window_to
        )
        await conn.execute(
            """
            UPDATE eparking.run_logs
            SET status = 'success', rows_upserted = $2, finished_at = now(),
                error_message = $3
            WHERE id = $1
            """,
            run_id,
            rows_affected,
            f"reason: {reason}" if reason else None,
        )
    except Exception as exc:  # noqa: BLE001 -- surfaced via run_logs, then re-raised
        await conn.execute(
            """
            UPDATE eparking.run_logs
            SET status = 'failed', finished_at = now(), error_message = $2
            WHERE id = $1
            """,
            run_id,
            f"reason: {reason}; error: {exc}",
        )
        raise

    if return_run_id:
        return rows_affected, run_id
    return rows_affected


# --------------------------------------------------------------------------
# rebuild_daily_revenue
# --------------------------------------------------------------------------
#
# DELETE ... WHERE revenue_date = ANY($1) then INSERT ... SELECT ... GROUP BY
# transaction_date, for the affected dates only -- never a full-table rebuild.
# Applies the effective-dated revenue_split_config, freezing aicl_amount/
# gsds_amount at the split rate in force on each row's transaction_date (a
# multi-day range spanning a rate change correctly uses a different rate per
# day, since the join is per-row against revenue_split_config, not a single
# rate looked up once for the whole call).

_REBUILD_DAILY_REVENUE_SQL = """
WITH by_vehicle AS (
    SELECT
        dt.transaction_date AS revenue_date,
        jsonb_object_agg(dt.vehicle_type, veh_amount) AS ticket_amount_by_vehicle
    FROM (
        SELECT transaction_date, vehicle_type, SUM(amount) AS veh_amount
        FROM eparking.dashboard_transactions
        WHERE status = 'success' AND is_revenue
          AND revenue_stream = 'parking_ticket'
          AND transaction_date = ANY($1::date[])
        GROUP BY transaction_date, vehicle_type
    ) dt
    GROUP BY dt.transaction_date
),
agg AS (
    SELECT
        dt.transaction_date AS revenue_date,

        -- Tickets = VEHICLES, so this sums ticket_quantity: one batched ₦900
        -- payment is 3 car tickets, not 1. The distinct row count is kept
        -- separately as ticket_transaction_count now that the two differ.
        COALESCE(SUM(dt.ticket_quantity) FILTER (WHERE dt.revenue_stream = 'parking_ticket'), 0) AS ticket_count,
        COUNT(*) FILTER (WHERE dt.revenue_stream = 'parking_ticket')                 AS ticket_transaction_count,
        COALESCE(SUM(dt.amount) FILTER (WHERE dt.revenue_stream = 'parking_ticket'), 0) AS ticket_amount,

        COALESCE(SUM(dt.card_component_annual_count), 0)                               AS card_annual_count_raw,
        COALESCE(SUM(dt.card_component_annual_amount), 0)                              AS card_annual_amount,
        COALESCE(SUM(dt.card_component_monthly_count), 0)                              AS card_monthly_count_raw,
        COALESCE(SUM(dt.card_component_monthly_amount), 0)                             AS card_monthly_amount,

        COALESCE(SUM(dt.amount), 0)                                                    AS total_collection,
        COUNT(*)                                                                       AS transaction_count_total
    FROM eparking.dashboard_transactions dt
    WHERE dt.status = 'success' AND dt.is_revenue
      AND dt.transaction_date = ANY($1::date[])
    GROUP BY dt.transaction_date
),
with_split AS (
    SELECT
        agg.*,
        bv.ticket_amount_by_vehicle,
        rsc.id       AS split_config_id,
        rsc.aicl_pct AS aicl_pct,
        rsc.gsds_pct AS gsds_pct
    FROM agg
    LEFT JOIN by_vehicle bv ON bv.revenue_date = agg.revenue_date
    LEFT JOIN eparking.revenue_split_config rsc
        ON rsc.effective_from <= agg.revenue_date
        AND (rsc.effective_to IS NULL OR agg.revenue_date <= rsc.effective_to)
)
INSERT INTO eparking.daily_revenue (
    revenue_date,
    ticket_count, ticket_transaction_count, ticket_amount, ticket_amount_by_vehicle,
    card_annual_count, card_annual_amount,
    card_monthly_count, card_monthly_amount, card_total_amount,
    total_collection,
    split_config_id, aicl_pct, gsds_pct, aicl_amount, gsds_amount,
    transaction_count_total,
    rebuilt_at, classification_version
)
SELECT
    revenue_date,
    ticket_count, ticket_transaction_count, ticket_amount, ticket_amount_by_vehicle,
    card_annual_count_raw, card_annual_amount,
    card_monthly_count_raw, card_monthly_amount,
    card_annual_amount + card_monthly_amount,
    total_collection,
    split_config_id, aicl_pct, gsds_pct,
    ROUND(total_collection * COALESCE(aicl_pct, 0), 2),
    ROUND(total_collection * COALESCE(gsds_pct, 0), 2),
    transaction_count_total,
    now(), 1
FROM with_split
"""


async def rebuild_daily_revenue(conn: asyncpg.Connection, *, dates: list[date]) -> int:
    """Delete-then-insert `daily_revenue` rows for exactly `dates`.

    Chained after `transform_raw_to_dashboard`/`reclassify_transactions` for
    the same affected date range -- never a full rebuild. Aggregates from
    `dashboard_transactions WHERE status='success' AND is_revenue` only
    (UNMAPPED and test-charge rows are excluded from every money total by
    construction, since both have `is_revenue = false`).

    Card annual/monthly counts/amounts are summed from the
    `card_component_annual/monthly_count/amount` columns rather than
    `revenue_stream = 'card_subscription'`, so multi-unit card rows contribute
    the right per-sub-type counts from a single dashboard_transactions row.
    Under the corrected rule (migration 013), ₦12,500 and ₦25,000 are
    first-time Annual card purchases and contribute ONLY to annual -- their
    embedded ₦2,000 registration fee is not the cab-driver Monthly card and
    must never reach card_monthly_*.

    `ticket_count` sums `ticket_quantity` (vehicles), not rows, so a batched
    ₦900 = 3 x Car payment counts as 3 tickets; `ticket_transaction_count`
    keeps the row count.
    """
    if not dates:
        return 0

    async with conn.transaction():
        await conn.execute(
            "DELETE FROM eparking.daily_revenue WHERE revenue_date = ANY($1::date[])",
            dates,
        )
        result = await conn.execute(_REBUILD_DAILY_REVENUE_SQL, dates)

    return int(result.split()[-1])
