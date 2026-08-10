"""Operational review reports. `/api/ops/unmapped` surfaces UNMAPPED-category
transactions -- the admin early-warning signal for a missing price tier or
unconfirmed bundle (see CLAUDE.md, .claude/skills/transform-classification/
SKILL.md).

ADMIN-or-VIEWER access (not ADMIN-only): this is a read-only operational
report, not a write surface -- see app.core.auth.require_viewer_or_admin's
docstring for the full reasoning.

Deliberately NOT cached through the SWR layer (unlike revenue/occupancy
endpoints) -- this is a low-traffic admin report where "always fresh" matters
more than shaving a DB round trip, and it needs to reflect a just-triggered
reclassify immediately for acceptance-testing purposes without relying on
cache invalidation timing.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.core.auth import require_viewer_or_admin
from app.core.db import get_pool
from app.models.responses import (
    DateRange,
    UnmappedAmountSummaryItem,
    UnmappedTransactionItem,
    UnmappedTransactionsResponse,
)
from app.repositories import admin as admin_repo

router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/unmapped", response_model=UnmappedTransactionsResponse)
async def unmapped_transactions(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    limit: int = Query(500, ge=1, le=5000),
    _role: str = Depends(require_viewer_or_admin),
) -> UnmappedTransactionsResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        items = await admin_repo.list_unmapped_transactions(
            conn, date_from=date_from, date_to=date_to, limit=limit
        )
        by_amount = await admin_repo.summarize_unmapped_amounts(
            conn, date_from=date_from, date_to=date_to
        )

    return UnmappedTransactionsResponse(
        date_range=DateRange(
            date_from=date_from or date(2020, 1, 1),
            date_to=date_to or date.today(),
            label="from/to filter (unbounded defaults shown as 2020-01-01 / today)",
        ),
        total_count=len(items),
        items=[
            UnmappedTransactionItem(
                paystack_transaction_id=r["paystack_transaction_id"],
                reference=r["reference"],
                amount=float(r["amount"]),
                status=r["status"],
                channel=r["channel"],
                terminal_serial=r["terminal_serial"],
                location_name=r["location_name"],
                paid_at=r["paid_at"].isoformat() if r["paid_at"] else None,
                transaction_date=r["transaction_date"],
            )
            for r in items
        ],
        by_amount=[
            UnmappedAmountSummaryItem(
                amount=float(r["amount"]),
                txn_count=r["txn_count"],
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
            )
            for r in by_amount
        ],
    )
