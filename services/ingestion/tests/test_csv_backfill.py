"""Unit tests for app.csv_backfill's row-mapping logic (no DB required)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.csv_backfill import CSV_BACKFILL_INGEST_SOURCE, map_csv_row


def _base_row(**overrides: str) -> dict[str, str]:
    row = {
        "Transaction Date": "Jul 1st, 2026 06:37:34 AM",
        "Customer (email)": "pos_iafnliujs@paystack.com",
        "Amount Paid": "600",
        "Gateway Response": "Approved or completed successfully",
        "Transaction ID": "6314881016",
        "Card Type": "debit",
        "Card Bank": "PAYCOM",
        "Currency": "NGN",
        "Source": "pos",
        "Source Identifier": "2PSTAW36",
        "Status": "success",
        "Channel": "pos",
    }
    row.update(overrides)
    return row


def test_maps_success_row_verbatim() -> None:
    mapped = map_csv_row(_base_row())
    assert mapped.paystack_transaction_id == 6314881016
    assert mapped.reference == "6314881016"
    assert mapped.amount == "600"
    assert mapped.amount_kobo is None
    assert mapped.currency == "NGN"
    assert mapped.status == "success"
    assert mapped.channel == "pos"
    assert mapped.gateway_response == "Approved or completed successfully"
    assert mapped.source == "pos"
    assert mapped.source_identifier == "2PSTAW36"
    assert mapped.customer_email == "pos_iafnliujs@paystack.com"
    assert mapped.card_type == "debit"
    assert mapped.card_bank == "PAYCOM"
    assert mapped.card_last4 is None
    assert mapped.paid_at == datetime(2026, 7, 1, 6, 37, 34, tzinfo=timezone.utc)
    assert mapped.fees is None
    assert mapped.ingest_source == CSV_BACKFILL_INGEST_SOURCE
    assert mapped.raw_payload == _base_row()


def test_abandoned_row_has_blank_card_fields_mapped_to_none() -> None:
    row = _base_row(
        **{
            "Transaction Date": "Jul 1st, 2026 06:51:42 AM",
            "Amount Paid": "300",
            "Gateway Response": "The transaction was not completed",
            "Transaction ID": "6314912099",
            "Card Type": "",
            "Card Bank": "",
            "Status": "abandoned",
            "Channel": "card",
        }
    )
    mapped = map_csv_row(row)
    assert mapped.status == "abandoned"
    assert mapped.card_type is None
    assert mapped.card_bank is None
    assert mapped.amount == "300"


def test_small_test_charge_amount_preserved_exactly() -> None:
    row = _base_row(
        **{
            "Amount Paid": "0.03",
            "Transaction ID": "6318893357",
            "Card Type": "",
            "Card Bank": "",
            "Status": "abandoned",
            "Channel": "card",
        }
    )
    mapped = map_csv_row(row)
    assert mapped.amount == "0.03"


def test_bundled_annual_monthly_amount_preserved() -> None:
    row = _base_row(**{"Amount Paid": "12500", "Transaction ID": "6315749729"})
    mapped = map_csv_row(row)
    assert mapped.amount == "12500"


def test_raw_hash_changes_when_status_changes() -> None:
    row_success = _base_row()
    row_failed = _base_row(Status="failed")
    assert map_csv_row(row_success).raw_hash != map_csv_row(row_failed).raw_hash


def test_raw_hash_stable_for_identical_row() -> None:
    row = _base_row()
    assert map_csv_row(row).raw_hash == map_csv_row(dict(row)).raw_hash
