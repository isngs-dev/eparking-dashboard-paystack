import { getEntryCount, getPeakHours, getTrafficToday } from "@/lib/api/client";
import { tryFetch } from "@/lib/tryFetch";
import { activeFilterKinds, type ResolvedFilters } from "@/lib/filters";
import { ignoredFiltersFootnote } from "@/lib/api/endpointFilters";
import { formatHourBand, formatInt } from "@/lib/format";
import { KpiCard } from "@/components/kpi/KpiCard";
import { ErrorCard } from "@/components/primitives/ErrorCard";

function basisText(basis: string): string {
  return basis === "all_transactions"
    ? "Derived from all successful revenue transactions — not gate-sensor data."
    : "Derived from successful ticket transactions — not gate-sensor data.";
}

export async function OccupancyKpiCards({ filters }: { filters: ResolvedFilters }) {
  const [entryRes, todayRes, peakRes] = await Promise.all([
    tryFetch(() => getEntryCount(filters)),
    tryFetch(() => getTrafficToday()),
    tryFetch(() => getPeakHours(filters)),
  ]);

  if (!entryRes.data || !todayRes.data || !peakRes.data) {
    const message =
      entryRes.errorMessage ?? todayRes.errorMessage ?? peakRes.errorMessage ?? "Failed to load.";
    return (
      <ErrorCard title="Entry Count / Total Vehicles / Peak Hours" message={message} span={3} />
    );
  }

  const entry = entryRes.data;
  const today = todayRes.data;
  const peak = peakRes.data;
  const active = activeFilterKinds(filters);

  const peakSublabel =
    peak.peak_hour === null || peak.peak_band_start === null || peak.peak_band_end === null
      ? "No data in this range"
      : `Inside the ${formatHourBand(peak.peak_band_start, peak.peak_band_end)} band`;

  return (
    <>
      <KpiCard
        label="Entry Count"
        value={formatInt(entry.entry_count)}
        sublabel="Ticket transactions in range"
        infoTitle={basisText(entry.entry_count_basis)}
        footnote={ignoredFiltersFootnote("occupancy_entry_count", active)}
        tooltip={{
          title: "Entry Count",
          rows: [
            { label: "Count", value: formatInt(entry.entry_count) },
            { label: "Basis", value: entry.entry_count_basis },
          ],
        }}
      />
      <KpiCard
        label="Total Vehicles Today"
        value={formatInt(today.vehicle_count)}
        sublabel="Today only — not affected by filters"
        infoTitle={basisText(today.entry_count_basis)}
        tooltip={{
          title: "Total Vehicles Today",
          rows: [
            { label: "Date", value: today.date },
            { label: "Count", value: formatInt(today.vehicle_count) },
            { label: "Basis", value: today.entry_count_basis },
          ],
        }}
      />
      <KpiCard
        label="Peak Hours Count"
        value={peak.peak_hour === null ? "—" : formatInt(peak.peak_hour_count)}
        sublabel={peakSublabel}
        infoTitle={basisText(peak.entry_count_basis)}
        footnote={ignoredFiltersFootnote("occupancy_peak_hours", active)}
        tooltip={{
          title: "Peak Hours Count",
          rows:
            peak.peak_hour === null
              ? [{ label: "Status", value: "No data in this range" }]
              : [
                  { label: "Peak hour", value: `${peak.peak_hour}:00` },
                  { label: "Count", value: formatInt(peak.peak_hour_count) },
                  {
                    label: "Band",
                    value: formatHourBand(peak.peak_band_start!, peak.peak_band_end!),
                  },
                ],
        }}
      />
    </>
  );
}
