"""Calendar-to-date windows used by the executive revenue KPIs."""

from __future__ import annotations

from datetime import date, timedelta


KPIWindowDefinition = tuple[date, date, str]


def _compact_range(date_from: date, date_to: date) -> str:
    if date_from == date_to:
        return f"{date_from.day} {date_from:%b}"
    if date_from.month == date_to.month and date_from.year == date_to.year:
        return f"{date_from.day}–{date_to.day} {date_to:%b}"
    return f"{date_from.day} {date_from:%b}–{date_to.day} {date_to:%b}"


def revenue_kpi_windows(today: date) -> dict[str, KPIWindowDefinition]:
    """Daily, Monday-based week-to-date, and month-to-date windows."""
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    return {
        "daily": (today, today, "Today"),
        "weekly": (
            week_start,
            today,
            f"Week to date · {_compact_range(week_start, today)}",
        ),
        "monthly": (
            month_start,
            today,
            f"Month to date · {_compact_range(month_start, today)}",
        ),
    }
