/**
 * Pure date-grid helpers for <DateRangePicker>. No React, no DOM -- exchanges
 * only YYYY-MM-DD ISO strings with the rest of the app. Internally uses
 * UTC-noon Date objects so month/day arithmetic is immune to DST shifts.
 */

/** "2026-08-09" -> Date at 12:00 UTC on that calendar day. */
export function parseIso(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d, 12));
}

/** Inverse of parseIso. Reads UTC parts, so it round-trips exactly. */
export function toIso(d: Date): string {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Today in the *user's local* calendar, as ISO -- matches defaultDateRange()'s notion of "today". */
export function todayIso(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}

export function addDays(iso: string, n: number): string {
  const d = parseIso(iso);
  d.setUTCDate(d.getUTCDate() + n);
  return toIso(d);
}

/** month cursor is itself an ISO string pinned to the 1st, e.g. "2026-08-01" */
export function monthStart(iso: string): string {
  return `${iso.slice(0, 7)}-01`;
}

export function addMonths(monthIso: string, n: number): string {
  const d = parseIso(monthIso);
  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() + n);
  return toIso(d);
}

/** "August 2026" */
export function monthTitle(monthIso: string): string {
  return parseIso(monthIso).toLocaleDateString("en-NG", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export interface GridCell {
  iso: string;
  inMonth: boolean;
}

/**
 * Always exactly 42 cells (6 weeks), Sunday-first, so the popover never
 * changes height when navigating months -- a jumping popover would itself
 * feel glitchy.
 */
export function buildMonthGrid(monthIso: string): GridCell[] {
  const first = parseIso(monthStart(monthIso));
  const monthNum = first.getUTCMonth();
  const lead = first.getUTCDay(); // 0=Sun .. 6=Sat
  const start = new Date(first);
  start.setUTCDate(start.getUTCDate() - lead);

  const cells: GridCell[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start);
    d.setUTCDate(d.getUTCDate() + i);
    cells.push({ iso: toIso(d), inMonth: d.getUTCMonth() === monthNum });
  }
  return cells;
}

export const WEEKDAY_LABELS = ["S", "M", "T", "W", "T", "F", "S"];

/** Lexicographic comparison is correct for zero-padded ISO dates. */
export function isBefore(a: string, b: string) {
  return a < b;
}
export function isAfter(a: string, b: string) {
  return a > b;
}
export function isBetween(x: string, a: string, b: string) {
  return x >= a && x <= b;
}
