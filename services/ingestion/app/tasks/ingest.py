"""Celery tasks that poll Paystack (or read the CSV backfill) into
`eparking.raw_transactions`.

Schedule (see .claude/skills/paystack-ingestion/SKILL.md and
.claude/sprints/03_INGESTION.md):
    sync_recent      every 15 min, window = last 48h
    sync_reconcile   nightly,      window = last 35 days
    backfill         manual/parameterized, arbitrary date range (live API)
    backfill_csv      manual, CSV-backfill mode (no live API call at all)

No settlement-related task exists here by design -- settlement is fully out
of scope project-wide (see CLAUDE.md and the skill's non-negotiables).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.api_mapping import LIVE_API_INGEST_SOURCE, get_created_at, map_api_transaction
from app.cache_invalidate import invalidate_dashboard_cache
from app.celery_app import celery_app
from app.csv_backfill import CSV_BACKFILL_INGEST_SOURCE, iter_mapped_batches
from app.db import (
    create_run_log,
    finish_run_log,
    get_connection,
    upsert_raw_transactions_batch,
)
from app.paystack_client import PaystackClient
from app.transform import rebuild_daily_revenue, reclassify_transactions, transform_raw_to_dashboard

SYNC_RECENT_WINDOW = timedelta(hours=48)
SYNC_RECONCILE_WINDOW = timedelta(days=35)

# Default location of the larger, 28,672-row validation CSV export. Override
# via the `csv_path` kwarg on `backfill_csv` for other exports / local dev.
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_BACKFILL_CSV_PATH = (
    _REPO_ROOT
    / "references"
    / "sample-data"
    / "E__Parking_Solution_transactions_1786014900375.csv"
)


async def _run_api_ingest(
    *, run_type: str, window_from: datetime, window_to: datetime
) -> dict[str, int]:
    """Shared body for sync_recent / sync_reconcile / backfill (live API)."""
    conn = await get_connection()
    run_id = await create_run_log(conn, run_type=run_type, window_from=window_from, window_to=window_to)

    rows_fetched = 0
    rows_upserted = 0
    try:
        client = PaystackClient()
        try:
            batch = []
            async for tx in client.iter_all_transactions(
                window_from=window_from, window_to=window_to
            ):
                rows_fetched += 1
                # Defensive: window is off created_at, but the API is also
                # queried with from/to on created_at, so this is a sanity
                # re-check rather than the primary filter.
                created_at = get_created_at(tx)
                if created_at is not None and not (window_from <= created_at <= window_to):
                    continue
                batch.append(map_api_transaction(tx))
                if len(batch) >= 500:
                    rows_upserted += await upsert_raw_transactions_batch(
                        conn, batch, ingest_run_id=run_id
                    )
                    batch = []
            if batch:
                rows_upserted += await upsert_raw_transactions_batch(
                    conn, batch, ingest_run_id=run_id
                )
        finally:
            await client.aclose()

        # Transform runs inline in the same task, immediately after the raw
        # upsert, per .claude/sprints/04_TRANSFORM_CLASSIFICATION.md -- never
        # a separately scheduled task, so raw_transactions and
        # dashboard_transactions can't drift out of sync silently. Windowed
        # on the same [window_from, window_to] the ingest itself used.
        await transform_raw_to_dashboard(conn, from_ts=window_from, to_ts=window_to)

        # daily_revenue is rebuilt only for the calendar dates actually
        # touched by this run's dashboard_transactions rows -- never a full
        # rebuild. Dates are read back from dashboard_transactions (business
        # timezone bucketing already applied there) rather than derived from
        # window_from/window_to directly, since a UTC ingestion window can
        # span a different set of business-tz calendar dates.
        affected_dates = [
            row["transaction_date"]
            for row in await conn.fetch(
                """
                SELECT DISTINCT transaction_date
                FROM eparking.dashboard_transactions
                WHERE paid_at BETWEEN $1 AND $2
                  AND transaction_date IS NOT NULL
                """,
                window_from,
                window_to,
            )
        ]
        await rebuild_daily_revenue(conn, dates=affected_dates)

        await finish_run_log(
            conn,
            run_id=run_id,
            status="success",
            rows_fetched=rows_fetched,
            rows_upserted=rows_upserted,
        )

        # Sprint 7 (carried forward from Sprint 5): invalidate the API's
        # Redis cache after every successful transform_raw_to_dashboard +
        # rebuild_daily_revenue run, so the next dashboard request gets
        # fresh data instead of a stale cached response for up to the
        # per-endpoint hard TTL (up to 30 min). See app/cache_invalidate.py.
        invalidate_dashboard_cache()
    except Exception as exc:  # noqa: BLE001 -- top-level task error reporting
        await finish_run_log(
            conn,
            run_id=run_id,
            status="failed",
            rows_fetched=rows_fetched,
            rows_upserted=rows_upserted,
            error_message=str(exc),
        )
        raise
    finally:
        await conn.close()

    return {"run_id": run_id, "rows_fetched": rows_fetched, "rows_upserted": rows_upserted}


async def _run_csv_backfill(*, csv_path: Path) -> dict[str, int]:
    conn = await get_connection()
    run_id = await create_run_log(
        conn,
        run_type="backfill",
        window_from=None,
        window_to=None,
    )

    rows_fetched = 0
    rows_upserted = 0
    try:
        for mapped_batch in iter_mapped_batches(csv_path):
            rows_fetched += len(mapped_batch)
            rows_upserted += await upsert_raw_transactions_batch(
                conn, mapped_batch, ingest_run_id=run_id
            )

        await finish_run_log(
            conn,
            run_id=run_id,
            status="success",
            rows_fetched=rows_fetched,
            rows_upserted=rows_upserted,
        )
    except Exception as exc:  # noqa: BLE001
        await finish_run_log(
            conn,
            run_id=run_id,
            status="failed",
            rows_fetched=rows_fetched,
            rows_upserted=rows_upserted,
            error_message=str(exc),
        )
        raise
    finally:
        await conn.close()

    return {"run_id": run_id, "rows_fetched": rows_fetched, "rows_upserted": rows_upserted}


@celery_app.task(name="eparking.ingest.sync_recent")
def sync_recent() -> dict[str, int]:
    """Every 15 min: poll the last 48h, windowed off created_at."""
    now = datetime.now(timezone.utc)
    return asyncio.run(
        _run_api_ingest(run_type="sync_recent", window_from=now - SYNC_RECENT_WINDOW, window_to=now)
    )


@celery_app.task(name="eparking.ingest.sync_reconcile")
def sync_reconcile() -> dict[str, int]:
    """Nightly: re-poll the last 35 days as cheap insurance against missed
    runs -- idempotent UPSERT makes the overlap with sync_recent free."""
    now = datetime.now(timezone.utc)
    return asyncio.run(
        _run_api_ingest(
            run_type="sync_reconcile", window_from=now - SYNC_RECONCILE_WINDOW, window_to=now
        )
    )


@celery_app.task(name="eparking.ingest.backfill")
def backfill(window_from_iso: str, window_to_iso: str) -> dict[str, int]:
    """Manual/parameterized backfill against the live Paystack API for an
    arbitrary date range. Params are ISO 8601 strings (Celery task args must
    be JSON-serializable)."""
    window_from = datetime.fromisoformat(window_from_iso)
    window_to = datetime.fromisoformat(window_to_iso)
    return asyncio.run(_run_api_ingest(run_type="backfill", window_from=window_from, window_to=window_to))


@celery_app.task(name="eparking.ingest.backfill_csv")
def backfill_csv(csv_path: str | None = None) -> dict[str, int]:
    """Manual CSV-backfill mode -- no live Paystack API call at all.

    Defaults to the larger 28,672-row validation export
    (`E__Parking_Solution_transactions_1786014900375.csv`) per the sprint
    spec; pass `csv_path` to point at a different export for local dev.
    """
    path = Path(csv_path) if csv_path else DEFAULT_BACKFILL_CSV_PATH
    return asyncio.run(_run_csv_backfill(csv_path=path))


async def _run_reclassify(*, from_date_iso: str, to_date_iso: str, reason: str) -> dict[str, int]:
    from datetime import date as date_cls

    conn = await get_connection()
    try:
        rows_affected, run_id = await reclassify_transactions(
            conn,
            from_date=date_cls.fromisoformat(from_date_iso),
            to_date=date_cls.fromisoformat(to_date_iso),
            reason=reason,
            return_run_id=True,
        )

        # daily_revenue must be rebuilt for exactly the calendar dates that
        # were touched, same "no full rebuild" rule as the inline ingest
        # path -- read the affected dates back from raw_transactions'
        # equivalent date bucketing rather than re-deriving from_date/to_date
        # business-tz math a second time here.
        affected_dates = [
            row["transaction_date"]
            for row in await conn.fetch(
                """
                SELECT DISTINCT transaction_date
                FROM eparking.dashboard_transactions
                WHERE transaction_date BETWEEN $1 AND $2
                """,
                date_cls.fromisoformat(from_date_iso),
                date_cls.fromisoformat(to_date_iso),
            )
        ]
        await rebuild_daily_revenue(conn, dates=affected_dates)

        # Same cache-invalidation requirement as the inline ingest path (see
        # Sprint 7 sprint doc): an admin correcting a fee_categories rule
        # should see the dashboard reflect it immediately, not after a stale
        # cache wait.
        invalidate_dashboard_cache()
    finally:
        await conn.close()

    return {"rows_affected": rows_affected, "run_id": run_id}


@celery_app.task(name="eparking.ingest.reclassify")
def reclassify(from_date_iso: str, to_date_iso: str, reason: str = "") -> dict[str, int]:
    """Celery entry point wrapping `app.transform.reclassify_transactions`
    plus the matching `rebuild_daily_revenue` + cache invalidation, so a
    caller outside this process (the API, in Sprint 7) can trigger a
    reclassify by task name via `celery_app.send_task(...)` without
    importing ingestion's application code.

    `reclassify_transactions` itself already holds no lock and is proven
    idempotent (see services/ingestion/tests/test_transform.py); running it
    as a Celery task additionally serializes it against `sync_recent`/
    `sync_reconcile` through Celery's normal one-task-at-a-time-per-worker-
    process semantics for this queue, per the skill's guidance to avoid
    racing the inline transform. Params are plain strings (ISO dates) since
    Celery task args must be JSON-serializable.
    """
    return asyncio.run(
        _run_reclassify(from_date_iso=from_date_iso, to_date_iso=to_date_iso, reason=reason)
    )
