"""Unit tests for app.parsing -- the ordinal-date parser and raw_hash helper.

Scoped strictly to the CSV-backfill path per the paystack-ingestion skill:
these fixtures are exactly the kind of strings that appear in
references/sample-data/E__Parking_Solution_transactions_1786014900375.csv,
never ISO 8601 (that's the live API's shape, handled in api_mapping.py).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.parsing import compute_raw_hash, parse_ordinal_csv_datetime, strip_ordinal_suffix


class TestStripOrdinalSuffix:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Jul 1st, 2026 06:37:34 AM", "Jul 1, 2026 06:37:34 AM"),
            ("Jul 2nd, 2026 10:54:25 AM", "Jul 2, 2026 10:54:25 AM"),
            ("Jul 3rd, 2026 11:56:10 AM", "Jul 3, 2026 11:56:10 AM"),
            ("Jul 4th, 2026 01:00:00 PM", "Jul 4, 2026 01:00:00 PM"),
            ("Jul 21st, 2026 09:00:00 AM", "Jul 21, 2026 09:00:00 AM"),
            ("Jul 22nd, 2026 09:00:00 AM", "Jul 22, 2026 09:00:00 AM"),
            ("Jul 23rd, 2026 09:00:00 AM", "Jul 23, 2026 09:00:00 AM"),
            ("Jul 31st, 2026 09:00:00 AM", "Jul 31, 2026 09:00:00 AM"),
            ("Jul 11th, 2026 09:00:00 AM", "Jul 11, 2026 09:00:00 AM"),
            ("Jul 12th, 2026 09:00:00 AM", "Jul 12, 2026 09:00:00 AM"),
            ("Jul 13th, 2026 09:00:00 AM", "Jul 13, 2026 09:00:00 AM"),
        ],
    )
    def test_strips_all_ordinal_suffix_variants(self, raw: str, expected: str) -> None:
        assert strip_ordinal_suffix(raw) == expected


class TestParseOrdinalCsvDatetime:
    def test_parses_verified_sample_row(self) -> None:
        # Verbatim from references/sample-data/..._1786014900375.csv row 2.
        result = parse_ordinal_csv_datetime("Jul 1st, 2026 06:37:34 AM")
        assert result == datetime(2026, 7, 1, 6, 37, 34, tzinfo=timezone.utc)

    def test_parses_pm_time(self) -> None:
        result = parse_ordinal_csv_datetime("Jul 7th, 2026 04:21:39 PM")
        assert result == datetime(2026, 7, 7, 16, 21, 39, tzinfo=timezone.utc)

    def test_parses_21st_22nd_23rd_31st_edge_cases(self) -> None:
        assert parse_ordinal_csv_datetime("Jul 21st, 2026 12:00:00 AM").day == 21
        assert parse_ordinal_csv_datetime("Jul 22nd, 2026 12:00:00 AM").day == 22
        assert parse_ordinal_csv_datetime("Jul 23rd, 2026 12:00:00 AM").day == 23
        assert parse_ordinal_csv_datetime("Jul 31st, 2026 12:00:00 AM").day == 31

    def test_result_is_timezone_aware_utc(self) -> None:
        result = parse_ordinal_csv_datetime("Jul 1st, 2026 06:37:34 AM")
        assert result.tzinfo is timezone.utc

    def test_handles_surrounding_whitespace(self) -> None:
        result = parse_ordinal_csv_datetime("  Jul 1st, 2026 06:37:34 AM  ")
        assert result == datetime(2026, 7, 1, 6, 37, 34, tzinfo=timezone.utc)

    def test_raises_on_garbage_input(self) -> None:
        with pytest.raises(ValueError):
            parse_ordinal_csv_datetime("not a date at all")

    def test_raises_on_iso8601_input(self) -> None:
        """Guard against accidentally feeding a live-API ISO 8601 timestamp
        into the CSV-only ordinal parser -- it should fail loudly, not
        silently misparse."""
        with pytest.raises(ValueError):
            parse_ordinal_csv_datetime("2026-07-01T06:37:34.000Z")


class TestComputeRawHash:
    def test_same_inputs_produce_same_hash(self) -> None:
        h1 = compute_raw_hash("a", 300, None, "success")
        h2 = compute_raw_hash("a", 300, None, "success")
        assert h1 == h2

    def test_different_inputs_produce_different_hash(self) -> None:
        h1 = compute_raw_hash("a", 300, None, "success")
        h2 = compute_raw_hash("a", 300, None, "failed")
        assert h1 != h2

    def test_none_and_empty_string_do_not_collide(self) -> None:
        h_none = compute_raw_hash(None, "x")
        h_empty = compute_raw_hash("", "x")
        assert h_none != h_empty

    def test_field_boundary_shift_does_not_collide(self) -> None:
        # "ab", "c" vs "a", "bc" -- naive concatenation would collide.
        h1 = compute_raw_hash("ab", "c")
        h2 = compute_raw_hash("a", "bc")
        assert h1 != h2
