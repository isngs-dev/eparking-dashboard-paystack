/**
 * Currency/number/date formatting helpers. Currency always renders the real
 * naira sign U+20A6 (₦) -- never the mock's mojibake artifact.
 */

const NAIRA = "₦"; // ₦

export function formatNaira(value: number): string {
  return `${NAIRA}${Math.round(value).toLocaleString("en-NG")}`;
}

/** Compact k/m-suffixed naira for axis labels / donut center text, e.g. ₦150k. */
export function formatCompactNaira(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) {
    return `${NAIRA}${trimDecimal(value / 1_000_000)}m`;
  }
  if (abs >= 1_000) {
    return `${NAIRA}${trimDecimal(value / 1_000)}k`;
  }
  return `${NAIRA}${Math.round(value).toLocaleString("en-NG")}`;
}

function trimDecimal(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export function formatPct(value: number, digits = 1): string {
  return `${value.toFixed(digits)}%`;
}

export function formatDeltaPct(value: number | null, digits = 1): string | null {
  if (value === null) return null;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatInt(value: number): string {
  return value.toLocaleString("en-NG");
}

/** "2026-08-08" -> "Aug 8" */
export function formatShortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-NG", { month: "short", day: "numeric" });
}

/** "2026-08-08" -> "Aug 8, 2026" */
export function formatFullDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-NG", { month: "short", day: "numeric", year: "numeric" });
}

const HOUR_LABELS = [
  "12AM", "1AM", "2AM", "3AM", "4AM", "5AM", "6AM", "7AM", "8AM", "9AM", "10AM", "11AM",
  "12PM", "1PM", "2PM", "3PM", "4PM", "5PM", "6PM", "7PM", "8PM", "9PM", "10PM", "11PM",
];

export function formatHour(hour: number): string {
  return HOUR_LABELS[((hour % 24) + 24) % 24];
}

/** e.g. start=15 end=17 -> "3PM - 5PM" (handles midnight wrap upstream, this just labels endpoints). */
export function formatHourBand(start: number, end: number): string {
  return `${formatHour(start)} – ${formatHour(end)}`;
}

const DOW_LABELS: Record<number, string> = {
  1: "Monday",
  2: "Tuesday",
  3: "Wednesday",
  4: "Thursday",
  5: "Friday",
  6: "Saturday",
  7: "Sunday",
};

const DOW_SHORT: Record<number, string> = {
  1: "Mon",
  2: "Tue",
  3: "Wed",
  4: "Thu",
  5: "Fri",
  6: "Sat",
  7: "Sun",
};

export function dayOfWeekLabel(dow: number): string {
  return DOW_LABELS[dow] ?? String(dow);
}

export function dayOfWeekShort(dow: number): string {
  return DOW_SHORT[dow] ?? String(dow);
}

/** Inclusive day count between two ISO dates. */
export function daySpan(from: string, to: string): number {
  const a = new Date(`${from}T00:00:00`);
  const b = new Date(`${to}T00:00:00`);
  return Math.round((b.getTime() - a.getTime()) / 86_400_000) + 1;
}

/** ISO 8601 week number for a given ISO date string, e.g. "2026-08-08" -> 32. */
export function isoWeek(iso: string): number {
  const date = new Date(`${iso}T00:00:00`);
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7);
}

/** e.g. "2026-08-08" -> "2026-W32" (used as an aggregation bucket key, not display). */
export function isoWeekKey(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((d.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

/** "2026-08-08" -> "2026-08" (month bucket key). */
export function monthKey(iso: string): string {
  return iso.slice(0, 7);
}

export function monthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1, 1));
  return d.toLocaleDateString("en-NG", { month: "short", year: "2-digit", timeZone: "UTC" });
}
