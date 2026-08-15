import { Suspense } from "react";
import { getOverviewSummary, getTotalCollection } from "@/lib/api/client";
import { BackendFetchError } from "@/lib/api/backendFetch";
import type { ResolvedFilters } from "@/lib/filters";
import { formatNaira, formatInt, formatShortDate } from "@/lib/format";
import { KpiCard } from "@/components/kpi/KpiCard";
import { ErrorCard } from "@/components/primitives/ErrorCard";
import { SkeletonCard } from "@/components/primitives/Skeleton";
import { VisualErrorBoundary } from "@/components/primitives/VisualErrorBoundary";
import type { KPIWindow, TotalCollectionResponse } from "@/lib/api/types";
import styles from "./RevenueKpiCards.module.css";

function windowCard(label: string, w: KPIWindow) {
  return (
    <KpiCard
      key={label}
      label={label}
      value={formatNaira(w.total_collection)}
      sublabel={w.date_range.label}
      tooltip={{
        title: label,
        rows: [
          {
            label: "Date range",
            value: `${formatShortDate(w.date_range.date_from)} – ${formatShortDate(w.date_range.date_to)}`,
          },
          { label: "Ticket amount", value: formatNaira(w.ticket_amount) },
          { label: "Card total", value: formatNaira(w.card_total_amount) },
          { label: "Transactions", value: formatInt(w.transaction_count_total) },
          { label: "Tickets", value: formatInt(w.ticket_count) },
        ],
      }}
    />
  );
}

async function RevenueWindowKpiCards() {
  let summary;
  try {
    summary = await getOverviewSummary();
  } catch (err) {
    const message =
      err instanceof BackendFetchError
        ? err.detail
        : "Failed to load revenue KPIs.";
    return (
      <ErrorCard
        title="Daily/Weekly/Monthly/Yearly Revenue"
        message={message}
        span={4}
      />
    );
  }

  return (
    <>
      {windowCard("Today's Revenue", summary.daily)}
      {windowCard("Weekly Revenue", summary.weekly)}
      {windowCard("Monthly Revenue", summary.monthly)}
      {windowCard("Yearly Revenue", summary.yearly)}
    </>
  );
}

export function RevenueWindowKpiSection() {
  return (
    <div className={styles.fixedGrid}>
      <VisualErrorBoundary
        title="Daily/Weekly/Monthly/Yearly Revenue"
        span={4}
      >
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
          <RevenueWindowKpiCards />
        </Suspense>
      </VisualErrorBoundary>
    </div>
  );
}

export async function TotalCollectionKpiCard({
  filters,
}: {
  filters: ResolvedFilters;
}) {
  let total: TotalCollectionResponse;
  try {
    total = await getTotalCollection(filters);
  } catch (err) {
    const message =
      err instanceof BackendFetchError
        ? err.detail
        : "Failed to load total collection.";
    return <ErrorCard title="Total Collection" message={message} />;
  }

  return (
    <KpiCard
      label="Total Collection"
      value={formatNaira(total.total_collection)}
      sublabel={total.date_range.label}
      tooltip={{
        title: "Total Collection",
        rows: [
          { label: "Ticket amount", value: formatNaira(total.ticket_amount) },
          { label: "Card total", value: formatNaira(total.card_total_amount) },
          {
            label: "Prior period",
            value: formatNaira(total.prior_period_total_collection),
          },
        ],
      }}
    />
  );
}
