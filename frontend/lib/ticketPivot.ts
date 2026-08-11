/**
 * Client-side pivot for Daily Ticket Collection. The real endpoint returns
 * one sparse row per (date, vehicle_type) -- not pre-pivoted. We build a
 * Map<date, Map<vehicle_type, {ticket_count, ticket_amount}>>, derive the
 * date axis from the response's date_range (so zero-ticket days still get a
 * bar slot), and derive the tier legend from the union of vehicle_type
 * values actually present, in the fixed ascending fee-tier order.
 */

import type { TicketTierDayPoint } from "./api/types";
import { VEHICLE_TYPE_ORDER } from "./seriesColors";

export interface PivotedDay {
  date: string;
  tiers: Record<string, { ticket_count: number; ticket_amount: number }>;
  dayTotalAmount: number;
  dayTotalCount: number;
}

export interface PivotResult {
  days: PivotedDay[];
  tiersPresent: string[]; // fixed ascending order, only tiers actually present anywhere in range
}

function eachDate(from: string, to: string): string[] {
  const out: string[] = [];
  const d = new Date(`${from}T00:00:00`);
  const end = new Date(`${to}T00:00:00`);
  while (d <= end) {
    out.push(d.toISOString().slice(0, 10));
    d.setDate(d.getDate() + 1);
  }
  return out;
}

export function pivotTicketsByTier(
  points: TicketTierDayPoint[],
  dateFrom: string,
  dateTo: string,
): PivotResult {
  const byDate = new Map<string, Map<string, { ticket_count: number; ticket_amount: number }>>();
  const tiersSeen = new Set<string>();

  for (const p of points) {
    tiersSeen.add(p.vehicle_type);
    if (!byDate.has(p.date)) byDate.set(p.date, new Map());
    byDate.get(p.date)!.set(p.vehicle_type, {
      ticket_count: p.ticket_count,
      ticket_amount: p.ticket_amount,
    });
  }

  const tiersPresent = VEHICLE_TYPE_ORDER.filter((t) => tiersSeen.has(t));
  // Include any unexpected tier not in the known order at the end, defensively.
  for (const t of tiersSeen) {
    if (!tiersPresent.includes(t)) tiersPresent.push(t);
  }

  const dateAxis = eachDate(dateFrom, dateTo);
  const days: PivotedDay[] = dateAxis.map((date) => {
    const tierMap = byDate.get(date);
    const tiers: Record<string, { ticket_count: number; ticket_amount: number }> = {};
    let dayTotalAmount = 0;
    let dayTotalCount = 0;
    for (const tier of tiersPresent) {
      const v = tierMap?.get(tier) ?? { ticket_count: 0, ticket_amount: 0 };
      tiers[tier] = v;
      dayTotalAmount += v.ticket_amount;
      dayTotalCount += v.ticket_count;
    }
    return { date, tiers, dayTotalAmount, dayTotalCount };
  });

  return { days, tiersPresent };
}
