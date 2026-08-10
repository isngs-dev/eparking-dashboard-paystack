"""Repository functions backing the `/admin/*` and `/api/ops/unmapped`
endpoints: `fee_categories` CRUD, `revenue_split_config` CRUD, the
raw_transactions date-range clamp used to scope auto-reclassify, and the
UNMAPPED transactions report.

Every write here is a thin wrapper around a plain INSERT/UPDATE -- the
EXCLUDE USING gist constraints on both tables (migrations 004/005) are the
actual source of truth for "is this a valid rule"; this module's job is only
to catch the resulting `asyncpg.ExclusionViolationError` and translate it
into a friendly, structured 409 rather than letting a raw Postgres error
(or FastAPI's default 500) leak to the caller. See `.claude/skills/
transform-classification/SKILL.md`: "don't work around the constraint, fix
the range."
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import asyncpg


def _decode_fee_category_row(row: dict) -> dict:
    """asyncpg has no jsonb codec registered on this pool (see cache.py's
    own manual json.dumps/loads pattern for the same reason), so
    `components` comes back as a raw JSON string, not a parsed
    list/dict -- decode it here, once, for every fee_categories read path."""
    out = dict(row)
    if isinstance(out.get("components"), str):
        out["components"] = json.loads(out["components"])
    return out


class ExclusionConflict(Exception):
    """Raised on an EXCLUDE USING gist violation, carrying the conflicting
    row(s) already in the table so the router can build a friendly 409."""

    def __init__(self, message: str, *, conflicting_rows: list[dict]):
        super().__init__(message)
        self.conflicting_rows = conflicting_rows


# --------------------------------------------------------------------------
# fee_categories
# --------------------------------------------------------------------------

_FEE_CATEGORY_COLUMNS = """
    id, code, revenue_stream, label, vehicle_type, amount_min, amount_max,
    counts_as_entry, is_revenue, components, is_provisional, known_limitation,
    priority, effective_from, effective_to
"""


async def list_fee_categories(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        f"SELECT {_FEE_CATEGORY_COLUMNS} FROM eparking.fee_categories ORDER BY amount_min, effective_from"
    )
    return [_decode_fee_category_row(dict(r)) for r in rows]


async def get_fee_category(conn: asyncpg.Connection, fee_category_id: int) -> dict | None:
    row = await conn.fetchrow(
        f"SELECT {_FEE_CATEGORY_COLUMNS} FROM eparking.fee_categories WHERE id = $1",
        fee_category_id,
    )
    return _decode_fee_category_row(dict(row)) if row else None


async def _find_overlapping_fee_categories(
    conn: asyncpg.Connection,
    *,
    exclude_id: int | None,
    amount_min: Any,
    amount_max: Any,
    effective_from: date,
    effective_to: date | None,
) -> list[dict]:
    """Best-effort lookup of the row(s) that would conflict, for the 409
    payload. Run *after* the EXCLUDE violation is caught (not as a
    check-then-insert race-prone pre-check) -- this is purely to make the
    error message useful, the DB constraint is still what actually decides."""
    rows = await conn.fetch(
        f"""
        SELECT {_FEE_CATEGORY_COLUMNS} FROM eparking.fee_categories
        WHERE ($1::bigint IS NULL OR id <> $1)
          AND numrange(amount_min, amount_max, '[]') && numrange($2::numeric, $3::numeric, '[]')
          AND daterange(effective_from, effective_to, '[]')
              && daterange($4::date, $5::date, '[]')
        """,
        exclude_id,
        amount_min,
        amount_max,
        effective_from,
        effective_to,
    )
    return [dict(r) for r in rows]


async def create_fee_category(conn: asyncpg.Connection, payload: dict) -> dict:
    try:
        row = await conn.fetchrow(
            f"""
            INSERT INTO eparking.fee_categories
                (code, revenue_stream, label, vehicle_type, amount_min, amount_max,
                 counts_as_entry, is_revenue, components, is_provisional, known_limitation,
                 priority, effective_from, effective_to)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING {_FEE_CATEGORY_COLUMNS}
            """,
            payload["code"],
            payload["revenue_stream"],
            payload["label"],
            payload.get("vehicle_type"),
            payload["amount_min"],
            payload["amount_max"],
            payload["counts_as_entry"],
            payload["is_revenue"],
            json.dumps(payload["components"]) if payload.get("components") is not None else None,
            payload.get("is_provisional", False),
            payload.get("known_limitation"),
            payload.get("priority", 100),
            payload["effective_from"],
            payload.get("effective_to"),
        )
    except asyncpg.ExclusionViolationError as exc:
        conflicting = await _find_overlapping_fee_categories(
            conn,
            exclude_id=None,
            amount_min=payload["amount_min"],
            amount_max=payload["amount_max"],
            effective_from=payload["effective_from"],
            effective_to=payload.get("effective_to"),
        )
        raise ExclusionConflict(str(exc), conflicting_rows=conflicting) from exc
    return _decode_fee_category_row(dict(row))


async def update_fee_category(conn: asyncpg.Connection, fee_category_id: int, patch: dict) -> dict | None:
    existing = await get_fee_category(conn, fee_category_id)
    if existing is None:
        return None

    # `patch` is already the caller's `model_dump(exclude_unset=True)` --
    # every *key present* should override the existing value, including an
    # explicit `None` (e.g. clearing `effective_to` back to open-ended, or
    # `known_limitation`/`vehicle_type`/`components` back to NULL). Only
    # keys genuinely absent from the PATCH body fall back to `existing`.
    merged = {**existing, **patch}

    try:
        row = await conn.fetchrow(
            f"""
            UPDATE eparking.fee_categories SET
                code = $2, revenue_stream = $3, label = $4, vehicle_type = $5,
                amount_min = $6, amount_max = $7, counts_as_entry = $8, is_revenue = $9,
                components = $10, is_provisional = $11, known_limitation = $12,
                priority = $13, effective_from = $14, effective_to = $15
            WHERE id = $1
            RETURNING {_FEE_CATEGORY_COLUMNS}
            """,
            fee_category_id,
            merged["code"],
            merged["revenue_stream"],
            merged["label"],
            merged["vehicle_type"],
            merged["amount_min"],
            merged["amount_max"],
            merged["counts_as_entry"],
            merged["is_revenue"],
            json.dumps(merged["components"]) if merged.get("components") is not None else None,
            merged["is_provisional"],
            merged["known_limitation"],
            merged["priority"],
            merged["effective_from"],
            merged["effective_to"],
        )
    except asyncpg.ExclusionViolationError as exc:
        conflicting = await _find_overlapping_fee_categories(
            conn,
            exclude_id=fee_category_id,
            amount_min=merged["amount_min"],
            amount_max=merged["amount_max"],
            effective_from=merged["effective_from"],
            effective_to=merged["effective_to"],
        )
        raise ExclusionConflict(str(exc), conflicting_rows=conflicting) from exc
    return _decode_fee_category_row(dict(row))


# --------------------------------------------------------------------------
# revenue_split_config
# --------------------------------------------------------------------------

_SPLIT_COLUMNS = "id, aicl_pct, gsds_pct, effective_from, effective_to"


async def list_revenue_split_config(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        f"SELECT {_SPLIT_COLUMNS} FROM eparking.revenue_split_config ORDER BY effective_from"
    )
    return [dict(r) for r in rows]


async def _find_overlapping_split_config(
    conn: asyncpg.Connection, *, effective_from: date, effective_to: date | None
) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT {_SPLIT_COLUMNS} FROM eparking.revenue_split_config
        WHERE daterange(effective_from, effective_to, '[]')
              && daterange($1::date, $2::date, '[]')
        """,
        effective_from,
        effective_to,
    )
    return [dict(r) for r in rows]


async def create_revenue_split_config(conn: asyncpg.Connection, payload: dict) -> dict:
    try:
        row = await conn.fetchrow(
            f"""
            INSERT INTO eparking.revenue_split_config
                (aicl_pct, gsds_pct, effective_from, effective_to)
            VALUES ($1, $2, $3, $4)
            RETURNING {_SPLIT_COLUMNS}
            """,
            payload["aicl_pct"],
            payload["gsds_pct"],
            payload["effective_from"],
            payload.get("effective_to"),
        )
    except asyncpg.ExclusionViolationError as exc:
        conflicting = await _find_overlapping_split_config(
            conn,
            effective_from=payload["effective_from"],
            effective_to=payload.get("effective_to"),
        )
        raise ExclusionConflict(str(exc), conflicting_rows=conflicting) from exc
    except asyncpg.CheckViolationError as exc:
        raise ExclusionConflict(
            f"aicl_pct + gsds_pct must equal 1.0 (got {payload['aicl_pct']} + {payload['gsds_pct']})",
            conflicting_rows=[],
        ) from exc
    return dict(row)


# --------------------------------------------------------------------------
# raw_transactions date-range clamp (for auto-reclassify scoping)
# --------------------------------------------------------------------------


async def clamp_to_raw_transactions_range(
    conn: asyncpg.Connection,
    *,
    requested_from: date,
    requested_to: date,
) -> tuple[date, date] | None:
    """Clamp `[requested_from, requested_to]` to what's actually present in
    `raw_transactions` (by business-tz transaction date, matching
    `dashboard_transactions.transaction_date` semantics via `paid_at`).
    Returns None if there is no overlap at all (nothing to reclassify).
    """
    row = await conn.fetchrow(
        """
        SELECT
            min((paid_at AT TIME ZONE tz.business_tz)::date) AS min_date,
            max((paid_at AT TIME ZONE tz.business_tz)::date) AS max_date
        FROM eparking.raw_transactions
        CROSS JOIN LATERAL (
            SELECT COALESCE(
                (SELECT value FROM eparking.app_settings WHERE key = 'business_timezone'),
                'Africa/Lagos'
            ) AS business_tz
        ) tz
        WHERE paid_at IS NOT NULL
          AND (paid_at AT TIME ZONE tz.business_tz)::date BETWEEN $1 AND $2
        """,
        requested_from,
        requested_to,
    )
    if row is None or row["min_date"] is None:
        return None
    clamped_from = max(requested_from, row["min_date"])
    clamped_to = min(requested_to, row["max_date"])
    return clamped_from, clamped_to


async def get_raw_transactions_extent(conn: asyncpg.Connection) -> tuple[date, date] | None:
    """Full min/max business-tz transaction date range present in
    raw_transactions -- used to scope an auto-reclassify to "all dates this
    category could have applied to" when effective_to is NULL (open-ended)."""
    row = await conn.fetchrow(
        """
        SELECT
            min((paid_at AT TIME ZONE tz.business_tz)::date) AS min_date,
            max((paid_at AT TIME ZONE tz.business_tz)::date) AS max_date
        FROM eparking.raw_transactions
        CROSS JOIN LATERAL (
            SELECT COALESCE(
                (SELECT value FROM eparking.app_settings WHERE key = 'business_timezone'),
                'Africa/Lagos'
            ) AS business_tz
        ) tz
        WHERE paid_at IS NOT NULL
        """
    )
    if row is None or row["min_date"] is None:
        return None
    return row["min_date"], row["max_date"]


# --------------------------------------------------------------------------
# run_logs lookup (for correlating an enqueued reclassify with its run id)
# --------------------------------------------------------------------------


async def find_recent_reclassify_run(
    conn: asyncpg.Connection, *, window_from: date, window_to: date
) -> dict | None:
    """Best-effort lookup of the most recently started reclassify run_logs
    row whose window matches the requested clamped date range (by date, not
    exact timestamptz, since the caller only has calendar dates), used to
    hand back a pollable run id in the 202 response shortly after enqueueing
    (see auto_reclassify.py's polling retry loop -- this function itself
    does not wait). Narrowed to a recent time bound (last 2 minutes) so a
    long-past run over the same calendar dates is never mistaken for the
    one just enqueued.
    """
    row = await conn.fetchrow(
        """
        WITH tz AS (
            SELECT COALESCE(
                (SELECT value FROM eparking.app_settings WHERE key = 'business_timezone'),
                'Africa/Lagos'
            ) AS business_tz
        )
        SELECT rl.id, rl.run_type, rl.status, rl.window_from, rl.window_to, rl.rows_upserted,
               rl.error_message, rl.started_at, rl.finished_at
        FROM eparking.run_logs rl
        CROSS JOIN tz
        WHERE rl.run_type = 'reclassify'
          AND rl.started_at >= now() - interval '2 minutes'
          AND (rl.window_from AT TIME ZONE tz.business_tz)::date = $1
          AND (rl.window_to AT TIME ZONE tz.business_tz)::date = $2
        ORDER BY rl.started_at DESC
        LIMIT 1
        """,
        window_from,
        window_to,
    )
    return dict(row) if row else None


async def get_run_log(conn: asyncpg.Connection, run_id: int) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT id, run_type, status, window_from, window_to, rows_fetched,
               rows_upserted, error_message, started_at, finished_at
        FROM eparking.run_logs
        WHERE id = $1
        """,
        run_id,
    )
    return dict(row) if row else None


# --------------------------------------------------------------------------
# UNMAPPED transactions report
# --------------------------------------------------------------------------


async def list_unmapped_transactions(
    conn: asyncpg.Connection,
    *,
    date_from: date | None,
    date_to: date | None,
    limit: int,
) -> list[dict]:
    """dashboard_transactions rows classified as UNMAPPED (fee_category_code
    = 'UNMAPPED'), for the admin operational review report. Ordered newest
    first so a recurring new amount is easy to spot at the top."""
    rows = await conn.fetch(
        """
        SELECT
            paystack_transaction_id, reference, amount, status, channel,
            terminal_serial, location_name, paid_at, transaction_date
        FROM eparking.dashboard_transactions
        WHERE fee_category_code = 'UNMAPPED'
          AND ($1::date IS NULL OR transaction_date >= $1)
          AND ($2::date IS NULL OR transaction_date <= $2)
        ORDER BY paid_at DESC NULLS LAST
        LIMIT $3
        """,
        date_from,
        date_to,
        limit,
    )
    return [dict(r) for r in rows]


async def summarize_unmapped_amounts(
    conn: asyncpg.Connection, *, date_from: date | None, date_to: date | None
) -> list[dict]:
    """Amount-grouped summary -- the leading signal of a missing price tier
    or unconfirmed bundle per CLAUDE.md ("a recurring unmapped amount is the
    leading signal of a new bundle or price change")."""
    rows = await conn.fetch(
        """
        SELECT amount, COUNT(*) AS txn_count, MIN(transaction_date) AS first_seen,
               MAX(transaction_date) AS last_seen
        FROM eparking.dashboard_transactions
        WHERE fee_category_code = 'UNMAPPED'
          AND ($1::date IS NULL OR transaction_date >= $1)
          AND ($2::date IS NULL OR transaction_date <= $2)
        GROUP BY amount
        ORDER BY txn_count DESC, amount
        """,
        date_from,
        date_to,
    )
    return [dict(r) for r in rows]
