"""Turns a validated `CommonFilters` into a parameterized SQL WHERE fragment.

Centralized so every repository builds filter predicates identically instead
of re-deriving the placeholder bookkeeping per query. Values are always bound
via `$n` placeholders -- `vehicle_types`/`days` were already allowlisted in
`app.core.filters` before reaching here, but we never string-interpolate
them into SQL regardless.
"""

from __future__ import annotations

from app.core.filters import CommonFilters


def build_where(
    filters: CommonFilters,
    *,
    date_column: str,
    vehicle_type_column: str | None = None,
    day_of_week_column: str | None = None,
    start_param_index: int = 1,
) -> tuple[str, list]:
    """Returns (sql_fragment, params). sql_fragment starts with "AND ..." or
    is empty; params must be appended to the caller's existing param list at
    `start_param_index`.
    """
    clauses: list[str] = []
    params: list = []
    idx = start_param_index

    if filters.date_from is not None:
        clauses.append(f"{date_column} >= ${idx}")
        params.append(filters.date_from)
        idx += 1
    if filters.date_to is not None:
        clauses.append(f"{date_column} <= ${idx}")
        params.append(filters.date_to)
        idx += 1
    if filters.vehicle_types and vehicle_type_column:
        clauses.append(f"{vehicle_type_column} = ANY(${idx}::text[])")
        params.append(list(filters.vehicle_types))
        idx += 1
    if filters.days and day_of_week_column:
        clauses.append(f"{day_of_week_column} = ANY(${idx}::smallint[])")
        params.append(list(filters.days))
        idx += 1

    if not clauses:
        return "", params
    return " AND " + " AND ".join(clauses), params
