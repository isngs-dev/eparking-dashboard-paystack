import { getOccupancyByHour, getPeakHours } from "@/lib/api/client";
import { tryFetch } from "@/lib/tryFetch";
import { activeFilterKinds, type ResolvedFilters } from "@/lib/filters";
import { formatHour, formatHourBand, formatInt, formatPct } from "@/lib/format";
import { SectionCard } from "@/components/primitives/SectionCard";
import { SmoothAreaChart, type PeakBandRect } from "@/components/charts/SmoothAreaChart";
import { FilterFootnote } from "@/components/primitives/FilterFootnote";
import { ErrorCard } from "@/components/primitives/ErrorCard";

function niceIntYLabels(maxValue: number): string[] {
  const steps = 5;
  const out: string[] = [];
  for (let i = steps - 1; i >= 0; i--) {
    out.push(formatInt(Math.round((maxValue / (steps - 1)) * i)));
  }
  return out;
}

/** Handles a band that wraps past midnight -- renders as two rects, not one with negative width. */
function peakBandRects(start: number | null, end: number | null): PeakBandRect[] {
  if (start === null || end === null) return [];
  const bandLabel = `PEAK BAND · ${formatHourBand(start, end)}`;
  if (end >= start) {
    return [{ x0: start / 24, x1: (end + 1) / 24, label: bandLabel }];
  }
  // wraps past midnight: [start, 23] and [0, end]
  return [
    { x0: start / 24, x1: 1, label: bandLabel },
    { x0: 0, x1: (end + 1) / 24 },
  ];
}

export async function OccupancyByHourSection({ filters }: { filters: ResolvedFilters }) {
  const [byHourRes, peakRes] = await Promise.all([
    tryFetch(() => getOccupancyByHour(filters)),
    tryFetch(() => getPeakHours(filters)),
  ]);
  if (!byHourRes.data || !peakRes.data) {
    const message = byHourRes.errorMessage ?? peakRes.errorMessage ?? "Failed to load.";
    return <ErrorCard title="Occupancy by Time of Day" message={message} span={2} />;
  }
  const byHour = byHourRes.data;
  const peak = peakRes.data;
  const values = byHour.points.map((p) => p.total_count);
  const totalAll = values.reduce((s, v) => s + v, 0);
  const maxValue = Math.max(...values, 1);

  return (
    <SectionCard
      span={2}
      title="Occupancy by Time of Day"
      infoTitle="Ticket payments bucketed by transaction hour — a proxy for occupancy, not a sensor reading."
      subtitle="Average tickets per hour"
    >
      <SmoothAreaChart
        values={values}
        xLabels={byHour.points.map((p) => formatHour(p.hour))}
        yLabels={niceIntYLabels(maxValue)}
        xLabelCount={8}
        peakBands={peakBandRects(peak.peak_band_start, peak.peak_band_end)}
        tooltips={byHour.points.map((p) => {
          const share = totalAll > 0 ? (p.total_count / totalAll) * 100 : 0;
          return {
            title: formatHour(p.hour),
            rows: [
              { label: "Total tickets", value: formatInt(p.total_count) },
              { label: "Avg per day", value: p.avg_count.toFixed(2) },
              { label: "Share of day", value: formatPct(share) },
            ],
            note: "Derived from ticket payments, not sensors.",
          };
        })}
      />
      <FilterFootnote endpoint="occupancy_by_hour" activeFilters={activeFilterKinds(filters)} />
    </SectionCard>
  );
}
