/**
 * Filter-state helpers. State lives entirely in the URL query string, param
 * names matching the API's own (`from`, `to`, `vehicle_types`, `days`) so
 * there's no translation layer. `<FilterBar>` is the only stateful client
 * component driving navigation; every visual is an async server component
 * reading from `searchParams`.
 */

export interface ResolvedFilters {
  from?: string;
  to?: string;
  vehicle_types?: string;
  days?: string;
}

export type SearchParams = Record<string, string | string[] | undefined>;

function firstValue(v: string | string[] | undefined): string | undefined {
  if (Array.isArray(v)) return v[0];
  return v;
}

/** Business-timezone "today" minus 29 days through today -- matches the API's own default window. */
export function defaultDateRange(today: Date = new Date()): { from: string; to: string } {
  const to = toIsoDate(today);
  const fromDate = new Date(today);
  fromDate.setDate(fromDate.getDate() - 29);
  const from = toIsoDate(fromDate);
  return { from, to };
}

function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Reads filters from Next's `searchParams`, filling in the default date range if absent. */
export function resolveFilters(searchParams: SearchParams): ResolvedFilters {
  const from = firstValue(searchParams.from);
  const to = firstValue(searchParams.to);
  const vehicle_types = firstValue(searchParams.vehicle_types);
  const days = firstValue(searchParams.days);

  if (from && to) {
    return { from, to, vehicle_types, days };
  }
  const defaults = defaultDateRange();
  return {
    from: from ?? defaults.from,
    to: to ?? defaults.to,
    vehicle_types,
    days,
  };
}

/**
 * Which filter *kinds* are currently active per the URL -- date range is
 * always considered active since it always has an effective value
 * (explicit or defaulted); vehicle_types/days are active only when set.
 */
export function activeFilterKinds(
  filters: ResolvedFilters,
): ("date" | "vehicle_types" | "days")[] {
  const active: ("date" | "vehicle_types" | "days")[] = ["date"];
  if (filters.vehicle_types) active.push("vehicle_types");
  if (filters.days) active.push("days");
  return active;
}

export const DAY_OPTIONS: { value: string; label: string }[] = [
  { value: "1", label: "Monday" },
  { value: "2", label: "Tuesday" },
  { value: "3", label: "Wednesday" },
  { value: "4", label: "Thursday" },
  { value: "5", label: "Friday" },
  { value: "6", label: "Saturday" },
  { value: "7", label: "Sunday" },
];
