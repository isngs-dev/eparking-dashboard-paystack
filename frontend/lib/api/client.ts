/**
 * Typed wrapper functions, one per endpoint, each building its request
 * params from `ENDPOINT_FILTERS` so an endpoint that ignores a filter never
 * has that param sent (keeps server-side cache keys clean and matches the
 * documented backend behavior exactly).
 */

import { backendFetch } from "./backendFetch";
import { ENDPOINT_FILTERS, EndpointKey, FilterKind } from "./endpointFilters";
import type {
  CardBreakdownResponse,
  CardTotalResponse,
  EntryCountResponse,
  OccupancyByHourResponse,
  OverviewSummaryResponse,
  PeakHoursResponse,
  RevenueSplitResponse,
  RevenueTrendResponse,
  TicketDailyByTierResponse,
  TotalCollectionResponse,
  TrafficTodayResponse,
  VehicleTypeDistributionResponse,
  VehicleTypesFilterResponse,
  WeeklyPatternResponse,
} from "./types";
import type { ResolvedFilters } from "../filters";

function buildParams(
  key: EndpointKey,
  filters: ResolvedFilters,
): Record<string, string | undefined> {
  const honored = new Set<FilterKind>(ENDPOINT_FILTERS[key]);
  const params: Record<string, string | undefined> = {};
  if (honored.has("date")) {
    params.from = filters.from;
    params.to = filters.to;
  }
  if (honored.has("vehicle_types")) {
    params.vehicle_types = filters.vehicle_types;
  }
  if (honored.has("days")) {
    params.days = filters.days;
  }
  return params;
}

export function getOverviewSummary(): Promise<OverviewSummaryResponse> {
  return backendFetch<OverviewSummaryResponse>("/api/overview/summary");
}

export function getRevenueTrend(filters: ResolvedFilters): Promise<RevenueTrendResponse> {
  return backendFetch<RevenueTrendResponse>("/api/overview/revenue-trend", {
    params: buildParams("revenue_trend", filters),
  });
}

export function getVehicleTypeDistribution(
  filters: ResolvedFilters,
  window: "range" | "today" = "range",
): Promise<VehicleTypeDistributionResponse> {
  return backendFetch<VehicleTypeDistributionResponse>("/api/vehicle-types/distribution", {
    params: { ...buildParams("vehicle_type_distribution", filters), window },
  });
}

export function getCardsBreakdown(filters: ResolvedFilters): Promise<CardBreakdownResponse> {
  return backendFetch<CardBreakdownResponse>("/api/cards/breakdown", {
    params: buildParams("cards_breakdown", filters),
  });
}

export function getCardsTotal(filters: ResolvedFilters): Promise<CardTotalResponse> {
  return backendFetch<CardTotalResponse>("/api/cards/total", {
    params: buildParams("cards_total", filters),
  });
}

export function getTicketsDailyByTier(
  filters: ResolvedFilters,
): Promise<TicketDailyByTierResponse> {
  return backendFetch<TicketDailyByTierResponse>("/api/tickets/daily-by-tier", {
    params: buildParams("tickets_daily_by_tier", filters),
  });
}

export function getTotalCollection(filters: ResolvedFilters): Promise<TotalCollectionResponse> {
  return backendFetch<TotalCollectionResponse>("/api/revenue/total-collection", {
    params: buildParams("revenue_total_collection", filters),
  });
}

export function getRevenueSplit(filters: ResolvedFilters): Promise<RevenueSplitResponse> {
  return backendFetch<RevenueSplitResponse>("/api/revenue/split", {
    params: buildParams("revenue_split", filters),
  });
}

export function getEntryCount(filters: ResolvedFilters): Promise<EntryCountResponse> {
  return backendFetch<EntryCountResponse>("/api/occupancy/entry-count", {
    params: buildParams("occupancy_entry_count", filters),
  });
}

export function getOccupancyByHour(filters: ResolvedFilters): Promise<OccupancyByHourResponse> {
  return backendFetch<OccupancyByHourResponse>("/api/occupancy/by-hour", {
    params: buildParams("occupancy_by_hour", filters),
  });
}

export function getPeakHours(filters: ResolvedFilters): Promise<PeakHoursResponse> {
  return backendFetch<PeakHoursResponse>("/api/occupancy/peak-hours", {
    params: buildParams("occupancy_peak_hours", filters),
  });
}

export function getWeeklyPattern(filters: ResolvedFilters): Promise<WeeklyPatternResponse> {
  return backendFetch<WeeklyPatternResponse>("/api/occupancy/weekly-pattern", {
    params: buildParams("occupancy_weekly_pattern", filters),
  });
}

export function getTrafficToday(): Promise<TrafficTodayResponse> {
  return backendFetch<TrafficTodayResponse>("/api/traffic/today");
}

export function getVehicleTypesFilter(): Promise<VehicleTypesFilterResponse> {
  return backendFetch<VehicleTypesFilterResponse>("/api/filters/vehicle-types", {
    revalidate: 300,
  });
}
