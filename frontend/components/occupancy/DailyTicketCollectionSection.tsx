import { getTicketsDailyByTier } from "@/lib/api/client";
import { tryFetch } from "@/lib/tryFetch";
import { activeFilterKinds, type ResolvedFilters } from "@/lib/filters";
import { pivotTicketsByTier } from "@/lib/ticketPivot";
import { formatCompactNaira, formatFullDate, formatInt, formatNaira, formatShortDate } from "@/lib/format";
import { vehicleTypeColorVar, VEHICLE_TYPE_PRICE } from "@/lib/seriesColors";
import { SectionCard } from "@/components/primitives/SectionCard";
import { LegendChips } from "@/components/primitives/LegendChips";
import { StackedBarChart } from "@/components/charts/StackedBarChart";
import { FilterFootnote } from "@/components/primitives/FilterFootnote";
import { ErrorCard } from "@/components/primitives/ErrorCard";

function niceYLabels(maxValue: number): string[] {
  const steps = 5;
  const out: string[] = [];
  for (let i = steps - 1; i >= 0; i--) {
    out.push(formatCompactNaira((maxValue / (steps - 1)) * i));
  }
  return out;
}

export async function DailyTicketCollectionSection({ filters }: { filters: ResolvedFilters }) {
  const { data: res, errorMessage } = await tryFetch(() => getTicketsDailyByTier(filters));
  if (!res) {
    return <ErrorCard title="Daily Ticket Collection" message={errorMessage!} span={2} />;
  }
  const { days, tiersPresent } = pivotTicketsByTier(
    res.points,
    res.date_range.date_from,
    res.date_range.date_to,
  );

  const groups = days.map((d) => ({
    label: formatShortDate(d.date),
    segments: tiersPresent.map((tier) => ({
      seriesKey: tier,
      colorVar: vehicleTypeColorVar(tier),
      value: d.tiers[tier].ticket_amount,
    })),
  }));

  const maxTotal = Math.max(...days.map((d) => d.dayTotalAmount), 1);

  return (
    <SectionCard
      span={2}
      title="Daily Ticket Collection"
      subtitle="Stacked by fee tier"
      headerRight={
        <LegendChips
          items={tiersPresent.map((tier) => ({
            colorVar: vehicleTypeColorVar(tier),
            label: `${tier} ₦${(VEHICLE_TYPE_PRICE[tier] ?? 0).toLocaleString("en-NG")}`,
          }))}
        />
      }
    >
      <StackedBarChart
        groups={groups}
        yLabels={niceYLabels(maxTotal)}
        tooltips={days.map((d) => ({
          dayTotal: {
            title: formatFullDate(d.date),
            rows: [
              { label: "Day total", value: formatNaira(d.dayTotalAmount) },
              { label: "Tickets", value: formatInt(d.dayTotalCount) },
            ],
          },
          bySeries: tiersPresent.reduce<Record<string, { title: string; rows: { label: string; value: string }[] }>>(
            (acc, tier) => {
              const seg = d.tiers[tier];
              acc[tier] = {
                title: formatFullDate(d.date),
                rows: [
                  { label: tier, value: formatNaira(seg.ticket_amount) },
                  { label: "Tickets", value: formatInt(seg.ticket_count) },
                  { label: "Day total", value: formatNaira(d.dayTotalAmount) },
                ],
              };
              return acc;
            },
            {},
          ),
        }))}
      />
      <FilterFootnote endpoint="tickets_daily_by_tier" activeFilters={activeFilterKinds(filters)} />
    </SectionCard>
  );
}
