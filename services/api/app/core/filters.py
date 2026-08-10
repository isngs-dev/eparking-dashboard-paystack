"""Shared query-param parsing/validation for revenue/occupancy/traffic endpoints.

Every list/aggregate endpoint accepts `from`, `to`, `vehicle_types`,
`days` (see `.claude/skills/api-layer/SKILL.md`). `vehicle_types` and `days`
are allowlisted against real DB values / `1..7` and rejected with 422 --
never silently dropped or passed through to SQL unchecked (explicit
acceptance criterion in `.claude/sprints/05_API_LAYER.md`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import asyncpg
from fastapi import HTTPException, Query

from app.core.db import get_pool

_VALID_DAYS = set(range(1, 8))


@dataclass(frozen=True)
class CommonFilters:
    date_from: date | None
    date_to: date | None
    vehicle_types: tuple[str, ...] | None
    days: tuple[int, ...] | None

    def cache_params(self) -> dict:
        return {
            "from": self.date_from.isoformat() if self.date_from else None,
            "to": self.date_to.isoformat() if self.date_to else None,
            "vehicle_types": sorted(self.vehicle_types) if self.vehicle_types else None,
            "days": sorted(self.days) if self.days else None,
        }


async def get_valid_vehicle_types(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch(
        "SELECT DISTINCT vehicle_type FROM eparking.fee_categories "
        "WHERE vehicle_type IS NOT NULL"
    )
    return {r["vehicle_type"] for r in rows}


def _parse_vehicle_types(raw: str | None) -> tuple[str, ...] | None:
    if raw is None or raw.strip() == "":
        return None
    return tuple(v.strip() for v in raw.split(",") if v.strip())


def _parse_days(raw: str | None) -> tuple[int, ...] | None:
    if raw is None or raw.strip() == "":
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    parsed: list[int] = []
    for p in parts:
        try:
            parsed.append(int(p))
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid 'days' value {p!r}: must be an integer 1-7 "
                "(1=Monday .. 7=Sunday).",
            ) from exc
    return tuple(parsed)


async def parse_common_filters(
    *,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    vehicle_types: str | None = Query(
        None, description="Comma-separated list of vehicle_type values."
    ),
    days: str | None = Query(
        None, description="Comma-separated list of day-of-week ints, 1-7 (1=Mon..7=Sun)."
    ),
) -> CommonFilters:
    """FastAPI dependency -- acquires its own connection from the shared pool
    (rather than taking one as a param) so it's directly usable via
    `Depends(parse_common_filters)` without FastAPI trying to treat
    `asyncpg.Connection` as a request parameter/response field.
    """
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail=f"'from' ({date_from.isoformat()}) must not be after "
            f"'to' ({date_to.isoformat()}).",
        )

    parsed_vehicle_types = _parse_vehicle_types(vehicle_types)
    if parsed_vehicle_types is not None:
        pool = get_pool()
        async with pool.acquire() as conn:
            valid = await get_valid_vehicle_types(conn)
        invalid = [v for v in parsed_vehicle_types if v not in valid]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid vehicle_types value(s): {invalid}. "
                f"Valid values: {sorted(valid)}.",
            )

    parsed_days = _parse_days(days)
    if parsed_days is not None:
        invalid_days = [d for d in parsed_days if d not in _VALID_DAYS]
        if invalid_days:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid days value(s): {invalid_days}. Must be 1-7 "
                "(1=Monday .. 7=Sunday).",
            )

    return CommonFilters(
        date_from=date_from,
        date_to=date_to,
        vehicle_types=parsed_vehicle_types,
        days=parsed_days,
    )


def default_range(days_back: int, *, today: date) -> tuple[date, date]:
    """Trailing N-day window ending today (inclusive), used when no explicit
    from/to is supplied."""
    return today - timedelta(days=days_back - 1), today
