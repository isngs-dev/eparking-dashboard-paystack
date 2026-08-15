import { Suspense } from "react";
import {
  getEntryCount,
  getPeakHours,
  getTrafficSummary,
} from "@/lib/api/client";
import { tryFetch } from "@/lib/tryFetch";
import type { ResolvedFilters } from "@/lib/filters";
import type { VehicleKPIWindow } from "@/lib/api/types";
import { formatHourBand, formatInt, formatShortDate } from "@/lib/format";
import { KpiCard } from "@/components/kpi/KpiCard";
import { ErrorCard } from "@/components/primitives/ErrorCard";
import { SkeletonCard } from "@/components/primitives/Skeleton";
import { VisualErrorBoundary } from "@/components/primitives/VisualErrorBoundary";
import styles from "./OccupancyKpiCards.module.css";

function basisText(basis: string): string {
  return basis === "all_transactions"
    ? "Derived from all successful revenue transactions — not gate-sensor data."
    : "Derived from successful ticket transactions — not gate-sensor data.";
}

function vehicleWindowCard(label: string, window: VehicleKPIWindow) {
  return (
    <KpiCard
      key={label}
      label={label}
      value={formatInt(window.vehicle_count)}
      sublabel={window.date_range.label}
      infoTitle={basisText(window.entry_count_basis)}
      tooltip={{
        title: label,
        rows: [
          {
            label: "Date range",
            value: `${formatShortDate(window.date_range.date_from)} – ${formatShortDate(window.date_range.date_to)}`,
          },
          { label: "Vehicles", value: formatInt(window.vehicle_count) },
          { label: "Basis", value: window.entry_count_basis },
        ],
      }}
    />
  );
}

async function VehicleWindowKpiCards() {
  const { data: summary, errorMessage } = await tryFetch(() => getTrafficSummary());
  if (!summary) {
    return <ErrorCard title="Vehicle totals" message={errorMessage!} span={4} />;
  }

  return (
    <>
      {vehicleWindowCard("Total Vehicles Today", summary.daily)}
      {vehicleWindowCard("Weekly Vehicles", summary.weekly)}
      {vehicleWindowCard("Monthly Vehicles", summary.monthly)}
      {vehicleWindowCard("Yearly Vehicles", summary.yearly)}
    </>
  );
}

export function VehicleWindowKpiSection() {
  return (
    <div className={styles.fixedGrid}>
      <VisualErrorBoundary title="Vehicle totals" span={4}>
        <Suspense
          fallback={
            <>
              <SkeletonCard span={1} height={60} />
              <SkeletonCard span={1} height={60} />
              <SkeletonCard span={1} height={60} />
              <SkeletonCard span={1} height={60} />
            </>
          }
        >
          <VehicleWindowKpiCards />
        </Suspense>
      </VisualErrorBoundary>
    </div>
  );
}

export async function TotalCountKpiCard({ filters }: { filters: ResolvedFilters }) {
  const { data: entry, errorMessage } = await tryFetch(() => getEntryCount(filters));
  if (!entry) {
    return <ErrorCard title="Total Count" message={errorMessage!} />;
  }

  return (
    <KpiCard
      label="Total Count"
      value={formatInt(entry.entry_count)}
      sublabel="Total Entries in range"
      infoTitle={basisText(entry.entry_count_basis)}
      tooltip={{
        title: "Total Count",
        rows: [
          { label: "Count", value: formatInt(entry.entry_count) },
          { label: "Basis", value: entry.entry_count_basis },
        ],
      }}
    />
  );
}

export async function PeakHoursKpiCard({ filters }: { filters: ResolvedFilters }) {
  const { data: peak, errorMessage } = await tryFetch(() => getPeakHours(filters));
  if (!peak) {
    return <ErrorCard title="Peak Hours Count" message={errorMessage!} />;
  }

  const sublabel =
    peak.peak_hour === null || peak.peak_band_start === null || peak.peak_band_end === null
      ? "No data in this range"
      : `Inside the ${formatHourBand(peak.peak_band_start, peak.peak_band_end)} band`;

  return (
    <KpiCard
      label="Peak Hours Count"
      value={peak.peak_hour === null ? "—" : formatInt(peak.peak_hour_count)}
      sublabel={sublabel}
      infoTitle={basisText(peak.entry_count_basis)}
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
  );
}
