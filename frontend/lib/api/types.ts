/**
 * Hand-mirrored from `services/api/app/models/responses.py`.
 * Keep in sync manually -- there is no shared codegen between the two
 * layers (Python/Pydantic on the API, TypeScript here). If a field name
 * or shape here looks wrong, check the source file first, not this one.
 */

export interface DateRange {
  date_from: string; // ISO date
  date_to: string; // ISO date
  label: string;
}

export interface KPIWindow {
  label: string;
  date_range: DateRange;
  total_collection: number;
  ticket_amount: number;
  card_total_amount: number;
  transaction_count_total: number;
  ticket_count: number;
  prior_period_total_collection: number;
  delta_pct: number | null;
}

export interface OverviewSummaryResponse {
  daily: KPIWindow;
  weekly: KPIWindow;
  monthly: KPIWindow;
  yearly: KPIWindow;
}

export interface RevenueTrendPoint {
  date: string;
  ticket_amount: number;
  card_total_amount: number;
  total_collection: number;
  transaction_count_total: number;
}

export interface RevenueTrendResponse {
  date_range: DateRange;
  points: RevenueTrendPoint[];
}

export interface VehicleTypeDistributionItem {
  vehicle_type: string;
  txn_count: number;
  total_amount: number;
}

export interface VehicleTypeDistributionResponse {
  window: string;
  date_range: DateRange;
  items: VehicleTypeDistributionItem[];
}

export interface CardBreakdownDayPoint {
  date: string;
  annual_count: number;
  annual_amount: number;
  monthly_count: number;
  monthly_amount: number;
}

export interface CardBreakdownResponse {
  date_range: DateRange;
  points: CardBreakdownDayPoint[];
}

export interface CardTotalResponse {
  date_range: DateRange;
  card_total_amount: number;
  annual_amount: number;
  monthly_amount: number;
  annual_count: number;
  monthly_count: number;
}

export interface TicketTierDayPoint {
  date: string;
  vehicle_type: string;
  ticket_count: number;
  ticket_amount: number;
}

export interface TicketDailyByTierResponse {
  date_range: DateRange;
  points: TicketTierDayPoint[];
}

export interface TotalCollectionResponse {
  date_range: DateRange;
  total_collection: number;
  ticket_amount: number;
  card_total_amount: number;
  prior_period_total_collection: number;
  delta_pct: number | null;
}

export interface RevenueSplitResponse {
  date_range: DateRange;
  aicl_amount: number;
  gsds_amount: number;
  // NOTE: fractions (e.g. 0.3), not percentages -- multiply by 100 to display.
  aicl_pct: number | null;
  gsds_pct: number | null;
  total_collection: number;
}

export interface EntryCountResponse {
  date_range: DateRange;
  entry_count: number;
  entry_count_basis: string;
}

export interface HourlyHistogramPoint {
  hour: number;
  total_count: number;
  avg_count: number;
}

export interface OccupancyByHourResponse {
  date_range: DateRange;
  entry_count_basis: string;
  points: HourlyHistogramPoint[];
}

export interface PeakHoursResponse {
  date_range: DateRange;
  entry_count_basis: string;
  peak_hour: number | null;
  peak_hour_count: number;
  peak_band_start: number | null;
  peak_band_end: number | null;
  peak_band_pct: number;
  off_peak_pct: number;
  total_count: number;
}

export interface WeeklyPatternPoint {
  day_of_week: number; // 1-7, ISODOW, Mon=1..Sun=7
  entry_count: number;
}

export interface WeeklyPatternResponse {
  date_range: DateRange;
  entry_count_basis: string;
  points: WeeklyPatternPoint[];
}

export interface TrafficTodayResponse {
  date: string;
  vehicle_count: number;
  entry_count_basis: string;
}

export interface VehicleKPIWindow {
  label: string;
  date_range: DateRange;
  vehicle_count: number;
  entry_count_basis: string;
}

export interface TrafficSummaryResponse {
  daily: VehicleKPIWindow;
  weekly: VehicleKPIWindow;
  monthly: VehicleKPIWindow;
  yearly: VehicleKPIWindow;
}

export interface VehicleTypesFilterResponse {
  vehicle_types: string[];
}

/** Shared query-param shape sent to every filterable endpoint. */
export interface CommonFilterParams {
  from?: string;
  to?: string;
  vehicle_types?: string;
  days?: string;
}
