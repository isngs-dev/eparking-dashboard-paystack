"""Occupancy-page endpoints: entry count, hourly histogram, peak-hours
(shared with Traffic), weekly pattern. Every function here respects
`app_settings.entry_count_basis` at query time (never hardcoded).
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Response

from app.core.auth import require_viewer_or_admin
from app.core.cache import cache_key, get_swr
from app.core.db import get_pool
from app.core.filters import CommonFilters, parse_common_filters
from app.core.settings_repo import get_entry_count_basis, get_today
from app.core.ttl import STANDARD_HARD_TTL, STANDARD_SOFT_TTL
from app.models.responses import (
    DateRange,
    EntryCountResponse,
    HourlyHistogramPoint,
    OccupancyByHourResponse,
    PeakHoursResponse,
    WeeklyPatternPoint,
    WeeklyPatternResponse,
)
from app.repositories import occupancy as occupancy_repo

router = APIRouter(prefix="/api/occupancy", tags=["occupancy"])


def _resolve_range(filters: CommonFilters, today) -> tuple:
    date_from = filters.date_from or (today - timedelta(days=29))
    date_to = filters.date_to or today
    return date_from, date_to


@router.get("/entry-count", response_model=EntryCountResponse)
async def entry_count(
    response: Response,
    filters: CommonFilters = Depends(parse_common_filters),
    _role: str = Depends(require_viewer_or_admin),
) -> EntryCountResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        today = await get_today(conn)
        entry_count_basis = await get_entry_count_basis(conn)
    date_from, date_to = _resolve_range(filters, today)

    effective_filters = CommonFilters(
        date_from=date_from,
        date_to=date_to,
        vehicle_types=filters.vehicle_types,
        days=filters.days,
    )
    key = cache_key(
        "occupancy_entry_count",
        {"basis": entry_count_basis, **effective_filters.cache_params()},
    )

    async def loader() -> dict:
        async with pool.acquire() as conn:
            result = await occupancy_repo.get_entry_count(
                conn, filters=effective_filters, entry_count_basis=entry_count_basis
            )
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "entry_count": result["entry_count"],
            "entry_count_basis": result["entry_count_basis"],
        }

    result = await get_swr(
        key, soft_ttl_seconds=STANDARD_SOFT_TTL, hard_ttl_seconds=STANDARD_HARD_TTL, loader=loader
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return EntryCountResponse(
        date_range=DateRange(
            date_from=v["date_from"], date_to=v["date_to"], label="Entry count range"
        ),
        entry_count=v["entry_count"],
        entry_count_basis=v["entry_count_basis"],
    )


@router.get("/by-hour", response_model=OccupancyByHourResponse)
async def by_hour(
    response: Response,
    filters: CommonFilters = Depends(parse_common_filters),
    _role: str = Depends(require_viewer_or_admin),
) -> OccupancyByHourResponse:
    """Hourly histogram 0-23, averaged per day across the range."""
    pool = get_pool()
    async with pool.acquire() as conn:
        today = await get_today(conn)
        entry_count_basis = await get_entry_count_basis(conn)
    date_from, date_to = _resolve_range(filters, today)

    effective_filters = CommonFilters(
        date_from=date_from,
        date_to=date_to,
        vehicle_types=filters.vehicle_types,
        days=filters.days,
    )
    key = cache_key(
        "occupancy_by_hour",
        {"basis": entry_count_basis, **effective_filters.cache_params()},
    )

    async def loader() -> dict:
        async with pool.acquire() as conn:
            points = await occupancy_repo.get_hourly_histogram(
                conn, filters=effective_filters, entry_count_basis=entry_count_basis
            )
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "entry_count_basis": entry_count_basis,
            "points": points,
        }

    result = await get_swr(
        key, soft_ttl_seconds=STANDARD_SOFT_TTL, hard_ttl_seconds=STANDARD_HARD_TTL, loader=loader
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return OccupancyByHourResponse(
        date_range=DateRange(
            date_from=v["date_from"], date_to=v["date_to"], label="Occupancy by hour range"
        ),
        entry_count_basis=v["entry_count_basis"],
        points=[HourlyHistogramPoint(**p) for p in v["points"]],
    )


@router.get("/peak-hours", response_model=PeakHoursResponse)
async def peak_hours(
    response: Response,
    filters: CommonFilters = Depends(parse_common_filters),
    _role: str = Depends(require_viewer_or_admin),
) -> PeakHoursResponse:
    """Peak/off-peak band + percentages, derived from the same hourly
    histogram used by /by-hour -- also serves Traffic's peak-hour-count
    field (shared logic, one computation, per the api-layer skill).

    Peak band defined as the 3 contiguous hours (a rolling 3-hour window)
    with the highest combined total_count -- a documented, reasonable
    definition since the spec does not pin down the exact band width.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        today = await get_today(conn)
        entry_count_basis = await get_entry_count_basis(conn)
    date_from, date_to = _resolve_range(filters, today)

    effective_filters = CommonFilters(
        date_from=date_from,
        date_to=date_to,
        vehicle_types=filters.vehicle_types,
        days=filters.days,
    )
    key = cache_key(
        "occupancy_peak_hours",
        {"basis": entry_count_basis, **effective_filters.cache_params()},
    )

    async def loader() -> dict:
        async with pool.acquire() as conn:
            hist = await occupancy_repo.get_hourly_histogram(
                conn, filters=effective_filters, entry_count_basis=entry_count_basis
            )
        total_count = sum(h["total_count"] for h in hist)
        if total_count == 0:
            return {
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "entry_count_basis": entry_count_basis,
                "peak_hour": None,
                "peak_hour_count": 0,
                "peak_band_start": None,
                "peak_band_end": None,
                "peak_band_pct": 0.0,
                "off_peak_pct": 0.0,
                "total_count": 0,
            }

        counts = [h["total_count"] for h in hist]
        peak_hour_idx = max(range(24), key=lambda h: counts[h])

        band_width = 3
        best_start = 0
        best_sum = -1
        for start in range(24):
            window_sum = sum(counts[(start + i) % 24] for i in range(band_width))
            if window_sum > best_sum:
                best_sum = window_sum
                best_start = start
        band_end = (best_start + band_width - 1) % 24

        peak_band_pct = round((best_sum / total_count) * 100, 2)
        off_peak_pct = round(100.0 - peak_band_pct, 2)

        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "entry_count_basis": entry_count_basis,
            "peak_hour": peak_hour_idx,
            "peak_hour_count": counts[peak_hour_idx],
            "peak_band_start": best_start,
            "peak_band_end": band_end,
            "peak_band_pct": peak_band_pct,
            "off_peak_pct": off_peak_pct,
            "total_count": total_count,
        }

    result = await get_swr(
        key, soft_ttl_seconds=STANDARD_SOFT_TTL, hard_ttl_seconds=STANDARD_HARD_TTL, loader=loader
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return PeakHoursResponse(
        date_range=DateRange(
            date_from=v["date_from"], date_to=v["date_to"], label="Peak hours range"
        ),
        entry_count_basis=v["entry_count_basis"],
        peak_hour=v["peak_hour"],
        peak_hour_count=v["peak_hour_count"],
        peak_band_start=v["peak_band_start"],
        peak_band_end=v["peak_band_end"],
        peak_band_pct=v["peak_band_pct"],
        off_peak_pct=v["off_peak_pct"],
        total_count=v["total_count"],
    )


@router.get("/weekly-pattern", response_model=WeeklyPatternResponse)
async def weekly_pattern(
    response: Response,
    filters: CommonFilters = Depends(parse_common_filters),
    _role: str = Depends(require_viewer_or_admin),
) -> WeeklyPatternResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        today = await get_today(conn)
        entry_count_basis = await get_entry_count_basis(conn)
    date_from, date_to = _resolve_range(filters, today)

    effective_filters = CommonFilters(
        date_from=date_from,
        date_to=date_to,
        vehicle_types=filters.vehicle_types,
        days=filters.days,
    )
    key = cache_key(
        "occupancy_weekly_pattern",
        {"basis": entry_count_basis, **effective_filters.cache_params()},
    )

    async def loader() -> dict:
        async with pool.acquire() as conn:
            points = await occupancy_repo.get_weekly_pattern(
                conn, filters=effective_filters, entry_count_basis=entry_count_basis
            )
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "entry_count_basis": entry_count_basis,
            "points": points,
        }

    result = await get_swr(
        key, soft_ttl_seconds=STANDARD_SOFT_TTL, hard_ttl_seconds=STANDARD_HARD_TTL, loader=loader
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return WeeklyPatternResponse(
        date_range=DateRange(
            date_from=v["date_from"], date_to=v["date_to"], label="Weekly pattern range"
        ),
        entry_count_basis=v["entry_count_basis"],
        points=[WeeklyPatternPoint(**p) for p in v["points"]],
    )
