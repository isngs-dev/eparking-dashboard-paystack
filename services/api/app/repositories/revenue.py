"""Revenue-page repository functions -- reads `eparking.daily_revenue`
(gold rollup) for everything KPI/trend shaped, per CLAUDE.md's table
ownership rules. Never touches `raw_transactions`.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import asyncpg

from app.core.filters import CommonFilters


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return value


# Public alias -- other layers (routers) convert NUMERIC rows to float too;
# keep the conversion logic in one place rather than duplicating it.
to_float = _to_float


async def get_daily_revenue_range(
    conn: asyncpg.Connection,
    *,
    date_from: date,
    date_to: date,
) -> list[dict]:
    """One row per `revenue_date` in [date_from, date_to], DB-side -- no
    vehicle/day-of-week filter here since `daily_revenue` is already a
    day-grain rollup with no per-vehicle or per-transaction granularity.
    """
    rows = await conn.fetch(
        """
        SELECT revenue_date, ticket_count, ticket_amount, ticket_amount_by_vehicle,
               card_annual_count, card_annual_amount, card_monthly_count,
               card_monthly_amount, card_total_amount, total_collection,
               split_config_id, aicl_pct, gsds_pct, aicl_amount, gsds_amount,
               transaction_count_total
        FROM eparking.daily_revenue
        WHERE revenue_date >= $1 AND revenue_date <= $2
        ORDER BY revenue_date
        """,
        date_from,
        date_to,
    )
    return [dict(r) for r in rows]


async def sum_window(
    conn: asyncpg.Connection,
    *,
    date_from: date,
    date_to: date,
) -> dict:
    row = await conn.fetchrow(
        """
        SELECT
            COALESCE(SUM(ticket_amount), 0)      AS ticket_amount,
            COALESCE(SUM(card_total_amount), 0)  AS card_total_amount,
            COALESCE(SUM(total_collection), 0)   AS total_collection,
            COALESCE(SUM(transaction_count_total), 0) AS transaction_count_total,
            COALESCE(SUM(ticket_count), 0)       AS ticket_count
        FROM eparking.daily_revenue
        WHERE revenue_date >= $1 AND revenue_date <= $2
        """,
        date_from,
        date_to,
    )
    return {
        "ticket_amount": _to_float(row["ticket_amount"]),
        "card_total_amount": _to_float(row["card_total_amount"]),
        "total_collection": _to_float(row["total_collection"]),
        "transaction_count_total": row["transaction_count_total"],
        "ticket_count": row["ticket_count"],
    }


async def sum_total_collection(
    conn: asyncpg.Connection,
    *,
    date_from: date,
    date_to: date,
) -> float:
    """Lightweight variant of `sum_window` for prior-period delta comparisons
    -- only `total_collection` is needed there, so this avoids pulling the
    other aggregate columns for a value the caller discards.
    """
    row = await conn.fetchrow(
        """
        SELECT COALESCE(SUM(total_collection), 0) AS total_collection
        FROM eparking.daily_revenue
        WHERE revenue_date >= $1 AND revenue_date <= $2
        """,
        date_from,
        date_to,
    )
    return _to_float(row["total_collection"])


def prior_period_range(date_from: date, date_to: date) -> tuple[date, date]:
    """The immediately preceding period of equal day-count, per the Sprint 6
    pre-step spec -- e.g. Aug 1-8 (8 days) compares against Jul 24-31 (8 days).
    """
    span_days = (date_to - date_from).days + 1
    prior_to = date_from - timedelta(days=1)
    prior_from = prior_to - timedelta(days=span_days - 1)
    return prior_from, prior_to


def compute_delta_pct(current: float, prior: float) -> float | None:
    """`((current - prior) / prior) * 100`, or `None` when the prior period
    had zero collection -- explicit guard against division-by-zero / an
    infinite-percent artifact (Sprint 6 pre-step spec), never `inf`/crash.
    """
    if prior <= 0:
        return None
    return ((current - prior) / prior) * 100


async def get_prior_period_total_collection(
    conn: asyncpg.Connection,
    *,
    date_from: date,
    date_to: date,
) -> float:
    """Sums `total_collection` over the equal-length period immediately
    preceding [date_from, date_to]."""
    prior_from, prior_to = prior_period_range(date_from, date_to)
    return await sum_total_collection(conn, date_from=prior_from, date_to=prior_to)


async def get_card_breakdown_by_day(
    conn: asyncpg.Connection,
    *,
    filters: CommonFilters,
) -> list[dict]:
    """Card sales by day x Annual/Monthly, from `dashboard_transactions`'
    `card_component_annual/monthly_*` columns. Per the corrected CLAUDE.md
    rule #2, a ₦12,500 charge is ONE first-time Annual card (card +
    registration fee) and contributes to the Annual series ONLY -- never to
    Monthly -- and ₦25,000 is two of those. `daily_revenue` has this rolled up at
    day grain with no vehicle_type/day-of-week dimension to filter on, so we
    query `dashboard_transactions` directly here (still not `raw_transactions`).
    """
    clauses = ["status = 'success'"]
    params: list = []
    idx = 1
    if filters.date_from is not None:
        clauses.append(f"transaction_date >= ${idx}")
        params.append(filters.date_from)
        idx += 1
    if filters.date_to is not None:
        clauses.append(f"transaction_date <= ${idx}")
        params.append(filters.date_to)
        idx += 1
    if filters.days:
        clauses.append(f"day_of_week = ANY(${idx}::smallint[])")
        params.append(list(filters.days))
        idx += 1
    # vehicle_types intentionally not applied here -- card rows never carry a
    # vehicle_type (cards aren't vehicle-tiered), so filtering by it would
    # silently zero out this endpoint. Documented deviation, see report.

    where_sql = " AND ".join(clauses)
    rows = await conn.fetch(
        f"""
        SELECT
            transaction_date,
            SUM(card_component_annual_count)  AS annual_count,
            SUM(card_component_annual_amount) AS annual_amount,
            SUM(card_component_monthly_count) AS monthly_count,
            SUM(card_component_monthly_amount) AS monthly_amount
        FROM eparking.dashboard_transactions
        WHERE {where_sql}
        GROUP BY transaction_date
        ORDER BY transaction_date
        """,
        *params,
    )
    return [
        {
            "date": r["transaction_date"],
            "annual_count": r["annual_count"],
            "annual_amount": _to_float(r["annual_amount"]),
            "monthly_count": r["monthly_count"],
            "monthly_amount": _to_float(r["monthly_amount"]),
        }
        for r in rows
    ]


async def get_ticket_daily_by_tier(
    conn: asyncpg.Connection,
    *,
    filters: CommonFilters,
) -> list[dict]:
    """Day x vehicle-type ticket amounts, for the stacked bar. Reads
    `dashboard_transactions` directly (not `daily_revenue.ticket_amount_by_vehicle`)
    because vehicle_types/days filters need per-transaction granularity that
    the JSONB rollup doesn't expose query-side.
    """
    clauses = ["status = 'success'", "revenue_stream = 'parking_ticket'"]
    params: list = []
    idx = 1
    if filters.date_from is not None:
        clauses.append(f"transaction_date >= ${idx}")
        params.append(filters.date_from)
        idx += 1
    if filters.date_to is not None:
        clauses.append(f"transaction_date <= ${idx}")
        params.append(filters.date_to)
        idx += 1
    if filters.vehicle_types:
        clauses.append(f"vehicle_type = ANY(${idx}::text[])")
        params.append(list(filters.vehicle_types))
        idx += 1
    if filters.days:
        clauses.append(f"day_of_week = ANY(${idx}::smallint[])")
        params.append(list(filters.days))
        idx += 1

    where_sql = " AND ".join(clauses)
    rows = await conn.fetch(
        f"""
        SELECT transaction_date, vehicle_type,
               COALESCE(SUM(ticket_quantity), 0) AS ticket_count,
               SUM(amount) AS ticket_amount
        FROM eparking.dashboard_transactions
        WHERE {where_sql}
        GROUP BY transaction_date, vehicle_type
        ORDER BY transaction_date, vehicle_type
        """,
        *params,
    )
    return [
        {
            "date": r["transaction_date"],
            "vehicle_type": r["vehicle_type"],
            "ticket_count": r["ticket_count"],
            "ticket_amount": _to_float(r["ticket_amount"]),
        }
        for r in rows
    ]


async def get_revenue_split(
    conn: asyncpg.Connection,
    *,
    date_from: date,
    date_to: date,
) -> dict:
    """AICL/GSDS split, summed off `daily_revenue.aicl_amount/gsds_amount`
    (already computed at the split rate in force on each row's date -- see
    migration 010's comment on gross-basis, effective-dated splits).
    """
    row = await conn.fetchrow(
        """
        SELECT
            COALESCE(SUM(aicl_amount), 0) AS aicl_amount,
            COALESCE(SUM(gsds_amount), 0) AS gsds_amount,
            COALESCE(SUM(total_collection), 0) AS total_collection
        FROM eparking.daily_revenue
        WHERE revenue_date >= $1 AND revenue_date <= $2
        """,
        date_from,
        date_to,
    )
    latest_config = await conn.fetchrow(
        """
        SELECT aicl_pct, gsds_pct, effective_from, effective_to
        FROM eparking.revenue_split_config
        WHERE effective_from <= $1
          AND (effective_to IS NULL OR effective_to >= $1)
        ORDER BY effective_from DESC
        LIMIT 1
        """,
        date_to,
    )
    return {
        "aicl_amount": _to_float(row["aicl_amount"]),
        "gsds_amount": _to_float(row["gsds_amount"]),
        "total_collection": _to_float(row["total_collection"]),
        "aicl_pct": _to_float(latest_config["aicl_pct"]) if latest_config else None,
        "gsds_pct": _to_float(latest_config["gsds_pct"]) if latest_config else None,
    }


def zero_fill(
    rows: list[dict],
    *,
    date_from: date,
    date_to: date,
    date_key: str,
    zero_template: dict,
) -> list[dict]:
    """Zero-fills gap days in a date-keyed series so the frontend never has
    to special-case missing days (explicit Sprint 5 requirement for the
    revenue-trend endpoint).
    """
    by_date = {r[date_key]: r for r in rows}
    out: list[dict] = []
    d = date_from
    while d <= date_to:
        if d in by_date:
            out.append(by_date[d])
        else:
            out.append({date_key: d, **zero_template})
        d += timedelta(days=1)
    return out
