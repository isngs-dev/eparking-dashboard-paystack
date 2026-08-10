"""Occupancy/Traffic-page repository functions -- reads
`eparking.dashboard_transactions` directly since these visuals need
hour-of-day / day-of-week granularity that `daily_revenue` doesn't carry.

`entry_count_basis` (app_settings) is read and applied at query time in every
function here -- never hardcoded to "ticket only" (see CLAUDE.md and the
api-layer skill).

Entry counts SUM `ticket_quantity`, never COUNT(*) rows: a single batched
multi-vehicle payment (₦900 = 3 x ₦300 Car) is one transaction row but three
vehicles entering. Ordinary rows carry ticket_quantity = 1, so this is
equivalent to COUNT(*) for everything except batched rows. See migration 013.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import asyncpg

from app.core.filters import CommonFilters
from app.core.sql_filters import build_where


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return value


def _entry_predicate(entry_count_basis: str) -> str:
    """`ticket_only` -> only counts_as_entry rows; `all_transactions` -> any
    successful is_revenue row, regardless of counts_as_entry. Both bases
    require status='success' -- failed/abandoned attempts never count as an
    entry under either basis.
    """
    if entry_count_basis == "all_transactions":
        return "status = 'success' AND is_revenue = true"
    # default / 'ticket_only'
    return "status = 'success' AND counts_as_entry = true"


async def get_entry_count(
    conn: asyncpg.Connection,
    *,
    filters: CommonFilters,
    entry_count_basis: str,
) -> dict:
    base_predicate = _entry_predicate(entry_count_basis)
    where_extra, params = build_where(
        filters,
        date_column="transaction_date",
        vehicle_type_column="vehicle_type",
        day_of_week_column="day_of_week",
    )
    row = await conn.fetchrow(
        f"""
        SELECT COALESCE(SUM(ticket_quantity), 0) AS entry_count
        FROM eparking.dashboard_transactions
        WHERE {base_predicate}{where_extra}
        """,
        *params,
    )
    return {"entry_count": row["entry_count"], "entry_count_basis": entry_count_basis}


async def get_hourly_histogram(
    conn: asyncpg.Connection,
    *,
    filters: CommonFilters,
    entry_count_basis: str,
) -> list[dict]:
    """Hourly histogram 0-23, averaged per day across the range. "Per day"
    means the number of distinct transaction_dates present in the filtered
    window, so a partial trailing day doesn't skew the average.
    """
    base_predicate = _entry_predicate(entry_count_basis)
    where_extra, params = build_where(
        filters,
        date_column="transaction_date",
        vehicle_type_column="vehicle_type",
        day_of_week_column="day_of_week",
    )
    rows = await conn.fetch(
        f"""
        WITH filtered AS (
            SELECT transaction_date, transaction_hour, ticket_quantity
            FROM eparking.dashboard_transactions
            WHERE {base_predicate}{where_extra}
        ),
        day_count AS (
            SELECT GREATEST(COUNT(DISTINCT transaction_date), 1) AS n_days
            FROM filtered
        ),
        hours AS (
            SELECT generate_series(0, 23) AS hour
        )
        SELECT
            hours.hour,
            COALESCE(SUM(filtered.ticket_quantity), 0) AS total_count,
            COALESCE(SUM(filtered.ticket_quantity), 0)::numeric / day_count.n_days AS avg_count
        FROM hours
        CROSS JOIN day_count
        LEFT JOIN filtered ON filtered.transaction_hour = hours.hour
        GROUP BY hours.hour, day_count.n_days
        ORDER BY hours.hour
        """,
        *params,
    )
    return [
        {
            "hour": r["hour"],
            "total_count": r["total_count"],
            "avg_count": round(_to_float(r["avg_count"]), 2),
        }
        for r in rows
    ]


async def get_weekly_pattern(
    conn: asyncpg.Connection,
    *,
    filters: CommonFilters,
    entry_count_basis: str,
) -> list[dict]:
    base_predicate = _entry_predicate(entry_count_basis)
    where_extra, params = build_where(
        filters,
        date_column="transaction_date",
        vehicle_type_column="vehicle_type",
        day_of_week_column="day_of_week",
    )
    rows = await conn.fetch(
        f"""
        SELECT day_of_week, COALESCE(SUM(ticket_quantity), 0) AS entry_count
        FROM eparking.dashboard_transactions
        WHERE {base_predicate}{where_extra}
        GROUP BY day_of_week
        ORDER BY day_of_week
        """,
        *params,
    )
    return [{"day_of_week": r["day_of_week"], "entry_count": r["entry_count"]} for r in rows]


async def get_today_vehicle_count(
    conn: asyncpg.Connection,
    *,
    today: date,
    entry_count_basis: str,
) -> dict:
    """Total Vehicles Today -- pinned to the business-timezone `today`
    regardless of any date filter param (Sprint 5 explicit requirement)."""
    base_predicate = _entry_predicate(entry_count_basis)
    row = await conn.fetchrow(
        f"""
        SELECT COALESCE(SUM(ticket_quantity), 0) AS vehicle_count
        FROM eparking.dashboard_transactions
        WHERE {base_predicate} AND transaction_date = $1
        """,
        today,
    )
    return {
        "date": today,
        "vehicle_count": row["vehicle_count"],
        "entry_count_basis": entry_count_basis,
    }


async def get_vehicle_type_distribution(
    conn: asyncpg.Connection,
    *,
    filters: CommonFilters,
    today: date | None = None,
    window: str = "range",
) -> list[dict]:
    """Shared by Overview and Traffic -- `window=range` uses the from/to
    filter, `window=today` pins to the business-timezone `today` regardless
    of the date filter (mirrors /api/traffic/today's pinning rule).
    """
    clauses = ["status = 'success'", "is_revenue = true", "vehicle_type IS NOT NULL"]
    params: list = []
    idx = 1

    if window == "today":
        clauses.append(f"transaction_date = ${idx}")
        params.append(today)
        idx += 1
    else:
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

    if filters.vehicle_types:
        clauses.append(f"vehicle_type = ANY(${idx}::text[])")
        params.append(list(filters.vehicle_types))
        idx += 1

    where_sql = " AND ".join(clauses)
    rows = await conn.fetch(
        f"""
        -- Vehicle counts, so batched multi-vehicle rows contribute their full
        -- quantity (₦900 = 3 Car). Keeps this consistent with entry_count and
        -- daily_revenue.ticket_count, which also count vehicles, not rows.
        SELECT vehicle_type,
               COALESCE(SUM(ticket_quantity), 0) AS txn_count,
               SUM(amount) AS total_amount
        FROM eparking.dashboard_transactions
        WHERE {where_sql}
        GROUP BY vehicle_type
        ORDER BY txn_count DESC
        """,
        *params,
    )
    return [
        {
            "vehicle_type": r["vehicle_type"],
            "txn_count": r["txn_count"],
            "total_amount": _to_float(r["total_amount"]),
        }
        for r in rows
    ]
