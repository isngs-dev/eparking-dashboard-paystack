"""Executive Overview revenue endpoints not already covered by overview.py:
card sales (breakdown/total), daily-by-tier tickets, total collection, and
the AICL/GSDS split.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Response

from app.core.auth import require_viewer_or_admin
from app.core.cache import cache_key, get_swr
from app.core.db import get_pool
from app.core.filters import CommonFilters, parse_common_filters
from app.core.settings_repo import get_today
from app.core.ttl import STANDARD_HARD_TTL, STANDARD_SOFT_TTL
from app.models.responses import (
    CardBreakdownDayPoint,
    CardBreakdownResponse,
    CardTotalResponse,
    DateRange,
    RevenueSplitResponse,
    TicketDailyByTierResponse,
    TicketTierDayPoint,
    TotalCollectionResponse,
)
from app.repositories import revenue as revenue_repo

router = APIRouter(prefix="/api", tags=["revenue"])


def _resolve_range(filters: CommonFilters, today) -> tuple:
    date_from = filters.date_from or (today - timedelta(days=29))
    date_to = filters.date_to or today
    return date_from, date_to


@router.get("/cards/breakdown", response_model=CardBreakdownResponse)
async def cards_breakdown(
    response: Response,
    filters: CommonFilters = Depends(parse_common_filters),
    _role: str = Depends(require_viewer_or_admin),
) -> CardBreakdownResponse:
    """Card sales by day x Annual/Monthly. The bundled 12,500 charge
    contributes to both series via card_component_annual/monthly columns
    (CLAUDE.md rule #2).
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        today = await get_today(conn)
    date_from, date_to = _resolve_range(filters, today)

    effective_filters = CommonFilters(
        date_from=date_from,
        date_to=date_to,
        vehicle_types=filters.vehicle_types,
        days=filters.days,
    )
    key = cache_key("cards_breakdown", effective_filters.cache_params())

    async def loader() -> dict:
        async with pool.acquire() as conn:
            rows = await revenue_repo.get_card_breakdown_by_day(
                conn, filters=effective_filters
            )
        filled = revenue_repo.zero_fill(
            rows,
            date_from=date_from,
            date_to=date_to,
            date_key="date",
            zero_template={
                "annual_count": 0,
                "annual_amount": 0.0,
                "monthly_count": 0,
                "monthly_amount": 0.0,
            },
        )
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "points": [
                {
                    "date": p["date"].isoformat() if hasattr(p["date"], "isoformat") else p["date"],
                    "annual_count": p["annual_count"],
                    "annual_amount": p["annual_amount"],
                    "monthly_count": p["monthly_count"],
                    "monthly_amount": p["monthly_amount"],
                }
                for p in filled
            ],
        }

    result = await get_swr(
        key, soft_ttl_seconds=STANDARD_SOFT_TTL, hard_ttl_seconds=STANDARD_HARD_TTL, loader=loader
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return CardBreakdownResponse(
        date_range=DateRange(
            date_from=v["date_from"], date_to=v["date_to"], label="Card breakdown range"
        ),
        points=[CardBreakdownDayPoint(**p) for p in v["points"]],
    )


@router.get("/cards/total", response_model=CardTotalResponse)
async def cards_total(
    response: Response,
    filters: CommonFilters = Depends(parse_common_filters),
    _role: str = Depends(require_viewer_or_admin),
) -> CardTotalResponse:
    """Total Card Sale KPI -- sums card_component_annual/monthly across the
    range so the 12,500 bundle is correctly split between sub-types.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        today = await get_today(conn)
    date_from, date_to = _resolve_range(filters, today)

    effective_filters = CommonFilters(
        date_from=date_from,
        date_to=date_to,
        vehicle_types=filters.vehicle_types,
        days=filters.days,
    )
    key = cache_key("cards_total", effective_filters.cache_params())

    async def loader() -> dict:
        async with pool.acquire() as conn:
            rows = await revenue_repo.get_card_breakdown_by_day(
                conn, filters=effective_filters
            )
        annual_count = sum(r["annual_count"] for r in rows)
        annual_amount = sum(r["annual_amount"] for r in rows)
        monthly_count = sum(r["monthly_count"] for r in rows)
        monthly_amount = sum(r["monthly_amount"] for r in rows)
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "card_total_amount": annual_amount + monthly_amount,
            "annual_amount": annual_amount,
            "monthly_amount": monthly_amount,
            "annual_count": annual_count,
            "monthly_count": monthly_count,
        }

    result = await get_swr(
        key, soft_ttl_seconds=STANDARD_SOFT_TTL, hard_ttl_seconds=STANDARD_HARD_TTL, loader=loader
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return CardTotalResponse(
        date_range=DateRange(
            date_from=v["date_from"], date_to=v["date_to"], label="Card total range"
        ),
        card_total_amount=v["card_total_amount"],
        annual_amount=v["annual_amount"],
        monthly_amount=v["monthly_amount"],
        annual_count=v["annual_count"],
        monthly_count=v["monthly_count"],
    )


@router.get("/tickets/daily-by-tier", response_model=TicketDailyByTierResponse)
async def tickets_daily_by_tier(
    response: Response,
    filters: CommonFilters = Depends(parse_common_filters),
    _role: str = Depends(require_viewer_or_admin),
) -> TicketDailyByTierResponse:
    """Daily Ticket Collection, day x tier, feeds the stacked bar."""
    pool = get_pool()
    async with pool.acquire() as conn:
        today = await get_today(conn)
    date_from, date_to = _resolve_range(filters, today)

    effective_filters = CommonFilters(
        date_from=date_from,
        date_to=date_to,
        vehicle_types=filters.vehicle_types,
        days=filters.days,
    )
    key = cache_key("tickets_daily_by_tier", effective_filters.cache_params())

    async def loader() -> dict:
        async with pool.acquire() as conn:
            rows = await revenue_repo.get_ticket_daily_by_tier(
                conn, filters=effective_filters
            )
        # Not zero-filled per-tier (sparse day x tier combos are expected --
        # the stacked bar only needs the days/tiers that actually occurred;
        # zero-filling every tier for every day would misrepresent tiers that
        # never ran that day vs. tiers excluded by the vehicle_types filter).
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "points": [
                {
                    "date": r["date"].isoformat() if hasattr(r["date"], "isoformat") else r["date"],
                    "vehicle_type": r["vehicle_type"],
                    "ticket_count": r["ticket_count"],
                    "ticket_amount": r["ticket_amount"],
                }
                for r in rows
            ],
        }

    result = await get_swr(
        key, soft_ttl_seconds=STANDARD_SOFT_TTL, hard_ttl_seconds=STANDARD_HARD_TTL, loader=loader
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return TicketDailyByTierResponse(
        date_range=DateRange(
            date_from=v["date_from"], date_to=v["date_to"], label="Daily ticket collection range"
        ),
        points=[TicketTierDayPoint(**p) for p in v["points"]],
    )


@router.get("/revenue/total-collection", response_model=TotalCollectionResponse)
async def revenue_total_collection(
    response: Response,
    filters: CommonFilters = Depends(parse_common_filters),
    _role: str = Depends(require_viewer_or_admin),
) -> TotalCollectionResponse:
    """Filter-aware ticket revenue plus applicable untyped card revenue."""
    pool = get_pool()
    async with pool.acquire() as conn:
        today = await get_today(conn)
    date_from, date_to = _resolve_range(filters, today)
    effective_filters = CommonFilters(
        date_from=date_from,
        date_to=date_to,
        vehicle_types=filters.vehicle_types,
        days=filters.days,
    )

    key = cache_key("revenue_total_collection_v2", effective_filters.cache_params())

    async def loader() -> dict:
        async with pool.acquire() as conn:
            totals = await revenue_repo.get_filtered_revenue_totals(
                conn, filters=effective_filters
            )
            prior_from, prior_to = revenue_repo.prior_period_range(date_from, date_to)
            prior_totals = await revenue_repo.get_filtered_revenue_totals(
                conn,
                filters=CommonFilters(
                    date_from=prior_from,
                    date_to=prior_to,
                    vehicle_types=filters.vehicle_types,
                    days=filters.days,
                ),
            )
            prior_total_collection = prior_totals["total_collection"]
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "total_collection": totals["total_collection"],
            "ticket_amount": totals["ticket_amount"],
            "card_total_amount": totals["card_total_amount"],
            "prior_period_total_collection": prior_total_collection,
            "delta_pct": revenue_repo.compute_delta_pct(
                totals["total_collection"], prior_total_collection
            ),
        }

    result = await get_swr(
        key, soft_ttl_seconds=STANDARD_SOFT_TTL, hard_ttl_seconds=STANDARD_HARD_TTL, loader=loader
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return TotalCollectionResponse(
        date_range=DateRange(
            date_from=v["date_from"], date_to=v["date_to"], label="Total collection range"
        ),
        total_collection=v["total_collection"],
        ticket_amount=v["ticket_amount"],
        card_total_amount=v["card_total_amount"],
        prior_period_total_collection=v["prior_period_total_collection"],
        delta_pct=v["delta_pct"],
    )


@router.get("/revenue/split", response_model=RevenueSplitResponse)
async def revenue_split(
    response: Response,
    filters: CommonFilters = Depends(parse_common_filters),
    _role: str = Depends(require_viewer_or_admin),
) -> RevenueSplitResponse:
    """AICL/GSDS split recalculated from each filtered day's collection."""
    pool = get_pool()
    async with pool.acquire() as conn:
        today = await get_today(conn)
    date_from, date_to = _resolve_range(filters, today)
    effective_filters = CommonFilters(
        date_from=date_from,
        date_to=date_to,
        vehicle_types=filters.vehicle_types,
        days=filters.days,
    )

    key = cache_key("revenue_split_v2", effective_filters.cache_params())

    async def loader() -> dict:
        async with pool.acquire() as conn:
            split = await revenue_repo.get_filtered_revenue_split(
                conn, filters=effective_filters
            )
        return {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            **split,
        }

    result = await get_swr(
        key, soft_ttl_seconds=STANDARD_SOFT_TTL, hard_ttl_seconds=STANDARD_HARD_TTL, loader=loader
    )
    response.headers["X-Cache"] = result.status
    v = result.value
    return RevenueSplitResponse(
        date_range=DateRange(
            date_from=v["date_from"], date_to=v["date_to"], label="Revenue split range"
        ),
        aicl_amount=v["aicl_amount"],
        gsds_amount=v["gsds_amount"],
        aicl_pct=v["aicl_pct"],
        gsds_pct=v["gsds_pct"],
        total_collection=v["total_collection"],
    )
