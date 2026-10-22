from datetime import datetime, date
from pydantic import BaseModel


class JobBase(BaseModel):
    customer_name: str
    address: str
    job_type: str | None = None
    payment_type: str | None = None
    primary_trade: str | None = None
    secondary_trades: list[str] | None = None
    material_type: str | None = None
    square_footage: float | None = None
    sales_rep: str | None = None


class JobResponse(JobBase):
    id: int
    jn_job_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    date_entered: datetime | None = None
    date_scheduled: date | None = None
    assigned_pm_id: int | None = None
    assigned_crew_id: int | None = None
    duration_days: int = 1
    duration_confirmed: bool = False
    duration_tier: str | None = None
    duration_source: str | None = None
    permit_confirmed: bool = False
    must_build: bool = False
    must_build_deadline: date | None = None
    must_build_reason: str | None = None
    crew_requirement_flag: bool = False
    crew_requirement_note: str | None = None
    standalone_rule: bool = False
    standalone_option: str | None = None
    no_build_dates: list[dict] | None = None
    bucket: str = "to_schedule"
    rescheduled_count: int = 0
    not_built_reason: str | None = None
    priority_bump: float = 0.0
    is_multi_day: bool = False
    score: float = 0.0
    score_explanation: str | None = None
    jn_status: str | None = None
    jn_number: str | None = None
    siding_before_gutters: bool = False
    jn_notes_raw: str | None = None
    ai_note_scan_result: str | None = None
    weather_status: str | None = None
    weather_detail: str | None = None
    primary_complete_date: datetime | None = None
    secondary_trades_status: dict | None = None
    created_at: datetime
    updated_at: datetime
    last_ai_analyzed_at: datetime | None = None
    # JobNimbus calendar, Weekly Plan plan, notes ready check
    jn_start_date: date | None = None
    jn_crews: list[str] | None = None
    jn_pm: str | None = None
    jn_work_orders: list[dict] | None = None
    planned_date: date | None = None
    planned_pm_id: int | None = None
    planned_crew_id: int | None = None
    planned_days: int | None = None
    crew_note_suggestions: list[dict] | None = None
    crew_notes_approved: list[str] | None = None
    crew_notes_by: str | None = None
    crew_notes_at: datetime | None = None
    jn_push_steps: dict | None = None
    jn_push_error: str | None = None
    planned_by: str | None = None
    planned_at: datetime | None = None
    suggested_date: date | None = None
    suggested_crew_id: int | None = None
    suggested_pm_id: int | None = None
    suggested_days: int | None = None
    suggested_why: str | None = None
    ready_status: str | None = None
    ready_flags: list[dict] | None = None
    ready_checked_at: datetime | None = None
    ready_decision_by: str | None = None
    ready_decision_at: datetime | None = None
    ready_decision_note: str | None = None

    model_config = {"from_attributes": True}


class JobCreate(BaseModel):
    """Schema for manually creating a new job (not from JN sync)."""
    customer_name: str
    address: str
    job_type: str = "retail"
    payment_type: str = "cash"
    primary_trade: str = "roofing"
    secondary_trades: list[str] = []
    material_type: str = "asphalt"
    square_footage: float | None = None
    sales_rep: str | None = None
    duration_days: int = 1
    notes: str | None = None


class JobUpdate(BaseModel):
    # Scheduling fields
    must_build: bool | None = None
    must_build_deadline: date | None = None
    must_build_reason: str | None = None
    bucket: str | None = None
    not_built_reason: str | None = None
    assigned_pm_id: int | None = None
    assigned_crew_id: int | None = None
    date_scheduled: date | None = None
    duration_days: int | None = None
    duration_confirmed: bool | None = None
    standalone_option: str | None = None
    # Editable job details (for manual correction / when JN fields are missing)
    customer_name: str | None = None
    address: str | None = None
    job_type: str | None = None
    payment_type: str | None = None
    primary_trade: str | None = None
    secondary_trades: list[str] | None = None
    material_type: str | None = None
    square_footage: float | None = None
    sales_rep: str | None = None
    notes: str | None = None  # Maps to jn_notes_raw
    permit_confirmed: bool | None = None
    crew_requirement_flag: bool | None = None
    # Scheduler already confirmed it's OK to build inside the job's No-Build Dates
    override_no_build: bool | None = None
    # Weekly Plan pick (not sent to JobNimbus). planned_date null clears the plan.
    planned_date: date | None = None
    planned_pm_id: int | None = None
    planned_crew_id: int | None = None
    planned_days: int | None = None
    siding_before_gutters: bool | None = None


class CrewNotesRequest(BaseModel):
    lines: list[str]


class ReadyDecisionRequest(BaseModel):
    decision: str  # "ok" (fine to schedule) or "hold"
    note: str | None = None


class NoBuildWindow(BaseModel):
    start: date
    end: date
    reason: str | None = None


class NoBuildDatesRequest(BaseModel):
    windows: list[NoBuildWindow]


class NotBuiltRequest(BaseModel):
    reason: str
    detail: str | None = None


class ScoringResult(BaseModel):
    job_id: int
    score: float
    explanation: str
    cluster_id: str | None = None


class ScoringResponse(BaseModel):
    recommendations: list[ScoringResult]
    clusters: list[dict]
    ai_explanation: str
