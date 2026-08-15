from datetime import date
from unittest import TestCase

from app.core.filters import CommonFilters
from app.repositories.revenue import _filtered_daily_revenue_sql


class FilteredDailyRevenueSqlTests(TestCase):
    def test_vehicle_filter_applies_to_tickets_but_not_cards(self) -> None:
        sql, params = _filtered_daily_revenue_sql(
            CommonFilters(
                date_from=date(2026, 8, 1),
                date_to=date(2026, 8, 15),
                vehicle_types=("Car",),
                days=(1,),
            )
        )

        self.assertIn("day_of_week = ANY($3::smallint[])", sql)
        self.assertIn("vehicle_type = ANY($4::text[])", sql)
        self.assertIn("revenue_stream = 'card_subscription'", sql)
        self.assertNotIn("AND vehicle_type = ANY($4::text[])\n        GROUP BY", sql)
        self.assertEqual(
            params,
            [date(2026, 8, 1), date(2026, 8, 15), [1], ["Car"]],
        )

    def test_no_vehicle_filter_preserves_all_ticket_and_card_revenue(self) -> None:
        sql, params = _filtered_daily_revenue_sql(
            CommonFilters(
                date_from=date(2026, 8, 1),
                date_to=date(2026, 8, 15),
                vehicle_types=None,
                days=None,
            )
        )

        self.assertNotIn("vehicle_type = ANY", sql)
        self.assertIn("revenue_stream = 'parking_ticket'", sql)
        self.assertIn("revenue_stream = 'card_subscription'", sql)
        self.assertEqual(params, [date(2026, 8, 1), date(2026, 8, 15)])
