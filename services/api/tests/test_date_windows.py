from datetime import date
from unittest import TestCase

from app.core.date_windows import revenue_kpi_windows, vehicle_kpi_windows


class RevenueKpiWindowsTests(TestCase):
    def test_midweek_and_midmonth_are_calendar_to_date(self) -> None:
        windows = revenue_kpi_windows(date(2026, 8, 13))

        self.assertEqual(
            windows["weekly"],
            (date(2026, 8, 10), date(2026, 8, 13), "Week to date · 10–13 Aug"),
        )
        self.assertEqual(
            windows["monthly"],
            (date(2026, 8, 1), date(2026, 8, 13), "Month to date · 1–13 Aug"),
        )
        self.assertEqual(
            windows["yearly"],
            (date(2026, 1, 1), date(2026, 8, 13), "Year to date · 1 Jan–13 Aug"),
        )

    def test_week_is_complete_on_sunday(self) -> None:
        windows = revenue_kpi_windows(date(2026, 8, 16))

        self.assertEqual(windows["weekly"][:2], (date(2026, 8, 10), date(2026, 8, 16)))

    def test_week_resets_on_monday(self) -> None:
        windows = revenue_kpi_windows(date(2026, 8, 17))

        self.assertEqual(
            windows["weekly"],
            (date(2026, 8, 17), date(2026, 8, 17), "Week to date · 17 Aug"),
        )

    def test_month_resets_on_first_day(self) -> None:
        windows = revenue_kpi_windows(date(2026, 9, 1))

        self.assertEqual(
            windows["monthly"],
            (date(2026, 9, 1), date(2026, 9, 1), "Month to date · 1 Sep"),
        )

    def test_year_resets_on_new_years_day(self) -> None:
        windows = revenue_kpi_windows(date(2027, 1, 1))

        self.assertEqual(
            windows["yearly"],
            (date(2027, 1, 1), date(2027, 1, 1), "Year to date · 1 Jan"),
        )


class VehicleKpiWindowsTests(TestCase):
    def test_vehicle_windows_use_the_same_calendar_boundaries(self) -> None:
        windows = vehicle_kpi_windows(date(2026, 8, 13))

        self.assertEqual(windows["daily"][:2], (date(2026, 8, 13), date(2026, 8, 13)))
        self.assertEqual(windows["weekly"][:2], (date(2026, 8, 10), date(2026, 8, 13)))
        self.assertEqual(windows["monthly"][:2], (date(2026, 8, 1), date(2026, 8, 13)))
        self.assertEqual(windows["yearly"][:2], (date(2026, 1, 1), date(2026, 8, 13)))

    def test_vehicle_month_and_year_reset_on_new_years_day(self) -> None:
        windows = vehicle_kpi_windows(date(2027, 1, 1))

        expected = (date(2027, 1, 1), date(2027, 1, 1))
        self.assertEqual(windows["daily"][:2], expected)
        self.assertEqual(windows["monthly"][:2], expected)
        self.assertEqual(windows["yearly"][:2], expected)
        self.assertEqual(windows["weekly"][:2], (date(2026, 12, 28), date(2027, 1, 1)))
