import { getCardsBreakdown } from "@/lib/api/client";
import { tryFetch } from "@/lib/tryFetch";
import { activeFilterKinds, type ResolvedFilters } from "@/lib/filters";
import { aggregateCardBreakdown } from "@/lib/cardSalesAggregation";
import { daySpan, formatCompactNaira, formatInt, formatNaira } from "@/lib/format";
import { SectionCard } from "@/components/primitives/SectionCard";
import { LegendChips } from "@/components/primitives/LegendChips";
import { GroupedBarChart } from "@/components/charts/GroupedBarChart";
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

function grainLabel(span: number): "day" | "week" | "month" {
  if (span <= 14) return "day";
  if (span <= 120) return "week";
  return "month";
}

export async function CardSalesSection({ filters }: { filters: ResolvedFilters }) {
  const { data: breakdown, errorMessage } = await tryFetch(() => getCardsBreakdown(filters));
  if (!breakdown) {
    return <ErrorCard title="Card Sales" message={errorMessage!} span={3} />;
  }
  const span = daySpan(breakdown.date_range.date_from, breakdown.date_range.date_to);
  const aggregated = aggregateCardBreakdown(
    breakdown.points,
    breakdown.date_range.date_from,
    breakdown.date_range.date_to,
  );

  const groups = aggregated.map((p) => ({
    label: p.label,
    values: [
      { seriesKey: "annual", colorVar: "--s1", value: p.annual_amount },
      { seriesKey: "monthly", colorVar: "--s3", value: p.monthly_amount },
    ],
  }));

  const maxValue = Math.max(...groups.flatMap((g) => g.values.map((v) => v.value)), 1);

  return (
    <SectionCard
      span={3}
      title="Card Sales"
      subtitle={`Annual (Shop Owners) vs Monthly (Green Cabs), by ${grainLabel(span)}`}
      headerRight={
        <LegendChips
          items={[
            { colorVar: "--s1", label: "Annual (Shop Owners) ₦10,500" },
            { colorVar: "--s3", label: "Monthly (Green Cabs) ₦2,000" },
          ]}
        />
      }
    >
      <GroupedBarChart
        groups={groups}
        yLabels={niceYLabels(maxValue)}
        tooltips={aggregated.map((p) => ({
          annual: {
            title: p.label,
            rows: [
              { label: "Annual (Shop Owners) amount", value: formatNaira(p.annual_amount) },
              { label: "Cards sold", value: formatInt(p.annual_count) },
            ],
          },
          monthly: {
            title: p.label,
            rows: [
              { label: "Monthly (Green Cabs) amount", value: formatNaira(p.monthly_amount) },
              { label: "Cards sold", value: formatInt(p.monthly_count) },
            ],
          },
        }))}
      />
      <FilterFootnote endpoint="cards_breakdown" activeFilters={activeFilterKinds(filters)} />
    </SectionCard>
  );
}
