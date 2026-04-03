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
    bucket: str = "to_schedule"
    rescheduled_count: int = 0
    not_built_reason: str | None = None
    priority_bump: float = 0.0
    is_multi_day: bool = False
    score: float = 0.0
    score_explanation: str | None = None
    jn_status: str | None = None
    jn_notes_raw: str | None = None
    ai_note_scan_result: str | None = None
    weather_status: str | None = None
    weather_detail: str | None = None
    primary_complete_date: datetime | None = None
    secondary_trades_status: dict | None = None
    created_at: datetime
    updated_at: datetime

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
