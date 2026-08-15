import { Suspense } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { BodyGrid } from "@/components/shell/BodyGrid";
import { FilterBarServer } from "@/components/shell/FilterBarServer";
import { VisualErrorBoundary } from "@/components/primitives/VisualErrorBoundary";
import { SkeletonCard } from "@/components/primitives/Skeleton";
import { resolveFilters, type SearchParams } from "@/lib/filters";
import {
  PeakHoursKpiCard,
  TotalCountKpiCard,
  VehicleWindowKpiSection,
} from "@/components/occupancy/OccupancyKpiCards";
import { OccupancyByHourSection } from "@/components/occupancy/OccupancyByHourSection";
import { PeakVsOffPeakSection } from "@/components/occupancy/PeakVsOffPeakSection";
import { VehicleTypeDistributionSection } from "@/components/occupancy/VehicleTypeDistributionSection";
import { DailyTicketCollectionSection } from "@/components/occupancy/DailyTicketCollectionSection";
import { WeeklyOccupancyPatternSection } from "@/components/occupancy/WeeklyOccupancyPatternSection";
import styles from "./occupancy.module.css";

export default async function OccupancyPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const filters = resolveFilters(searchParams);

  return (
    <>
      <PageHeader title="Occupancy & Traffic" />
      <VehicleWindowKpiSection />
      <FilterBarServer />
      <BodyGrid layout="occupancy">
        <VisualErrorBoundary title="Occupancy by Time of Day" span={2}>
          <Suspense fallback={<SkeletonCard span={2} height={200} />}>
            <OccupancyByHourSection filters={filters} />
          </Suspense>
        </VisualErrorBoundary>

        <div className={styles.visualStack}>
          <VisualErrorBoundary title="Peak Hours Count" span={1}>
            <Suspense fallback={<SkeletonCard span={1} height={100} />}>
              <PeakHoursKpiCard filters={filters} />
            </Suspense>
          </VisualErrorBoundary>

          <VisualErrorBoundary title="Peak vs Off-Peak" span={1}>
            <Suspense fallback={<SkeletonCard span={1} height={296} />}>
              <PeakVsOffPeakSection filters={filters} />
            </Suspense>
          </VisualErrorBoundary>
        </div>

        <div className={styles.visualStack}>
          <VisualErrorBoundary title="Total Count" span={1}>
            <Suspense fallback={<SkeletonCard span={1} height={100} />}>
              <TotalCountKpiCard filters={filters} />
            </Suspense>
          </VisualErrorBoundary>

          <VisualErrorBoundary title="Vehicle Type Distribution" span={1}>
            <Suspense fallback={<SkeletonCard span={1} height={296} />}>
              <VehicleTypeDistributionSection filters={filters} />
            </Suspense>
          </VisualErrorBoundary>
        </div>

        <VisualErrorBoundary title="Daily Ticket Collection" span={2}>
          <Suspense fallback={<SkeletonCard span={2} height={200} />}>
            <DailyTicketCollectionSection filters={filters} />
          </Suspense>
        </VisualErrorBoundary>

        <VisualErrorBoundary title="Weekly Occupancy Pattern" span={2}>
          <Suspense fallback={<SkeletonCard span={2} height={200} />}>
            <WeeklyOccupancyPatternSection filters={filters} />
          </Suspense>
        </VisualErrorBoundary>
      </BodyGrid>
    </>
  );
}
