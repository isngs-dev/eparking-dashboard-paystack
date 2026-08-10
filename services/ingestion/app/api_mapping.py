"""Maps a live Paystack API transaction dict into a `RawTransactionRow`.

Kept separate from `csv_backfill.py`'s mapping function because the two
source shapes genuinely differ (nested `source`/`authorization`/`customer`
objects here vs. flat CSV columns there) -- see the paystack-ingestion
skill's verified-facts section for the field shapes this relies on.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db import RawTransactionRow

LIVE_API_INGEST_SOURCE = "paystack_api"


def _parse_iso8601(value: str | None) -> datetime | None:
    """Parse a live-API ISO 8601 timestamp. Never the ordinal CSV parser."""
    if not value:
        return None
    # Paystack timestamps are ISO 8601, sometimes with a trailing "Z".
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def map_api_transaction(tx: dict[str, Any]) -> RawTransactionRow:
    """Map one `data[]` element from `GET /transaction` into a raw row.

    Null-guards the nested `source` object at both levels (the object itself
    and `source.identifier`) per the skill's verified facts -- both are
    documented as nullable.
    """
    authorization = tx.get("authorization") or {}
    customer = tx.get("customer") or {}
    source = tx.get("source") or {}

    amount_kobo = tx.get("amount")
    # Live API amount is in kobo per the (still-to-be-confirmed-against-a-
    # real-response) OpenAPI typing; store both the raw minor-unit value and
    # a naira conversion so downstream code has both without re-deriving.
    amount_naira = (amount_kobo / 100) if amount_kobo is not None else None

    return RawTransactionRow(
        paystack_transaction_id=int(tx["id"]),
        reference=tx.get("reference") or str(tx["id"]),
        amount=amount_naira,
        amount_kobo=amount_kobo,
        currency=tx.get("currency"),
        status=tx.get("status"),
        channel=tx.get("channel"),
        gateway_response=tx.get("gateway_response"),
        source=source.get("source") if source else None,
        source_identifier=source.get("identifier") if source else None,
        customer_email=customer.get("email"),
        customer_code=customer.get("customer_code"),
        card_type=authorization.get("card_type") or authorization.get("brand"),
        card_bank=authorization.get("bank"),
        card_last4=authorization.get("last4"),
        paid_at=_parse_iso8601(tx.get("paid_at")),
        fees=tx.get("fees"),
        raw_payload=tx,
        ingest_source=LIVE_API_INGEST_SOURCE,
    )


def get_created_at(tx: dict[str, Any]) -> datetime | None:
    """`created_at` is always present per the skill's verified facts, but
    guarded here anyway rather than assuming a live payload can't surprise
    us."""
    return _parse_iso8601(tx.get("created_at"))
