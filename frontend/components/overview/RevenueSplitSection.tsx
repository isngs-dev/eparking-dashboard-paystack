import { getRevenueSplit } from "@/lib/api/client";
import { tryFetch } from "@/lib/tryFetch";
import type { ResolvedFilters } from "@/lib/filters";
import { formatCompactNaira, formatNaira, formatPct } from "@/lib/format";
import { SectionCard } from "@/components/primitives/SectionCard";
import { DonutChart } from "@/components/charts/DonutChart";
import { ErrorCard } from "@/components/primitives/ErrorCard";

export async function RevenueSplitSection({ filters }: { filters: ResolvedFilters }) {
  const { data: split, errorMessage } = await tryFetch(() => getRevenueSplit(filters));
  if (!split) {
    return <ErrorCard title="AICL / GSDS Split" message={errorMessage!} span={1} />;
  }

  const segments = [
    { key: "AICL", value: split.aicl_amount, color: "--s1" },
    { key: "GSDS", value: split.gsds_amount, color: "--s3" },
  ];

  return (
    <SectionCard
      span={1}
      title="AICL / GSDS Split"
      infoTitle="Hover a segment for the entity name, amount and share."
    >
      <DonutChart
        segments={segments}
        centerValue={formatCompactNaira(split.total_collection)}
        centerLabel="TOTAL"
        tooltips={{
          AICL: {
            title: "AICL",
            rows: [
              { label: "Amount", value: formatNaira(split.aicl_amount) },
              {
                label: "Share",
                value: split.aicl_pct !== null ? formatPct(split.aicl_pct * 100) : "—",
              },
            ],
          },
          GSDS: {
            title: "GSDS",
            rows: [
              { label: "Amount", value: formatNaira(split.gsds_amount) },
              {
                label: "Share",
                value: split.gsds_pct !== null ? formatPct(split.gsds_pct * 100) : "—",
              },
            ],
          },
        }}
      />
    </SectionCard>
  );
}
