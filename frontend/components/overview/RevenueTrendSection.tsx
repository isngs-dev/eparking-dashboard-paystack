import { getRevenueTrend } from "@/lib/api/client";
import { tryFetch } from "@/lib/tryFetch";
import { activeFilterKinds, type ResolvedFilters } from "@/lib/filters";
import { formatCompactNaira, formatFullDate, formatInt, formatNaira, formatShortDate } from "@/lib/format";
import { SectionCard } from "@/components/primitives/SectionCard";
import { LegendChips } from "@/components/primitives/LegendChips";
import { SmoothAreaChart } from "@/components/charts/SmoothAreaChart";
import { FilterFootnote } from "@/components/primitives/FilterFootnote";
import { ExportButton } from "@/components/primitives/ExportButton";
import { ErrorCard } from "@/components/primitives/ErrorCard";

function niceYLabels(maxValue: number): string[] {
  const steps = 5;
  const out: string[] = [];
  for (let i = steps - 1; i >= 0; i--) {
    out.push(formatCompactNaira((maxValue / (steps - 1)) * i));
  }
  return out;
}

export async function RevenueTrendSection({ filters }: { filters: ResolvedFilters }) {
  const { data: trend, errorMessage } = await tryFetch(() => getRevenueTrend(filters));
  if (!trend) {
    return <ErrorCard title="Revenue Trend" message={errorMessage!} span={3} />;
  }
  const values = trend.points.map((p) => p.total_collection);
  const maxValue = Math.max(...values, 1);

  return (
    <SectionCard
      span={3}
      title="Revenue Trend"
      subtitle={`Total collection per day · ${trend.date_range.date_from} to ${trend.date_range.date_to}`}
      headerRight={
        <>
          <LegendChips items={[{ colorVar: "--s1", label: "Total collection" }]} />
          <ExportButton
            eventName="eparking:export-primary"
            filename="revenue-trend.csv"
            rows={trend.points.map((p) => ({
              date: p.date,
              total_collection: p.total_collection,
              ticket_amount: p.ticket_amount,
              card_total_amount: p.card_total_amount,
              transaction_count_total: p.transaction_count_total,
            }))}
          />
        </>
      }
    >
      <SmoothAreaChart
        values={values}
        xLabels={trend.points.map((p) => formatShortDate(p.date))}
        yLabels={niceYLabels(maxValue)}
        tooltips={trend.points.map((p) => ({
          title: formatFullDate(p.date),
          rows: [
            { label: "Total collection", value: formatNaira(p.total_collection) },
            { label: "Transactions", value: formatInt(p.transaction_count_total) },
            { label: "Card total", value: formatNaira(p.card_total_amount) },
          ],
        }))}
      />
      <FilterFootnote endpoint="revenue_trend" activeFilters={activeFilterKinds(filters)} />
    </SectionCard>
  );
}
