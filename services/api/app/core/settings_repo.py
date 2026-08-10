"""Reads from `eparking.app_settings` -- business timezone and
entry_count_basis are query-time settings, never hardcoded (see CLAUDE.md and
the transform-classification skill). Every occupancy/traffic endpoint that
needs "today" or the entry-count basis goes through here.
"""

from __future__ import annotations

from datetime import date

import asyncpg

_DEFAULT_BUSINESS_TIMEZONE = "Africa/Lagos"
_DEFAULT_ENTRY_COUNT_BASIS = "ticket_only"


async def get_business_timezone(conn: asyncpg.Connection) -> str:
    row = await conn.fetchrow(
        "SELECT value FROM eparking.app_settings WHERE key = 'business_timezone'"
    )
    return row["value"] if row else _DEFAULT_BUSINESS_TIMEZONE


async def get_entry_count_basis(conn: asyncpg.Connection) -> str:
    row = await conn.fetchrow(
        "SELECT value FROM eparking.app_settings WHERE key = 'entry_count_basis'"
    )
    return row["value"] if row else _DEFAULT_ENTRY_COUNT_BASIS


async def get_today(conn: asyncpg.Connection) -> date:
    """"Today" in the business timezone -- matches how `transaction_date` was
    bucketed at transform time, so date-window math lines up with the data.
    """
    tz = await get_business_timezone(conn)
    row = await conn.fetchrow("SELECT (now() AT TIME ZONE $1)::date AS today", tz)
    return row["today"]
