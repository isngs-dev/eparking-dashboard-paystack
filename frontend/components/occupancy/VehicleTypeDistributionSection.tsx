import { getVehicleTypeDistribution } from "@/lib/api/client";
import { tryFetch } from "@/lib/tryFetch";
import type { ResolvedFilters } from "@/lib/filters";
import { formatInt, formatNaira, formatPct } from "@/lib/format";
import { vehicleTypeColorVar, VEHICLE_TYPE_PRICE } from "@/lib/seriesColors";
import { SectionCard } from "@/components/primitives/SectionCard";
import { DonutChart } from "@/components/charts/DonutChart";
import { ErrorCard } from "@/components/primitives/ErrorCard";
import type { TooltipContent } from "@/components/primitives/Tooltip";

export async function VehicleTypeDistributionSection({ filters }: { filters: ResolvedFilters }) {
  const { data: dist, errorMessage } = await tryFetch(() =>
    getVehicleTypeDistribution(filters, "range"),
  );
  if (!dist) {
    return <ErrorCard title="Vehicle Type Distribution" message={errorMessage!} span={1} />;
  }
  const totalCount = dist.items.reduce((s, i) => s + i.txn_count, 0);

  const segments = dist.items.map((item) => ({
    key: item.vehicle_type,
    value: item.txn_count,
    color: vehicleTypeColorVar(item.vehicle_type),
  }));

  return (
    <SectionCard
      span={1}
      title="Vehicle Type Distribution"
      infoTitle="Vehicle type is inferred from the ticket fee tier paid, not from a camera. Hover a segment for detail."
    >
      <DonutChart
        segments={segments}
        centerValue={formatInt(totalCount)}
        centerLabel="TICKETS"
        tooltips={dist.items.reduce<Record<string, TooltipContent>>((acc, item) => {
          const share = totalCount > 0 ? (item.txn_count / totalCount) * 100 : 0;
          acc[item.vehicle_type] = {
            title: item.vehicle_type,
            rows: [
              { label: "Tickets", value: formatInt(item.txn_count) },
              { label: "Share", value: formatPct(share) },
              {
                label: "Fee tier",
                value:
                  VEHICLE_TYPE_PRICE[item.vehicle_type] !== undefined
                    ? formatNaira(VEHICLE_TYPE_PRICE[item.vehicle_type])
                    : "—",
              },
            ],
            note: "Type inferred from fee tier paid.",
          };
          return acc;
        }, {})}
      />
    </SectionCard>
  );
}
