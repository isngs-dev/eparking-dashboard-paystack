"""Global filter endpoint(s) -- populates the frontend's filter controls."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.core.auth import require_viewer_or_admin
from app.core.cache import cache_key, get_swr
from app.core.db import get_pool
from app.core.filters import get_valid_vehicle_types
from app.core.ttl import FILTERS_HARD_TTL, FILTERS_SOFT_TTL
from app.models.responses import VehicleTypesFilterResponse

router = APIRouter(prefix="/api/filters", tags=["filters"])


@router.get("/vehicle-types", response_model=VehicleTypesFilterResponse)
async def vehicle_types(
    response: Response, _role: str = Depends(require_viewer_or_admin)
) -> VehicleTypesFilterResponse:
    """Distinct vehicle_type values from fee_categories, for the global
    filter control.
    """
    pool = get_pool()
    key = cache_key("filters_vehicle_types", {})

    async def loader() -> dict:
        async with pool.acquire() as conn:
            values = await get_valid_vehicle_types(conn)
        return {"vehicle_types": sorted(values)}

    result = await get_swr(
        key, soft_ttl_seconds=FILTERS_SOFT_TTL, hard_ttl_seconds=FILTERS_HARD_TTL, loader=loader
    )
    response.headers["X-Cache"] = result.status
    return VehicleTypesFilterResponse(**result.value)
