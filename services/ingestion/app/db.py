"""Shared asyncpg helpers: connection + the raw_transactions UPSERT.

Both the live-API ingestion task and the CSV-backfill path funnel through
`upsert_raw_transaction` / `upsert_raw_transactions_batch` so idempotency
semantics (hash-guarded no-op re-writes) live in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from eparking_common.config import get_settings
from app.parsing import compute_raw_hash


@dataclass(frozen=True)
class RawTransactionRow:
    """One row bound for `eparking.raw_transactions`.

    Mirrors the migration 008 column set exactly (minus the bookkeeping
    columns `ingested_at`, which defaults server-side, and `raw_hash`, which
    is computed here so both ingestion paths hash consistently).
    """

    paystack_transaction_id: int
    reference: str
    amount: Any  # Decimal/str/float -- asyncpg + NUMERIC handles all three
    amount_kobo: int | None
    currency: str | None
    status: str | None
    channel: str | None
    gateway_response: str | None
    source: str | None
    source_identifier: str | None
    customer_email: str | None
    customer_code: str | None
    card_type: str | None
    card_bank: str | None
    card_last4: str | None
    paid_at: datetime | None
    fees: Any | None
    raw_payload: dict | None
    ingest_source: str

    @property
    def raw_hash(self) -> str:
        """Hash over data columns only -- excludes bookkeeping columns.

        See `compute_raw_hash` docstring for the exact rationale. Field
        order here is the contract; changing it changes every stored hash
        (harmless -- just means the next run rewrites everything once).
        """
        return compute_raw_hash(
            self.reference,
            self.amount,
            self.amount_kobo,
            self.currency,
            self.status,
            self.channel,
            self.gateway_response,
            self.source,
            self.source_identifier,
            self.customer_email,
            self.customer_code,
            self.card_type,
            self.card_bank,
            self.card_last4,
            self.paid_at.isoformat() if self.paid_at else None,
            self.fees,
        )


_UPSERT_SQL = """
INSERT INTO eparking.raw_transactions (
    paystack_transaction_id, reference, amount, amount_kobo, currency,
    status, channel, gateway_response, source, source_identifier,
    customer_email, customer_code, card_type, card_bank, card_last4,
    paid_at, fees, raw_payload, ingest_source, ingest_run_id,
    ingested_at, raw_hash
) VALUES (
    $1, $2, $3, $4, $5,
    $6, $7, $8, $9, $10,
    $11, $12, $13, $14, $15,
    $16, $17, $18, $19, $20,
    now(), $21
)
ON CONFLICT (paystack_transaction_id) DO UPDATE SET
    reference          = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.reference ELSE eparking.raw_transactions.reference END,
    amount              = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.amount ELSE eparking.raw_transactions.amount END,
    amount_kobo         = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.amount_kobo ELSE eparking.raw_transactions.amount_kobo END,
    currency            = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.currency ELSE eparking.raw_transactions.currency END,
    status              = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.status ELSE eparking.raw_transactions.status END,
    channel             = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.channel ELSE eparking.raw_transactions.channel END,
    gateway_response    = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.gateway_response ELSE eparking.raw_transactions.gateway_response END,
    source              = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.source ELSE eparking.raw_transactions.source END,
    source_identifier   = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.source_identifier ELSE eparking.raw_transactions.source_identifier END,
    customer_email      = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.customer_email ELSE eparking.raw_transactions.customer_email END,
    customer_code       = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.customer_code ELSE eparking.raw_transactions.customer_code END,
    card_type           = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.card_type ELSE eparking.raw_transactions.card_type END,
    card_bank           = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.card_bank ELSE eparking.raw_transactions.card_bank END,
    card_last4          = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.card_last4 ELSE eparking.raw_transactions.card_last4 END,
    paid_at             = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.paid_at ELSE eparking.raw_transactions.paid_at END,
    fees                = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.fees ELSE eparking.raw_transactions.fees END,
    raw_payload         = CASE WHEN eparking.raw_transactions.raw_hash IS DISTINCT FROM EXCLUDED.raw_hash
                               THEN EXCLUDED.raw_payload ELSE eparking.raw_transactions.raw_payload END,
    raw_hash            = EXCLUDED.raw_hash,
    -- Bookkeeping columns always advance, even for hash-unchanged rows, so
    -- the caller can see the row was touched by this run.
    ingest_source       = EXCLUDED.ingest_source,
    ingest_run_id        = EXCLUDED.ingest_run_id,
    ingested_at          = now()
"""


async def get_connection() -> asyncpg.Connection:
    settings = get_settings()
    return await asyncpg.connect(dsn=settings.asyncpg_dsn)


async def upsert_raw_transactions_batch(
    conn: asyncpg.Connection,
    rows: list[RawTransactionRow],
    *,
    ingest_run_id: int,
) -> int:
    """UPSERT a batch of rows inside one transaction. Returns rows upserted."""
    if not rows:
        return 0

    import json

    records = [
        (
            r.paystack_transaction_id,
            r.reference,
            r.amount,
            r.amount_kobo,
            r.currency,
            r.status,
            r.channel,
            r.gateway_response,
            r.source,
            r.source_identifier,
            r.customer_email,
            r.customer_code,
            r.card_type,
            r.card_bank,
            r.card_last4,
            r.paid_at,
            r.fees,
            json.dumps(r.raw_payload) if r.raw_payload is not None else None,
            r.ingest_source,
            ingest_run_id,
            r.raw_hash,
        )
        for r in rows
    ]

    async with conn.transaction():
        await conn.executemany(_UPSERT_SQL, records)

    return len(rows)


async def create_run_log(
    conn: asyncpg.Connection,
    *,
    run_type: str,
    window_from: datetime | None,
    window_to: datetime | None,
) -> int:
    row = await conn.fetchrow(
        """
        INSERT INTO eparking.run_logs (run_type, status, window_from, window_to)
        VALUES ($1, 'running', $2, $3)
        RETURNING id
        """,
        run_type,
        window_from,
        window_to,
    )
    return row["id"]


async def finish_run_log(
    conn: asyncpg.Connection,
    *,
    run_id: int,
    status: str,
    rows_fetched: int,
    rows_upserted: int,
    error_message: str | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE eparking.run_logs
        SET status = $2,
            rows_fetched = $3,
            rows_upserted = $4,
            error_message = $5,
            finished_at = now()
        WHERE id = $1
        """,
        run_id,
        status,
        rows_fetched,
        rows_upserted,
        error_message,
    )
