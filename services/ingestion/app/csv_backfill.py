"""CSV-backfill ingestion path.

Reads a Paystack CSV export (verified shape:
`references/sample-data/E__Parking_Solution_transactions_1786014900375.csv`,
28,672 rows, columns: Transaction Date, Customer (email), Amount Paid,
Gateway Response, Transaction ID, Card Type, Card Bank, Currency, Source,
Source Identifier, Status, Channel -- no Settlement Date column, which is
expected and correct: settlement is out of scope project-wide, see
CLAUDE.md) and loads it into `eparking.raw_transactions` with
`ingest_source='csv_backfill'`, going through the exact same
`upsert_raw_transactions_batch` UPSERT path the live-API task uses.

Column-mapping decisions (documented per the sprint instructions, since the
CSV's shape differs from the live API's):

- `Transaction Date` -> parsed via `parse_ordinal_csv_datetime` -> used for
  BOTH `paid_at` and as this row's window marker. Reasoning: the CSV gives
  us exactly one timestamp per row, with no way to distinguish "created" from
  "paid" the way the live API's `created_at`/`paid_at` pair does. Using it
  for `paid_at` is the more defensible reading even for abandoned/failed
  rows (which on live API would have `paid_at = null`) because CSV
  `Transaction Date` is closer in meaning to "when this happened" broadly --
  there's no other candidate value. This is flagged so a future reconciler
  comparing CSV-backfilled rows against live-API-backfilled rows for the
  same historical window knows `paid_at` is not directly comparable for
  failed/abandoned transactions between the two ingest_source values.
- `Transaction ID` -> `paystack_transaction_id` (the idempotency key) AND
  `reference` (the CSV has no separate reference/access-code column; the
  transaction ID string doubles as the best available reference value).
- `Amount Paid` -> `amount`, stored exactly as given (naira, e.g. "300.00").
  `amount_kobo` is left NULL for CSV-backfilled rows -- the kobo-vs-naira
  question is a live-API response-shape concern (see the skill's verified
  facts) and does not apply to a CSV that already gives naira.
- `Card Type` / `Card Bank` -> `card_type` / `card_bank` directly. The CSV
  has no card-last-4 column at all, so `card_last4` is always NULL for
  csv_backfill rows (not a parsing gap -- the data genuinely isn't in this
  export).
- `Source` / `Source Identifier` -> `source` / `source_identifier` directly
  (the CSV gives these as flat columns, unlike the live API's nested
  `source` object -- no further extraction needed here).
- `Currency`, `Status`, `Channel`, `Gateway Response`, `Customer (email)` ->
  mapped 1:1 to `currency`, `status`, `channel`, `gateway_response`,
  `customer_email`.
- `customer_code` and `fees` have no CSV source column -- left NULL.
- `raw_payload` is populated with the full CSV row (as a dict) so the bronze
  layer still holds a verbatim copy of what we read, consistent with the
  live-API path storing the full JSON response.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from app.db import RawTransactionRow
from app.parsing import parse_ordinal_csv_datetime

CSV_BACKFILL_INGEST_SOURCE = "csv_backfill"

# Rows are grouped into batches for executemany() rather than a single
# 28,672-row round trip or 28,672 individual round trips.
DEFAULT_BATCH_SIZE = 500


def read_csv_rows(path: Path) -> Iterator[dict[str, str]]:
    """Yield raw dict rows from the Paystack CSV export.

    `utf-8-sig` handles a possible BOM on the header line (harmless if
    absent). Uses `csv.DictReader` directly -- no pandas dependency needed
    for this shape.
    """
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        yield from reader


def map_csv_row(row: dict[str, str]) -> RawTransactionRow:
    """Map one CSV dict row into a `RawTransactionRow`.

    Raises ValueError (via the ordinal parser or int()) on malformed rows --
    intentionally not swallowed, so a bad row fails the run loudly rather
    than silently dropping data from the bronze layer.
    """
    transaction_id = int(row["Transaction ID"].strip())
    paid_at = parse_ordinal_csv_datetime(row["Transaction Date"])

    amount_raw = row["Amount Paid"].strip()

    def _blank_to_none(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    return RawTransactionRow(
        paystack_transaction_id=transaction_id,
        reference=str(transaction_id),
        amount=amount_raw,
        amount_kobo=None,
        currency=_blank_to_none(row.get("Currency")),
        status=_blank_to_none(row.get("Status")),
        channel=_blank_to_none(row.get("Channel")),
        gateway_response=_blank_to_none(row.get("Gateway Response")),
        source=_blank_to_none(row.get("Source")),
        source_identifier=_blank_to_none(row.get("Source Identifier")),
        customer_email=_blank_to_none(row.get("Customer (email)")),
        customer_code=None,
        card_type=_blank_to_none(row.get("Card Type")),
        card_bank=_blank_to_none(row.get("Card Bank")),
        card_last4=None,
        paid_at=paid_at,
        fees=None,
        raw_payload=dict(row),
        ingest_source=CSV_BACKFILL_INGEST_SOURCE,
    )


def iter_mapped_batches(
    path: Path, *, batch_size: int = DEFAULT_BATCH_SIZE
) -> Iterator[list[RawTransactionRow]]:
    """Yield lists of mapped `RawTransactionRow`, `batch_size` at a time."""
    batch: list[RawTransactionRow] = []
    for csv_row in read_csv_rows(path):
        batch.append(map_csv_row(csv_row))
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch
