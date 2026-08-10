"""Sprint 4 acceptance tests for the raw_transactions -> dashboard_transactions
transform, the fee_categories classification rules, and the daily_revenue
rollup.

Per .claude/sprints/04_TRANSFORM_CLASSIFICATION.md's "acceptance gate"
(rewritten for live data -- no CSV fixture, no hardcoded date range): these
tests query `run_logs`/`raw_transactions` themselves to find whatever window
of live-pulled data currently exists, run the transform against it, and
verify structural/distributional properties -- not a fixed row-by-row diff
against a frozen export. They will keep working as more live data
accumulates.

Requires a reachable Postgres (docker-compose `postgres` service, host port
5433 by default -- see .env / docker-compose.yml) with migrations applied
(`python -m app.migrate`). Skipped automatically if the DB is unreachable or
raw_transactions is empty, so this file is safe to collect in any
environment (CI without a live DB, a fresh clone before first backfill,
etc.) without failing the whole suite.

Follows the existing test-file pattern from Sprint 3
(tests/test_csv_backfill.py, tests/test_parsing.py) -- async DB calls are
driven with `asyncio.run` inside plain `def test_*` functions (no
pytest-asyncio plugin is installed in this project's venv), matching the
`asyncio.run(...)` convention already used throughout app/tasks/ingest.py.

Windows note: every asyncpg connection is opened *and* closed inside the
*same* `asyncio.run(...)` call. asyncpg's ProactorEventLoop transport does
not tolerate a connection created in one `asyncio.run` being reused from a
second `asyncio.run` call (the underlying socket transport is bound to the
now-closed loop) -- so each test does exactly one `asyncio.run(_inner())`
that connects, does its work, and closes, rather than sharing a connection
opened by a separate helper call.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import asyncpg
import pytest

from app.transform import (
    rebuild_daily_revenue,
    reclassify_transactions,
    transform_raw_to_dashboard,
)
from eparking_common.config import get_settings

_DASHBOARD_COLUMNS = """
    paystack_transaction_id, reference, amount, fee_category_id, fee_category_code,
    revenue_stream, vehicle_type, counts_as_entry, is_revenue, is_provisional_class,
    status, channel, terminal_id, terminal_serial, location_id, location_name,
    paid_at, transaction_date, transaction_hour, day_of_week, iso_week, iso_year,
    month_start, card_component_annual_count, card_component_monthly_count,
    card_component_annual_amount, card_component_monthly_amount, ticket_quantity, fees
"""

_FAR_PAST = datetime(2000, 1, 1, tzinfo=timezone.utc)
_FAR_FUTURE = datetime(2100, 1, 1, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.run(coro)


async def _connect_or_skip() -> asyncpg.Connection:
    settings = get_settings()
    try:
        return await asyncpg.connect(dsn=settings.asyncpg_dsn)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres unreachable, skipping live-data transform tests: {exc}")
        raise  # pragma: no cover -- pytest.skip always raises


async def _live_window_or_skip(conn: asyncpg.Connection) -> tuple[datetime, datetime]:
    """Fetch the live raw_transactions paid_at window, or skip the test."""
    row = await conn.fetchrow(
        "SELECT min(paid_at) AS from_ts, max(paid_at) AS to_ts, count(*) AS n "
        "FROM eparking.raw_transactions"
    )
    if row is None or row["n"] == 0 or row["from_ts"] is None:
        pytest.skip("raw_transactions is empty -- no live data pulled yet, skipping.")
    return row["from_ts"], row["to_ts"]


async def _snapshot_dashboard(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        f"SELECT {_DASHBOARD_COLUMNS} FROM eparking.dashboard_transactions "
        "ORDER BY paystack_transaction_id"
    )
    return [dict(r) for r in rows]


async def _insert_synthetic_row(conn: asyncpg.Connection, *, tx_id: int, amount: str) -> None:
    await conn.execute(
        """
        INSERT INTO eparking.raw_transactions
            (paystack_transaction_id, reference, amount, status, channel, paid_at, ingest_source)
        VALUES ($1, $2, $3::numeric, 'success', 'pos', now(), 'test_synthetic')
        """,
        tx_id,
        f"synthetic-{tx_id}-test",
        amount,
    )


async def _delete_synthetic_row(conn: asyncpg.Connection, *, tx_id: int) -> None:
    await conn.execute(
        "DELETE FROM eparking.dashboard_transactions WHERE paystack_transaction_id = $1", tx_id
    )
    await conn.execute(
        "DELETE FROM eparking.raw_transactions WHERE paystack_transaction_id = $1", tx_id
    )


class TestLiveWindowStructural:
    """The core acceptance gate: run the transform against whatever's
    actually in raw_transactions right now, and verify no drops/duplicates
    and internally-consistent daily_revenue totals."""

    def test_transform_produces_one_dashboard_row_per_raw_row(self) -> None:
        async def _inner() -> None:
            conn = await _connect_or_skip()
            try:
                from_ts, to_ts = await _live_window_or_skip(conn)

                raw_count = await conn.fetchval(
                    "SELECT count(*) FROM eparking.raw_transactions WHERE paid_at BETWEEN $1 AND $2",
                    from_ts,
                    to_ts,
                )
                await transform_raw_to_dashboard(conn, from_ts=from_ts, to_ts=to_ts)
                dtx_count = await conn.fetchval(
                    "SELECT count(*) FROM eparking.dashboard_transactions "
                    "WHERE paid_at BETWEEN $1 AND $2",
                    from_ts,
                    to_ts,
                )
                # No drops, no duplicates: straight COUNT(*) comparison.
                assert dtx_count == raw_count

                # Also true of the raw table as a whole, since our window
                # covers min..max of paid_at.
                total_raw = await conn.fetchval("SELECT count(*) FROM eparking.raw_transactions")
                total_dtx = await conn.fetchval("SELECT count(*) FROM eparking.dashboard_transactions")
                assert total_dtx == total_raw
            finally:
                await conn.close()

        _run(_inner())

    def test_no_dashboard_transaction_row_is_silently_dropped_for_null_paid_at(self) -> None:
        """Defensive coverage for the NULL-paid_at fallback path documented
        in transform.py -- verifies every raw_transactions row (regardless
        of paid_at) has a corresponding dashboard_transactions row after a
        full-table transform, even though none are expected in the current
        live pull."""

        async def _inner() -> None:
            conn = await _connect_or_skip()
            try:
                await _live_window_or_skip(conn)

                null_paid_at_count = await conn.fetchval(
                    "SELECT count(*) FROM eparking.raw_transactions WHERE paid_at IS NULL"
                )
                # Full-table transform covering everything, including any
                # NULL paid_at rows (those bypass the BETWEEN filter by
                # design -- see _TRANSFORM_SQL's WHERE clause).
                await transform_raw_to_dashboard(conn, from_ts=_FAR_PAST, to_ts=_FAR_FUTURE)

                total_raw = await conn.fetchval("SELECT count(*) FROM eparking.raw_transactions")
                total_dtx = await conn.fetchval("SELECT count(*) FROM eparking.dashboard_transactions")
                assert total_dtx == total_raw, (
                    f"drop detected: {total_raw} raw rows but {total_dtx} dashboard rows "
                    f"({null_paid_at_count} raw rows have a NULL paid_at)"
                )
            finally:
                await conn.close()

        _run(_inner())

    def test_daily_revenue_totals_reconcile_to_direct_sum(self) -> None:
        """Internal consistency check (no external Excel figure exists for
        this live window yet, per the sprint doc) -- daily_revenue's
        total_collection for each day must equal a direct
        SUM(amount) FROM dashboard_transactions for that day."""

        async def _inner() -> None:
            conn = await _connect_or_skip()
            try:
                from_ts, to_ts = await _live_window_or_skip(conn)
                await transform_raw_to_dashboard(conn, from_ts=from_ts, to_ts=to_ts)

                dates = [
                    r["transaction_date"]
                    for r in await conn.fetch(
                        "SELECT DISTINCT transaction_date FROM eparking.dashboard_transactions "
                        "WHERE transaction_date IS NOT NULL"
                    )
                ]
                assert dates, "expected at least one transaction_date after transform"

                await rebuild_daily_revenue(conn, dates=dates)

                direct_sums = {
                    r["transaction_date"]: r["s"]
                    for r in await conn.fetch(
                        "SELECT transaction_date, SUM(amount) AS s "
                        "FROM eparking.dashboard_transactions "
                        "WHERE status = 'success' AND is_revenue "
                        "GROUP BY transaction_date"
                    )
                }
                daily_rows = await conn.fetch(
                    "SELECT revenue_date, total_collection FROM eparking.daily_revenue "
                    "WHERE revenue_date = ANY($1::date[])",
                    dates,
                )

                # Every date with revenue transactions must have a
                # daily_revenue row, and totals must match exactly.
                seen = set()
                for row in daily_rows:
                    seen.add(row["revenue_date"])
                    expected = direct_sums.get(row["revenue_date"], Decimal("0"))
                    assert row["total_collection"] == expected, (
                        f"{row['revenue_date']}: daily_revenue={row['total_collection']} "
                        f"!= direct SUM={expected}"
                    )
                # Every date that has revenue rows must appear in daily_revenue too.
                assert set(direct_sums.keys()) <= seen
            finally:
                await conn.close()

        _run(_inner())

    def test_classification_matches_seed_rules_for_every_observed_amount(self) -> None:
        """Spot-check amount -> fee_category_code against whatever amounts
        actually appear in the live pull, per the confirmed fee_categories
        seed rules (CLAUDE.md / transform-classification skill). Any amount
        with no seeded rule must land on UNMAPPED, never NULL, never a
        different amount's category."""

        async def _inner() -> None:
            conn = await _connect_or_skip()
            try:
                from_ts, to_ts = await _live_window_or_skip(conn)
                await transform_raw_to_dashboard(conn, from_ts=from_ts, to_ts=to_ts)

                rows = await conn.fetch(
                    "SELECT DISTINCT amount, fee_category_code FROM eparking.dashboard_transactions"
                )
                observed = {r["amount"]: r["fee_category_code"] for r in rows}

                # Confirmed, non-negotiable price points -- see CLAUDE.md.
                # Only asserted if actually observed in the live window.
                expected_exact = {
                    Decimal("100.00"): "TICKET_100",
                    Decimal("300.00"): "TICKET_300",
                    Decimal("600.00"): "TICKET_600",
                    Decimal("1200.00"): "TICKET_1200",
                    Decimal("2000.00"): "CARD_MONTHLY",  # the confirmed rule, not "Lorry"
                    Decimal("3000.00"): "TICKET_3000",
                    Decimal("10500.00"): "CARD_ANNUAL",
                    Decimal("12500.00"): "CARD_COMBO_12500",
                    # Migration 013: batched ₦900 resolves onto the BASE Car
                    # tier (TICKET_300), not onto a ₦900 pseudo-tier.
                    Decimal("900.00"): "TICKET_300",
                    Decimal("25000.00"): "CARD_COMBO_ANNUAL_X2",
                }
                checked_any = False
                for amount, expected_code in expected_exact.items():
                    if amount in observed:
                        checked_any = True
                        assert observed[amount] == expected_code, (
                            f"amount {amount} classified as {observed[amount]!r}, "
                            f"expected {expected_code!r}"
                        )
                assert checked_any, "expected at least one known price point in the live window"

                # Sub-100 test charges.
                for amount, code in observed.items():
                    if Decimal("0.01") <= amount <= Decimal("99.99"):
                        assert code == "TEST_CHARGE", f"test charge {amount} classified as {code!r}"

                # Anything not matching a seeded range must be UNMAPPED, never
                # silently absent from fee_category_code / a NULL.
                seeded_ranges = [
                    (Decimal("0.01"), Decimal("99.99")),
                    (Decimal("100.00"), Decimal("100.00")),
                    (Decimal("300.00"), Decimal("300.00")),
                    (Decimal("600.00"), Decimal("600.00")),
                    (Decimal("1200.00"), Decimal("1200.00")),
                    (Decimal("2000.00"), Decimal("2000.00")),
                    (Decimal("3000.00"), Decimal("3000.00")),
                    (Decimal("10500.00"), Decimal("10500.00")),
                    (Decimal("12500.00"), Decimal("12500.00")),
                    (Decimal("900.00"), Decimal("900.00")),
                    (Decimal("25000.00"), Decimal("25000.00")),
                ]
                for amount, code in observed.items():
                    matches_seed = any(lo <= amount <= hi for lo, hi in seeded_ranges)
                    if not matches_seed:
                        assert code == "UNMAPPED", (
                            f"amount {amount} matches no seeded fee_categories range "
                            f"but classified as {code!r}, expected UNMAPPED"
                        )
                    assert code is not None
            finally:
                await conn.close()

        _run(_inner())

    def test_card_monthly_and_combo_rules_hold_if_present_else_synthetic(self) -> None:
        """The sprint doc's explicit requirement: verify the CARD_MONTHLY
        (2000) rule and the 12500 bundle decomposition against live data IF
        either amount appears; otherwise cover the rule with a synthetic row
        inserted, transformed, checked, then cleaned up -- so the rule is
        never left unverified regardless of what the live pull currently
        contains."""

        async def _inner() -> None:
            conn = await _connect_or_skip()
            try:
                from_ts, to_ts = await _live_window_or_skip(conn)
                await transform_raw_to_dashboard(conn, from_ts=from_ts, to_ts=to_ts)

                has_2000 = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM eparking.raw_transactions WHERE amount = 2000.00)"
                )
                has_12500 = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM eparking.raw_transactions WHERE amount = 12500.00)"
                )

                if has_2000:
                    row = await conn.fetchrow(
                        "SELECT fee_category_code, revenue_stream, is_revenue, counts_as_entry, "
                        "card_component_monthly_count, card_component_monthly_amount, "
                        "card_component_annual_count "
                        "FROM eparking.dashboard_transactions WHERE amount = 2000.00 LIMIT 1"
                    )
                    assert row["fee_category_code"] == "CARD_MONTHLY"
                    assert row["revenue_stream"] == "card_subscription"
                    assert row["is_revenue"] is True
                    assert row["counts_as_entry"] is False
                    assert row["card_component_monthly_count"] == 1
                    assert row["card_component_monthly_amount"] == Decimal("2000.00")
                    assert row["card_component_annual_count"] == 0
                else:
                    tx_id = 999_999_990_001
                    try:
                        await _insert_synthetic_row(conn, tx_id=tx_id, amount="2000.00")
                        await transform_raw_to_dashboard(conn, from_ts=_FAR_PAST, to_ts=_FAR_FUTURE)
                        row = await conn.fetchrow(
                            "SELECT fee_category_code, card_component_monthly_count, "
                            "card_component_monthly_amount, card_component_annual_count "
                            "FROM eparking.dashboard_transactions WHERE paystack_transaction_id = $1",
                            tx_id,
                        )
                        assert row is not None
                        assert row["fee_category_code"] == "CARD_MONTHLY"
                        assert row["card_component_monthly_count"] == 1
                        assert row["card_component_monthly_amount"] == Decimal("2000.00")
                        assert row["card_component_annual_count"] == 0
                    finally:
                        await _delete_synthetic_row(conn, tx_id=tx_id)

                if has_12500:
                    row = await conn.fetchrow(
                        "SELECT fee_category_code, card_component_annual_count, "
                        "card_component_monthly_count, card_component_annual_amount, "
                        "card_component_monthly_amount "
                        "FROM eparking.dashboard_transactions WHERE amount = 12500.00 LIMIT 1"
                    )
                    # Corrected rule (migration 013): ONE first-time annual
                    # card, NOT an annual+monthly bundle. The embedded ₦2,000
                    # is a registration fee, not the cab-driver Monthly card,
                    # so monthly must be zero and annual carries the full
                    # ₦12,500.
                    assert row["fee_category_code"] == "CARD_COMBO_12500"
                    assert row["card_component_annual_count"] == 1
                    assert row["card_component_monthly_count"] == 0
                    assert row["card_component_annual_amount"] == Decimal("12500.00")
                    assert row["card_component_monthly_amount"] == Decimal("0.00")
                else:
                    tx_id = 999_999_990_002
                    try:
                        await _insert_synthetic_row(conn, tx_id=tx_id, amount="12500.00")
                        await transform_raw_to_dashboard(conn, from_ts=_FAR_PAST, to_ts=_FAR_FUTURE)
                        row = await conn.fetchrow(
                            "SELECT fee_category_code, card_component_annual_count, "
                            "card_component_monthly_count, card_component_annual_amount, "
                            "card_component_monthly_amount "
                            "FROM eparking.dashboard_transactions WHERE paystack_transaction_id = $1",
                            tx_id,
                        )
                        assert row is not None
                        assert row["fee_category_code"] == "CARD_COMBO_12500"
                        assert row["card_component_annual_count"] == 1
                        assert row["card_component_monthly_count"] == 0
                        assert row["card_component_annual_amount"] == Decimal("12500.00")
                        assert row["card_component_monthly_amount"] == Decimal("0.00")
                    finally:
                        await _delete_synthetic_row(conn, tx_id=tx_id)
            finally:
                await conn.close()

        _run(_inner())

    def test_first_time_annual_x2_and_batched_car_quantity(self) -> None:
        """Migration 013's corrected rules, covered with synthetic rows so
        they hold regardless of what the live window currently contains:

          ₦25,000 -> CARD_COMBO_ANNUAL_X2, annual 2/₦25,000, monthly 0/₦0.
          ₦900    -> resolves onto the BASE Car tier (TICKET_300) with
                     ticket_quantity = 3, amount preserved at ₦900.

        Plus the guard that makes the "explicit seeded multiples" design
        safe: an unconfirmed exact multiple of ₦300 (₦3,300) must STAY
        UNMAPPED with quantity 1. If someone later replaces this mechanism
        with generic `amount % 300 = 0` logic, this assertion is what fails.
        """

        async def _inner() -> None:
            conn = await _connect_or_skip()
            try:
                cases = {
                    999_999_990_003: ("25000.00", "CARD_COMBO_ANNUAL_X2"),
                    999_999_990_004: ("900.00", "TICKET_300"),
                    999_999_990_005: ("3300.00", "UNMAPPED"),
                }
                try:
                    for tx_id, (amount, _) in cases.items():
                        await _insert_synthetic_row(conn, tx_id=tx_id, amount=amount)
                    await transform_raw_to_dashboard(conn, from_ts=_FAR_PAST, to_ts=_FAR_FUTURE)

                    rows = {}
                    for tx_id in cases:
                        rows[tx_id] = await conn.fetchrow(
                            "SELECT fee_category_code, revenue_stream, vehicle_type, amount, "
                            "ticket_quantity, counts_as_entry, is_revenue, "
                            "card_component_annual_count, card_component_monthly_count, "
                            "card_component_annual_amount, card_component_monthly_amount "
                            "FROM eparking.dashboard_transactions "
                            "WHERE paystack_transaction_id = $1",
                            tx_id,
                        )

                    for tx_id, (_, expected_code) in cases.items():
                        assert rows[tx_id] is not None
                        assert rows[tx_id]["fee_category_code"] == expected_code

                    # ₦25,000 = two first-time annual cards, nothing monthly.
                    x2 = rows[999_999_990_003]
                    assert x2["revenue_stream"] == "card_subscription"
                    assert x2["card_component_annual_count"] == 2
                    assert x2["card_component_annual_amount"] == Decimal("25000.00")
                    assert x2["card_component_monthly_count"] == 0
                    assert x2["card_component_monthly_amount"] == Decimal("0.00")

                    # ₦900 = 3 x Car, reported as the base Car tier.
                    batched = rows[999_999_990_004]
                    assert batched["revenue_stream"] == "parking_ticket"
                    assert batched["vehicle_type"] == "Car"
                    assert batched["ticket_quantity"] == 3
                    assert batched["amount"] == Decimal("900.00")
                    assert batched["counts_as_entry"] is True
                    assert batched["is_revenue"] is True

                    # Unconfirmed multiple of 300 stays UNMAPPED, quantity 1.
                    unconfirmed = rows[999_999_990_005]
                    assert unconfirmed["ticket_quantity"] == 1
                    assert unconfirmed["is_revenue"] is False
                    assert unconfirmed["counts_as_entry"] is False
                finally:
                    for tx_id in cases:
                        await _delete_synthetic_row(conn, tx_id=tx_id)
            finally:
                await conn.close()

        _run(_inner())


class TestReclassifyIdempotencyAndScoping:
    def test_reclassify_twice_produces_identical_rows(self) -> None:
        async def _inner() -> None:
            conn = await _connect_or_skip()
            try:
                await _live_window_or_skip(conn)

                from_date = await conn.fetchval(
                    "SELECT (min(paid_at) AT TIME ZONE 'Africa/Lagos')::date FROM eparking.raw_transactions"
                )
                to_date = await conn.fetchval(
                    "SELECT (max(paid_at) AT TIME ZONE 'Africa/Lagos')::date FROM eparking.raw_transactions"
                )

                await reclassify_transactions(
                    conn, from_date=from_date, to_date=to_date, reason="pytest idempotency run 1"
                )
                snap1 = await _snapshot_dashboard(conn)

                await reclassify_transactions(
                    conn, from_date=from_date, to_date=to_date, reason="pytest idempotency run 2"
                )
                snap2 = await _snapshot_dashboard(conn)

                assert snap1 == snap2
            finally:
                await conn.close()

        _run(_inner())

    def test_editing_fee_category_and_reclassifying_changes_only_expected_rows(self) -> None:
        """Retire TICKET_600 (in a rolled-back transaction, never persisted)
        and confirm reclassify changes exactly the rows that were TICKET_600
        and nothing else."""

        async def _inner() -> None:
            conn = await _connect_or_skip()
            from_ts, to_ts = await _live_window_or_skip(conn)

            tx = conn.transaction()
            await tx.start()
            try:
                from_date = await conn.fetchval(
                    "SELECT (min(paid_at) AT TIME ZONE 'Africa/Lagos')::date FROM eparking.raw_transactions"
                )
                to_date = await conn.fetchval(
                    "SELECT (max(paid_at) AT TIME ZONE 'Africa/Lagos')::date FROM eparking.raw_transactions"
                )

                # Ensure a stable baseline first.
                await transform_raw_to_dashboard(conn, from_ts=from_ts, to_ts=to_ts)
                before = {
                    r["paystack_transaction_id"]: r["fee_category_code"]
                    for r in await conn.fetch(
                        "SELECT paystack_transaction_id, fee_category_code FROM eparking.dashboard_transactions"
                    )
                }
                had_ticket_600 = any(v == "TICKET_600" for v in before.values())
                if not had_ticket_600:
                    await tx.rollback()
                    pytest.skip("no TICKET_600 (amount=600) rows in current live window to test against")

                await conn.execute(
                    "UPDATE eparking.fee_categories SET effective_to = '2020-01-02' "
                    "WHERE code = 'TICKET_600'"
                )
                await reclassify_transactions(
                    conn, from_date=from_date, to_date=to_date, reason="pytest edit-scoping test"
                )

                after = {
                    r["paystack_transaction_id"]: r["fee_category_code"]
                    for r in await conn.fetch(
                        "SELECT paystack_transaction_id, fee_category_code FROM eparking.dashboard_transactions"
                    )
                }

                changed = {k for k in before if before[k] != after[k]}
                expected_changed = {k for k, v in before.items() if v == "TICKET_600"}

                assert changed == expected_changed
                assert all(after[k] == "UNMAPPED" for k in changed)
            finally:
                await tx.rollback()
                await conn.close()

        _run(_inner())
