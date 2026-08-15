import { Suspense } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { BodyGrid } from "@/components/shell/BodyGrid";
import { FilterBarServer } from "@/components/shell/FilterBarServer";
import { VisualErrorBoundary } from "@/components/primitives/VisualErrorBoundary";
import { SkeletonCard } from "@/components/primitives/Skeleton";
import { resolveFilters, type SearchParams } from "@/lib/filters";
import {
  RevenueWindowKpiSection,
  TotalCollectionKpiCard,
} from "@/components/overview/RevenueKpiCards";
import { RevenueTrendSection } from "@/components/overview/RevenueTrendSection";
import { RevenueSplitSection } from "@/components/overview/RevenueSplitSection";
import { CardSalesSection } from "@/components/overview/CardSalesSection";
import { TotalCardSaleCard } from "@/components/overview/TotalCardSaleCard";
import styles from "./overview.module.css";

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const filters = resolveFilters(searchParams);

  return (
    <>
      <PageHeader title="Overview · Revenue" />
      <RevenueWindowKpiSection />
      <FilterBarServer />
      <BodyGrid layout="overview">
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

        <div className={styles.summaryStack}>
          <VisualErrorBoundary title="Total Collection" span={1}>
            <Suspense fallback={<SkeletonCard span={1} height={100} />}>
              <TotalCollectionKpiCard filters={filters} />
            </Suspense>
          </VisualErrorBoundary>

          <VisualErrorBoundary title="Total Card Sale" span={1}>
            <Suspense fallback={<SkeletonCard span={1} height={186} />}>
              <TotalCardSaleCard filters={filters} />
            </Suspense>
          </VisualErrorBoundary>
        </div>
      </BodyGrid>
    </>
  );
}
