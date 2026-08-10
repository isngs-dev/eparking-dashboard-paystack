"""Traffic-page endpoints. Vehicle-type distribution and peak-hour-count
reuse the Overview/Occupancy endpoints (see api-layer skill) -- only the
today-pinned total lives here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.core.auth import require_viewer_or_admin
from app.core.cache import cache_key, get_swr
from app.core.db import get_pool
from app.core.settings_repo import get_entry_count_basis, get_today
from app.core.ttl import TRAFFIC_TODAY_HARD_TTL, TRAFFIC_TODAY_SOFT_TTL
from app.models.responses import TrafficTodayResponse
from app.repositories import occupancy as occupancy_repo

router = APIRouter(prefix="/api/traffic", tags=["traffic"])


@router.get("/today", response_model=TrafficTodayResponse)
async def traffic_today(
    response: Response, _role: str = Depends(require_viewer_or_admin)
) -> TrafficTodayResponse:
    """Total Vehicles Today -- pinned to today's date (business timezone)
    regardless of any date filter, per Sprint 5's explicit requirement.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        today = await get_today(conn)
        entry_count_basis = await get_entry_count_basis(conn)

    key = cache_key(
        "traffic_today", {"date": today.isoformat(), "basis": entry_count_basis}
    )

    async def loader() -> dict:
        async with pool.acquire() as conn:
            result = await occupancy_repo.get_today_vehicle_count(
                conn, today=today, entry_count_basis=entry_count_basis
            )
        return {
            "date": result["date"].isoformat(),
            "vehicle_count": result["vehicle_count"],
            "entry_count_basis": result["entry_count_basis"],
        }

    result = await get_swr(
        key,
        soft_ttl_seconds=TRAFFIC_TODAY_SOFT_TTL,
        hard_ttl_seconds=TRAFFIC_TODAY_HARD_TTL,
        loader=loader,
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return TrafficTodayResponse(
        date=v["date"], vehicle_count=v["vehicle_count"], entry_count_basis=v["entry_count_basis"]
    )
