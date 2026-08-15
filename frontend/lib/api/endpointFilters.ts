/**
 * Capability map: which global filters (`date`, `vehicle_types`, `days`)
 * each endpoint actually honours. Several endpoints ignore some/all filters
 * by design (verified in services/api/app/repositories/revenue.py and
 * occupancy.py, and each router's own docstring) -- this is real backend
 * behavior, not a bug. Drives both the request params we send AND a visible
 * per-card footnote so the UI never silently implies a filter did something
 * it didn't.
 *
 * date  -> honors `from`/`to`
 * vtype -> honors `vehicle_types`
 * days  -> honors `days`
 */

export type FilterKind = "date" | "vehicle_types" | "days";

export type EndpointKey =
  | "overview_summary"
  | "revenue_trend"
  | "vehicle_type_distribution"
  | "cards_breakdown"
  | "cards_total"
  | "tickets_daily_by_tier"
  | "revenue_total_collection"
  | "revenue_split"
  | "occupancy_entry_count"
  | "occupancy_by_hour"
  | "occupancy_peak_hours"
  | "occupancy_weekly_pattern"
  | "traffic_today";

export const ENDPOINT_FILTERS: Record<EndpointKey, FilterKind[]> = {
  // Fixed calendar-to-date windows (Today/WTD/MTD) -- ignores all global filters.
  overview_summary: [],
  // Vehicle type limits tickets; untyped card revenue remains included.
  revenue_trend: ["date", "vehicle_types", "days"],
  // Honors all filters.
  vehicle_type_distribution: ["date", "vehicle_types", "days"],
  // Cards have no vehicle_type; honors from/to/days.
  cards_breakdown: ["date", "days"],
  cards_total: ["date", "days"],
  // Honors all filters.
  tickets_daily_by_tier: ["date", "vehicle_types", "days"],
  // Vehicle type limits tickets; untyped card revenue remains included.
  revenue_total_collection: ["date", "vehicle_types", "days"],
  revenue_split: ["date", "vehicle_types", "days"],
  // Honors all filters.
  occupancy_entry_count: ["date", "vehicle_types", "days"],
  occupancy_by_hour: ["date", "vehicle_types", "days"],
  occupancy_peak_hours: ["date", "vehicle_types", "days"],
  occupancy_weekly_pattern: ["date", "vehicle_types", "days"],
  // Ignores every filter param -- always pinned to business-today.
  traffic_today: [],
};

export function ignoredFilters(
  key: EndpointKey,
  active: FilterKind[],
): FilterKind[] {
  const honored = new Set(ENDPOINT_FILTERS[key]);
  return active.filter((f) => !honored.has(f));
}

const FILTER_LABEL: Record<FilterKind, string> = {
  date: "date range",
  vehicle_types: "vehicle type",
  days: "day",
};

/** Human-readable footnote, e.g. "Ignores the date range and vehicle type filters." */
export function ignoredFiltersFootnote(key: EndpointKey, active: FilterKind[]): string | null {
  const ignored = ignoredFilters(key, active);
  if (ignored.length === 0) return null;
  const labels = ignored.map((f) => FILTER_LABEL[f]);
  const joined =
    labels.length === 1
      ? labels[0]
      : `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
  const verb = labels.length === 1 ? "filter" : "filters";
  return `Ignores the ${joined} ${verb}.`;
}
