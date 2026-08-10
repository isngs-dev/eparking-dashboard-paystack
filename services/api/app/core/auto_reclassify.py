"""Shared "enqueue a scoped reclassify after a fee_categories/revenue_split
write" helper, used by both admin routers so the auto-trigger behavior
(clamp to raw_transactions, enqueue, poll briefly for a run_logs id) lives in
exactly one place rather than being duplicated per router.
"""

from __future__ import annotations

import asyncio
from datetime import date

import asyncpg

from app.core.reclassify_client import enqueue_reclassify
from app.repositories import admin as admin_repo

# How long/hard to poll run_logs for the row the just-enqueued Celery task
# will create, before giving up and returning just the Celery task id. The
# task's DB work is a single set-based SQL statement over a bounded date
# range, so in practice this resolves in well under a second locally; this
# is a generous ceiling for a slower/loaded worker, not an expected wait.
_POLL_ATTEMPTS = 20
_POLL_INTERVAL_SECONDS = 0.25


async def trigger_scoped_reclassify(
    conn: asyncpg.Connection,
    *,
    effective_from: date,
    effective_to: date | None,
    reason: str,
) -> dict:
    """Clamp `[effective_from, effective_to or <max raw date>]` to what's
    actually present in `raw_transactions`, enqueue the ingestion service's
    reclassify Celery task for that clamped range, and return a dict shaped
    like `ReclassifyTriggerInfo` (see models/responses.py).

    Returns `triggered=False` (no enqueue) if there is no raw_transactions
    data in the requested window at all -- per the sprint doc: "don't try to
    reclassify a date range with no data".
    """
    if effective_to is None:
        extent = await admin_repo.get_raw_transactions_extent(conn)
        if extent is None:
            return {"triggered": False, "reason": "no raw_transactions data present"}
        requested_to = extent[1]
    else:
        requested_to = effective_to

    clamped = await admin_repo.clamp_to_raw_transactions_range(
        conn, requested_from=effective_from, requested_to=requested_to
    )
    if clamped is None:
        return {
            "triggered": False,
            "reason": "no raw_transactions rows fall within the affected effective-date window",
            "scoped_from": effective_from,
            "scoped_to": requested_to,
        }

    clamped_from, clamped_to = clamped
    celery_task_id = enqueue_reclassify(
        from_date_iso=clamped_from.isoformat(),
        to_date_iso=clamped_to.isoformat(),
        reason=reason,
    )

    # Best-effort: poll run_logs briefly so the caller gets a real run_id to
    # track/poll themselves, rather than only an opaque Celery task id. Not
    # load-bearing -- if the worker is slow/backlogged, the caller still
    # gets celery_task_id and can find the run_logs row once it appears.
    run_row = None
    for _ in range(_POLL_ATTEMPTS):
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        candidate = await admin_repo.find_recent_reclassify_run(
            conn, window_from=clamped_from, window_to=clamped_to
        )
        if candidate is not None and candidate["started_at"] is not None:
            run_row = candidate
            break

    return {
        "triggered": True,
        "reason": reason,
        "scoped_from": clamped_from,
        "scoped_to": clamped_to,
        "run_id": run_row["id"] if run_row else None,
        "celery_task_id": celery_task_id,
        "status": run_row["status"] if run_row else "enqueued",
    }
