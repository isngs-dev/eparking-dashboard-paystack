"""Executive Overview endpoints: KPI summary, revenue trend, vehicle-type
distribution (shared with Traffic).
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Response

from app.core.auth import require_viewer_or_admin
from app.core.cache import cache_key, get_swr
from app.core.date_windows import revenue_kpi_windows
from app.core.db import get_pool
from app.core.filters import CommonFilters, parse_common_filters
from app.core.settings_repo import get_today
from app.core.ttl import STANDARD_HARD_TTL, STANDARD_SOFT_TTL
from app.models.responses import (
    DateRange,
    KPIWindow,
    OverviewSummaryResponse,
    RevenueTrendPoint,
    RevenueTrendResponse,
    VehicleTypeDistributionItem,
    VehicleTypeDistributionResponse,
)
from app.repositories import occupancy as occupancy_repo
from app.repositories import revenue as revenue_repo

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview/summary", response_model=OverviewSummaryResponse)
async def overview_summary(
    response: Response, _role: str = Depends(require_viewer_or_admin)
) -> OverviewSummaryResponse:
    """Daily/Weekly/Monthly KPIs, each carrying its own explicit labeled date
    range so the frontend can never present them ambiguously (fixes the old
    dashboard's Daily > Monthly bug -- see api-layer skill).

    Each window ends today in the business timezone. Daily is today only,
    Weekly is Monday-to-today, and Monthly is the first of the month through
    today. They are not affected by from/to filters: each KPI has a fixed,
    explicit calendar-to-date definition.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        today = await get_today(conn)
    key = cache_key("overview_summary", {"today": today.isoformat()})

    async def loader() -> dict:
        async with pool.acquire() as conn:
            windows = revenue_kpi_windows(today)
            out = {}
            for key_name, (date_from, date_to, label) in windows.items():
                totals = await revenue_repo.sum_window(
                    conn, date_from=date_from, date_to=date_to
                )
                prior_total_collection = await revenue_repo.get_prior_period_total_collection(
                    conn, date_from=date_from, date_to=date_to
                )
                out[key_name] = {
                    "label": label,
                    "date_range": {
                        "date_from": date_from.isoformat(),
                        "date_to": date_to.isoformat(),
                        "label": label,
                    },
                    "total_collection": totals["total_collection"],
                    "ticket_amount": totals["ticket_amount"],
                    "card_total_amount": totals["card_total_amount"],
                    "transaction_count_total": totals["transaction_count_total"],
                    "ticket_count": totals["ticket_count"],
                    "prior_period_total_collection": prior_total_collection,
                    "delta_pct": revenue_repo.compute_delta_pct(
                        totals["total_collection"], prior_total_collection
                    ),
                }
            return out

    result = await get_swr(
        key,
        soft_ttl_seconds=STANDARD_SOFT_TTL,
        hard_ttl_seconds=STANDARD_HARD_TTL,
        loader=loader,
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return OverviewSummaryResponse(
        daily=KPIWindow(**v["daily"]),
        weekly=KPIWindow(**v["weekly"]),
        monthly=KPIWindow(**v["monthly"]),
    )


@router.get("/overview/revenue-trend", response_model=RevenueTrendResponse)
async def revenue_trend(
    response: Response,
    filters: CommonFilters = Depends(parse_common_filters),
    _role: str = Depends(require_viewer_or_admin),
) -> RevenueTrendResponse:
    """Day-grain series from `daily_revenue`, zero-filled for gap days."""
    pool = get_pool()

    async with pool.acquire() as conn:
        today = await get_today(conn)
    date_from = filters.date_from or (today - timedelta(days=29))
    date_to = filters.date_to or today

    key = cache_key(
        "revenue_trend",
        {"from": date_from.isoformat(), "to": date_to.isoformat()},
    )

    async def loader() -> dict:
        async with pool.acquire() as conn:
            rows = await revenue_repo.get_daily_revenue_range(
                conn, date_from=date_from, date_to=date_to
            )
        filled = revenue_repo.zero_fill(
            [
                {
                    "revenue_date": r["revenue_date"],
                    "ticket_amount": revenue_repo.to_float(r["ticket_amount"]),
                    "card_total_amount": revenue_repo.to_float(r["card_total_amount"]),
                    "total_collection": revenue_repo.to_float(r["total_collection"]),
                    "transaction_count_total": r["transaction_count_total"],
                }
                for r in rows
            ],
            date_from=date_from,
            date_to=date_to,
            date_key="revenue_date",
            zero_template={
                "ticket_amount": 0.0,
                "card_total_amount": 0.0,
                "total_collection": 0.0,
                "transaction_count_total": 0,
            },
        )
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "points": [
                {
                    "date": p["revenue_date"].isoformat()
                    if hasattr(p["revenue_date"], "isoformat")
                    else p["revenue_date"],
                    "ticket_amount": p["ticket_amount"],
                    "card_total_amount": p["card_total_amount"],
                    "total_collection": p["total_collection"],
                    "transaction_count_total": p["transaction_count_total"],
                }
                for p in filled
            ],
        }

    result = await get_swr(
        key,
        soft_ttl_seconds=STANDARD_SOFT_TTL,
        hard_ttl_seconds=STANDARD_HARD_TTL,
        loader=loader,
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return RevenueTrendResponse(
        date_range=DateRange(
            date_from=v["date_from"], date_to=v["date_to"], label="Revenue trend range"
        ),
        points=[RevenueTrendPoint(**p) for p in v["points"]],
    )


@router.get("/vehicle-types/distribution", response_model=VehicleTypeDistributionResponse)
async def vehicle_types_distribution(
    response: Response,
    window: str = Query("range", pattern="^(range|today)$"),
    filters: CommonFilters = Depends(parse_common_filters),
    _role: str = Depends(require_viewer_or_admin),
) -> VehicleTypeDistributionResponse:
    """Shared by Overview and Traffic -- `window=range` uses from/to filter
    (defaulting to trailing 30 days), `window=today` pins to business-tz
    today regardless of the date filter.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        today = await get_today(conn)

    if window == "today":
        date_from = date_to = today
    else:
        date_from = filters.date_from or (today - timedelta(days=29))
        date_to = filters.date_to or today

    effective_filters = CommonFilters(
        date_from=date_from,
        date_to=date_to,
        vehicle_types=filters.vehicle_types,
        days=filters.days,
    )
    key = cache_key(
        "vehicle_type_distribution",
        {"window": window, **effective_filters.cache_params()},
    )

    async def loader() -> dict:
        async with pool.acquire() as conn:
            items = await occupancy_repo.get_vehicle_type_distribution(
                conn, filters=effective_filters, today=today, window=window
            )
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "items": items,
        }

    result = await get_swr(
        key,
        soft_ttl_seconds=STANDARD_SOFT_TTL,
        hard_ttl_seconds=STANDARD_HARD_TTL,
        loader=loader,
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return VehicleTypeDistributionResponse(
        window=window,
        date_range=DateRange(
            date_from=v["date_from"], date_to=v["date_to"], label=f"window={window}"
        ),
        items=[VehicleTypeDistributionItem(**i) for i in v["items"]],
    )
