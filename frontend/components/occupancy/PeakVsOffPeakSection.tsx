import { getPeakHours } from "@/lib/api/client";
import { tryFetch } from "@/lib/tryFetch";
import type { ResolvedFilters } from "@/lib/filters";
import { formatHourBand, formatInt, formatPct } from "@/lib/format";
import { SectionCard } from "@/components/primitives/SectionCard";
import { PeakOffPeakRow } from "@/components/charts/PeakOffPeakRow";
import { ErrorCard } from "@/components/primitives/ErrorCard";
import styles from "./PeakVsOffPeakSection.module.css";

export async function PeakVsOffPeakSection({ filters }: { filters: ResolvedFilters }) {
  const { data: peak, errorMessage } = await tryFetch(() => getPeakHours(filters));
  if (!peak) {
    return <ErrorCard title="Peak vs Off-Peak" message={errorMessage!} span={1} />;
  }

  if (peak.peak_hour === null || peak.peak_band_start === null || peak.peak_band_end === null) {
    return (
      <SectionCard
        span={1}
        title="Peak vs Off-Peak"
        infoTitle="Share of ticket transactions inside the busiest contiguous hour band."
      >
        <p className={styles.empty}>No ticket data in this range.</p>
      </SectionCard>
    );
  }

  const bandRange = formatHourBand(peak.peak_band_start, peak.peak_band_end);
  const peakCount = Math.round((peak.peak_band_pct / 100) * peak.total_count);
  const offPeakCount = peak.total_count - peakCount;

  return (
    <SectionCard
      span={1}
      title="Peak vs Off-Peak"
      infoTitle="Share of ticket transactions inside the busiest contiguous hour band."
    >
      <div className={styles.rows}>
        <PeakOffPeakRow
          title="Peak hours"
          rangeText={bandRange}
          pct={peak.peak_band_pct}
          colorVar="--s1"
          tooltip={{
            title: "Peak hours",
            rows: [
              { label: "Band", value: bandRange },
              { label: "Count", value: formatInt(peakCount) },
              { label: "Share", value: formatPct(peak.peak_band_pct) },
            ],
          }}
        />
        <PeakOffPeakRow
          title="Off-peak hours"
          rangeText="Rest of day"
          pct={peak.off_peak_pct}
          colorVar="--s3"
          tooltip={{
            title: "Off-peak hours",
            rows: [
              { label: "Count", value: formatInt(offPeakCount) },
              { label: "Share", value: formatPct(peak.off_peak_pct) },
            ],
          }}
        />
      </div>
    </SectionCard>
  );
}
