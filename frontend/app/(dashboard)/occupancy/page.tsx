import { Suspense } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { BodyGrid } from "@/components/shell/BodyGrid";
import { FilterBarServer } from "@/components/shell/FilterBarServer";
import { VisualErrorBoundary } from "@/components/primitives/VisualErrorBoundary";
import { SkeletonCard } from "@/components/primitives/Skeleton";
import { resolveFilters, type SearchParams } from "@/lib/filters";
import { OccupancyKpiCards } from "@/components/occupancy/OccupancyKpiCards";
import { InfoCalloutSection } from "@/components/occupancy/InfoCalloutSection";
import { OccupancyByHourSection } from "@/components/occupancy/OccupancyByHourSection";
import { PeakVsOffPeakSection } from "@/components/occupancy/PeakVsOffPeakSection";
import { VehicleTypeDistributionSection } from "@/components/occupancy/VehicleTypeDistributionSection";
import { DailyTicketCollectionSection } from "@/components/occupancy/DailyTicketCollectionSection";
import { WeeklyOccupancyPatternSection } from "@/components/occupancy/WeeklyOccupancyPatternSection";

export default async function OccupancyPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const filters = resolveFilters(searchParams);

  return (
    <>
      <PageHeader title="Occupancy & Traffic" tag="Usage & volume" />
      <FilterBarServer />
      <BodyGrid>
        <VisualErrorBoundary title="Entry Count / Total Vehicles / Peak Hours" span={3}>
          <Suspense
            fallback={
              <>
                <SkeletonCard span={1} height={60} />
                <SkeletonCard span={1} height={60} />
                <SkeletonCard span={1} height={60} />
              </>
            }
          >
            <OccupancyKpiCards filters={filters} />
          </Suspense>
        </VisualErrorBoundary>

        <VisualErrorBoundary title="Derived from ticket payments" span={1}>
          <Suspense fallback={<SkeletonCard span={1} height={60} />}>
            <InfoCalloutSection filters={filters} />
          </Suspense>
        </VisualErrorBoundary>

        <VisualErrorBoundary title="Occupancy by Time of Day" span={2}>
          <Suspense fallback={<SkeletonCard span={2} height={200} />}>
            <OccupancyByHourSection filters={filters} />
          </Suspense>
        </VisualErrorBoundary>

        <VisualErrorBoundary title="Peak vs Off-Peak" span={1}>
          <Suspense fallback={<SkeletonCard span={1} height={200} />}>
            <PeakVsOffPeakSection filters={filters} />
          </Suspense>
        </VisualErrorBoundary>

        <VisualErrorBoundary title="Vehicle Type Distribution" span={1}>
          <Suspense fallback={<SkeletonCard span={1} height={200} />}>
            <VehicleTypeDistributionSection filters={filters} />
          </Suspense>
        </VisualErrorBoundary>

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
