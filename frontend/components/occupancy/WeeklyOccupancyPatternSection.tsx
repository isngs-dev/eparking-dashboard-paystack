import { getWeeklyPattern } from "@/lib/api/client";
import { tryFetch } from "@/lib/tryFetch";
import { activeFilterKinds, type ResolvedFilters } from "@/lib/filters";
import { dayOfWeekLabel, formatInt, formatPct } from "@/lib/format";
import { SectionCard } from "@/components/primitives/SectionCard";
import { HBarRowList, type HBarRow } from "@/components/charts/HBarRowList";
import { FilterFootnote } from "@/components/primitives/FilterFootnote";
import { ErrorCard } from "@/components/primitives/ErrorCard";

export async function WeeklyOccupancyPatternSection({ filters }: { filters: ResolvedFilters }) {
  const { data: res, errorMessage } = await tryFetch(() => getWeeklyPattern(filters));
  if (!res) {
    return <ErrorCard title="Weekly Occupancy Pattern" message={errorMessage!} span={2} />;
  }

  const byDay = new Map<number, number>();
  for (const p of res.points) byDay.set(p.day_of_week, p.entry_count);

  const total = res.points.reduce((s, p) => s + p.entry_count, 0);
  const maxCount = Math.max(...Array.from(byDay.values()), 1);

  const rows: HBarRow[] = Array.from({ length: 7 }, (_, i) => i + 1).map((dow) => {
    const count = byDay.get(dow) ?? 0;
    const share = total > 0 ? (count / total) * 100 : 0;
    return {
      key: String(dow),
      label: dayOfWeekLabel(dow),
      pct: (count / maxCount) * 100,
      colorVar: "--s1",
      rightText: formatInt(count),
      tooltip: {
        title: dayOfWeekLabel(dow),
        rows: [
          { label: "Tickets", value: formatInt(count) },
          { label: "Share of week", value: formatPct(share) },
        ],
        note: "Derived from ticket payments.",
      },
    };
  });

  const sundayEntry = byDay.get(7) ?? 0;
  const showSundayNote = total > 0 && sundayEntry === 0;

  return (
    <SectionCard
      span={2}
      title="Weekly Occupancy Pattern"
      infoTitle="Ticket transactions grouped by day of week over the selected range."
      headerRight={
        showSundayNote ? (
          <span style={{ marginLeft: "auto", fontSize: 10.5, color: "var(--mu)" }}>
            Sunday closure detected in this range
          </span>
        ) : undefined
      }
    >
      <HBarRowList rows={rows} />
      <FilterFootnote endpoint="occupancy_weekly_pattern" activeFilters={activeFilterKinds(filters)} />
    </SectionCard>
  );
}
