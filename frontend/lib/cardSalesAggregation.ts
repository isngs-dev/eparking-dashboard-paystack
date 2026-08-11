/**
 * Adaptive client-side aggregation for Card Sales (Sprint 6 confirmed
 * decision #2): the real `/api/cards/breakdown` endpoint is day-grain only.
 *   <=14 days   -> one bar-group per day
 *   15-120 days -> ISO-week bar-groups (label "W{isoWeek}")
 *   >120 days   -> month bar-groups
 */

import type { CardBreakdownDayPoint } from "./api/types";
import { daySpan, formatShortDate, isoWeek, isoWeekKey, monthKey, monthLabel } from "./format";

export interface AggregatedCardPoint {
  key: string;
  label: string;
  annual_count: number;
  annual_amount: number;
  monthly_count: number;
  monthly_amount: number;
}

export function aggregateCardBreakdown(
  points: CardBreakdownDayPoint[],
  dateFrom: string,
  dateTo: string,
): AggregatedCardPoint[] {
  const span = daySpan(dateFrom, dateTo);

  if (span <= 14) {
    return points.map((p) => ({
      key: p.date,
      label: formatShortDate(p.date),
      annual_count: p.annual_count,
      annual_amount: p.annual_amount,
      monthly_count: p.monthly_count,
      monthly_amount: p.monthly_amount,
    }));
  }

  const keyFn = span <= 120 ? isoWeekKey : monthKey;
  const labelFn = span <= 120 ? (key: string) => `W${isoWeekForKey(key)}` : monthLabel;

  const buckets = new Map<string, AggregatedCardPoint>();
  for (const p of points) {
    const key = keyFn(p.date);
    const existing = buckets.get(key);
    if (existing) {
      existing.annual_count += p.annual_count;
      existing.annual_amount += p.annual_amount;
      existing.monthly_count += p.monthly_count;
      existing.monthly_amount += p.monthly_amount;
    } else {
      buckets.set(key, {
        key,
        label: labelFn(key),
        annual_count: p.annual_count,
        annual_amount: p.annual_amount,
        monthly_count: p.monthly_count,
        monthly_amount: p.monthly_amount,
      });
    }
  }

  return Array.from(buckets.values()).sort((a, b) => (a.key < b.key ? -1 : 1));
}

function isoWeekForKey(weekKey: string): number {
  // weekKey format "2026-W32"
  const match = /-W(\d+)$/.exec(weekKey);
  return match ? Number(match[1]) : 0;
}

export { isoWeek };
