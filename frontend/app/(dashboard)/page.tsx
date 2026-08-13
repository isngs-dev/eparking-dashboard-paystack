import { Suspense } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { BodyGrid } from "@/components/shell/BodyGrid";
import { FilterBarServer } from "@/components/shell/FilterBarServer";
import { VisualErrorBoundary } from "@/components/primitives/VisualErrorBoundary";
import { SkeletonCard } from "@/components/primitives/Skeleton";
import { resolveFilters, type SearchParams } from "@/lib/filters";
import { RevenueKpiCards } from "@/components/overview/RevenueKpiCards";
import { RevenueTrendSection } from "@/components/overview/RevenueTrendSection";
import { RevenueSplitSection } from "@/components/overview/RevenueSplitSection";
import { CardSalesSection } from "@/components/overview/CardSalesSection";
import { TotalCardSaleCard } from "@/components/overview/TotalCardSaleCard";

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const filters = resolveFilters(searchParams);

  return (
    <>
      <PageHeader title="Overview · Revenue" />
      <FilterBarServer />
      <BodyGrid>
        <VisualErrorBoundary title="Daily/Weekly/Monthly/Total Collection" span={4}>
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
            <RevenueKpiCards filters={filters} />
          </Suspense>
        </VisualErrorBoundary>

        <VisualErrorBoundary title="Revenue Trend" span={3}>
          <Suspense fallback={<SkeletonCard span={3} height={200} />}>
            <RevenueTrendSection filters={filters} />
          </Suspense>
        </VisualErrorBoundary>

        <VisualErrorBoundary title="AICL / GSDS Split" span={1}>
          <Suspense fallback={<SkeletonCard span={1} height={200} />}>
            <RevenueSplitSection filters={filters} />
          </Suspense>
        </VisualErrorBoundary>

        <VisualErrorBoundary title="Card Sales" span={3}>
          <Suspense fallback={<SkeletonCard span={3} height={200} />}>
            <CardSalesSection filters={filters} />
          </Suspense>
        </VisualErrorBoundary>

        <VisualErrorBoundary title="Total Card Sale" span={1}>
          <Suspense fallback={<SkeletonCard span={1} height={200} />}>
            <TotalCardSaleCard filters={filters} />
          </Suspense>
        </VisualErrorBoundary>
      </BodyGrid>
    </>
  );
}
