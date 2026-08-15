"""Pydantic response models for the dashboard API.

Every endpoint response is defined here so the API contract lives in code,
not documentation (per `references/knowledge-base/03_API_SERVICES.md`).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class DateRange(BaseModel):
    date_from: date
    date_to: date
    label: str


class KPIWindow(BaseModel):
    """One KPI figure with its own explicit, labeled date range -- fixes the
    old dashboard's Daily > Monthly inconsistency bug (see api-layer skill).
    """

    label: str
    date_range: DateRange
    total_collection: float
    ticket_amount: float
    card_total_amount: float
    transaction_count_total: int
    ticket_count: int
    prior_period_total_collection: float
    delta_pct: float | None


class OverviewSummaryResponse(BaseModel):
    daily: KPIWindow
    weekly: KPIWindow
    monthly: KPIWindow
    yearly: KPIWindow


class RevenueTrendPoint(BaseModel):
    date: date
    ticket_amount: float
    card_total_amount: float
    total_collection: float
    transaction_count_total: int


class RevenueTrendResponse(BaseModel):
    date_range: DateRange
    points: list[RevenueTrendPoint]


class VehicleTypeDistributionItem(BaseModel):
    vehicle_type: str
    txn_count: int
    total_amount: float


class VehicleTypeDistributionResponse(BaseModel):
    window: str
    date_range: DateRange
    items: list[VehicleTypeDistributionItem]


class CardBreakdownDayPoint(BaseModel):
    date: date
    annual_count: int
    annual_amount: float
    monthly_count: int
    monthly_amount: float


class CardBreakdownResponse(BaseModel):
    date_range: DateRange
    points: list[CardBreakdownDayPoint]


class CardTotalResponse(BaseModel):
    date_range: DateRange
    card_total_amount: float
    annual_amount: float
    monthly_amount: float
    annual_count: int
    monthly_count: int


class TicketTierDayPoint(BaseModel):
    date: date
    vehicle_type: str
    ticket_count: int
    ticket_amount: float


class TicketDailyByTierResponse(BaseModel):
    date_range: DateRange
    points: list[TicketTierDayPoint]


class TotalCollectionResponse(BaseModel):
    date_range: DateRange
    total_collection: float
    ticket_amount: float
    card_total_amount: float
    prior_period_total_collection: float
    delta_pct: float | None


class RevenueSplitResponse(BaseModel):
    date_range: DateRange
    aicl_amount: float
    gsds_amount: float
    aicl_pct: float | None
    gsds_pct: float | None
    total_collection: float


class EntryCountResponse(BaseModel):
    date_range: DateRange
    entry_count: int
    entry_count_basis: str


class HourlyHistogramPoint(BaseModel):
    hour: int
    total_count: int
    avg_count: float


class OccupancyByHourResponse(BaseModel):
    date_range: DateRange
    entry_count_basis: str
    points: list[HourlyHistogramPoint]


class PeakHoursResponse(BaseModel):
    date_range: DateRange
    entry_count_basis: str
    peak_hour: int | None
    peak_hour_count: int
    peak_band_start: int | None
    peak_band_end: int | None
    peak_band_pct: float
    off_peak_pct: float
    total_count: int


class WeeklyPatternPoint(BaseModel):
    day_of_week: int
    entry_count: int


class WeeklyPatternResponse(BaseModel):
    date_range: DateRange
    entry_count_basis: str
    points: list[WeeklyPatternPoint]


class TrafficTodayResponse(BaseModel):
    date: date
    vehicle_count: int
    entry_count_basis: str


class VehicleKPIWindow(BaseModel):
    label: str
    date_range: DateRange
    vehicle_count: int
    entry_count_basis: str


class TrafficSummaryResponse(BaseModel):
    daily: VehicleKPIWindow
    weekly: VehicleKPIWindow
    monthly: VehicleKPIWindow
    yearly: VehicleKPIWindow


class VehicleTypesFilterResponse(BaseModel):
    vehicle_types: list[str]


# --------------------------------------------------------------------------
# Sprint 7: admin fee-categories / revenue-split / reclassify / ops
# --------------------------------------------------------------------------


class FeeCategoryComponent(BaseModel):
    code: str
    amount: float
    count: int


class FeeCategoryBase(BaseModel):
    code: str
    revenue_stream: str
    label: str
    vehicle_type: str | None = None
    amount_min: float
    amount_max: float
    counts_as_entry: bool
    is_revenue: bool
    components: list[FeeCategoryComponent] | None = None
    is_provisional: bool = False
    known_limitation: str | None = None
    priority: int = 100
    effective_from: date
    effective_to: date | None = None


class FeeCategoryCreate(FeeCategoryBase):
    pass


class FeeCategoryUpdate(BaseModel):
    """PATCH body -- every field optional, only supplied fields are changed."""

    code: str | None = None
    revenue_stream: str | None = None
    label: str | None = None
    vehicle_type: str | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    counts_as_entry: bool | None = None
    is_revenue: bool | None = None
    components: list[FeeCategoryComponent] | None = None
    is_provisional: bool | None = None
    known_limitation: str | None = None
    priority: int | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class FeeCategoryResponse(BaseModel):
    id: int
    code: str
    revenue_stream: str
    label: str
    vehicle_type: str | None
    amount_min: float
    amount_max: float
    counts_as_entry: bool
    is_revenue: bool
    components: list[dict] | None
    is_provisional: bool
    known_limitation: str | None
    priority: int
    effective_from: date
    effective_to: date | None


class FeeCategoryListResponse(BaseModel):
    items: list[FeeCategoryResponse]


class ReclassifyTriggerInfo(BaseModel):
    """What every fee_categories/revenue_split write and manual reclassify
    endpoint returns: enough for a caller to poll progress in run_logs."""

    triggered: bool
    reason: str | None = None
    scoped_from: date | None = None
    scoped_to: date | None = None
    run_id: int | None = None
    celery_task_id: str | None = None
    status: str | None = None


class FeeCategoryWriteResponse(BaseModel):
    fee_category: FeeCategoryResponse
    reclassify: ReclassifyTriggerInfo


class ConflictRow(BaseModel):
    id: int
    code: str
    label: str
    amount_min: float
    amount_max: float
    effective_from: date
    effective_to: date | None


class ConflictErrorResponse(BaseModel):
    detail: str
    conflicting_rows: list[ConflictRow]


class RevenueSplitCreate(BaseModel):
    aicl_pct: float
    gsds_pct: float
    effective_from: date
    effective_to: date | None = None


class RevenueSplitConfigResponse(BaseModel):
    id: int
    aicl_pct: float
    gsds_pct: float
    effective_from: date
    effective_to: date | None


class RevenueSplitListResponse(BaseModel):
    items: list[RevenueSplitConfigResponse]


class RevenueSplitWriteResponse(BaseModel):
    revenue_split: RevenueSplitConfigResponse


class ManualReclassifyRequest(BaseModel):
    from_date: date
    to_date: date
    reason: str


class RunLogResponse(BaseModel):
    id: int
    run_type: str
    status: str
    window_from: str | None
    window_to: str | None
    rows_fetched: int | None = None
    rows_upserted: int | None = None
    error_message: str | None = None
    started_at: str
    finished_at: str | None = None


class UnmappedTransactionItem(BaseModel):
    paystack_transaction_id: int
    reference: str
    amount: float
    status: str | None
    channel: str | None
    terminal_serial: str | None
    location_name: str | None
    paid_at: str | None
    transaction_date: date | None


class UnmappedAmountSummaryItem(BaseModel):
    amount: float
    txn_count: int
    first_seen: date | None
    last_seen: date | None


class UnmappedTransactionsResponse(BaseModel):
    date_range: DateRange
    total_count: int
    items: list[UnmappedTransactionItem]
    by_amount: list[UnmappedAmountSummaryItem]
