import { getOverviewSummary, getTotalCollection } from "@/lib/api/client";
import { BackendFetchError } from "@/lib/api/backendFetch";
import { activeFilterKinds, type ResolvedFilters } from "@/lib/filters";
import type { EndpointKey, FilterKind } from "@/lib/api/endpointFilters";
import { ignoredFiltersFootnote } from "@/lib/api/endpointFilters";
import { formatNaira, formatInt, formatShortDate } from "@/lib/format";
import { KpiCard } from "@/components/kpi/KpiCard";
import { ErrorCard } from "@/components/primitives/ErrorCard";
import type { KPIWindow, TotalCollectionResponse } from "@/lib/api/types";

function windowCard(label: string, w: KPIWindow, endpointKey: EndpointKey, active: FilterKind[]) {
  return (
    <KpiCard
      key={label}
      label={label}
      value={formatNaira(w.total_collection)}
      sublabel={w.date_range.label}
      deltaPct={w.delta_pct}
      footnote={ignoredFiltersFootnote(endpointKey, active)}
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

export async function RevenueKpiCards({ filters }: { filters: ResolvedFilters }) {
  let summary, total;
  try {
    [summary, total] = await Promise.all([getOverviewSummary(), getTotalCollection(filters)]);
  } catch (err) {
    const message = err instanceof BackendFetchError ? err.detail : "Failed to load revenue KPIs.";
    return <ErrorCard title="Daily/Weekly/Monthly/Total Collection" message={message} span={4} />;
  }
  const active = activeFilterKinds(filters);

  return (
    <>
      {windowCard("Today's Revenue", summary.daily, "overview_summary", active)}
      {windowCard("Weekly Revenue", summary.weekly, "overview_summary", active)}
      {windowCard("Monthly Revenue", summary.monthly, "overview_summary", active)}
      <TotalCollectionCard total={total} active={active} />
    </>
  );
}

function TotalCollectionCard({
  total,
  active,
}: {
  total: TotalCollectionResponse;
  active: FilterKind[];
}) {
  return (
    <KpiCard
      label="Total Collection"
      value={formatNaira(total.total_collection)}
      sublabel={total.date_range.label}
      deltaPct={total.delta_pct}
      footnote={ignoredFiltersFootnote("revenue_total_collection", active)}
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
