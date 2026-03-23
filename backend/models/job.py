import enum
from datetime import datetime, date

from sqlalchemy import String, Float, Integer, Boolean, Text, DateTime, Date, Enum, JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class JobBucket(str, enum.Enum):
    PENDING_CONFIRMATION = "pending_confirmation"
    COMING_SOON = "coming_soon"
    TO_SCHEDULE = "to_schedule"
    SCHEDULED = "scheduled"
    NOT_BUILT = "not_built"
    PRIMARY_COMPLETE = "primary_complete"
    WAITING_ON_TRADES = "waiting_on_trades"
    REVIEW_FOR_COMPLETION = "review_for_completion"
    COMPLETED = "completed"


class PaymentType(str, enum.Enum):
    CASH = "cash"
    FINANCE = "finance"
    INSURANCE = "insurance"


class JobType(str, enum.Enum):
    INSURANCE = "insurance"
    RETAIL = "retail"


class DurationTier(str, enum.Enum):
    TIER_1 = "tier_1"       # ≤30 sq, auto-confirmed
    TIER_2 = "tier_2"       # 31-60 sq, yellow flag
    TIER_3 = "tier_3"       # 61+ sq, red flag
    LOW_SLOPE = "low_slope" # Hard gate, manual confirmation required


class MaterialType(str, enum.Enum):
    ASPHALT = "asphalt"
    POLYMER_MODIFIED = "polymer_modified"
    TPO = "tpo"
    DURO_LAST = "duro_last"
    EPDM = "epdm"
    COATING = "coating"
    WOOD_SHAKE = "wood_shake"
    SLATE = "slate"
    METAL = "metal"
    SIDING = "siding"
    OTHER = "other"


class TradeType(str, enum.Enum):
    ROOFING = "roofing"
    SIDING = "siding"
    GUTTERS = "gutters"
    WINDOWS = "windows"
    PAINT = "paint"
    INTERIOR = "interior"
    OTHER = "other"


LOW_SLOPE_MATERIALS = {MaterialType.TPO, MaterialType.DURO_LAST, MaterialType.EPDM, MaterialType.COATING}
SPECIALTY_MATERIALS = {MaterialType.WOOD_SHAKE, MaterialType.SLATE, MaterialType.METAL}


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    jn_job_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)

    # Customer info
    customer_name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(String(500))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Job classification
    job_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # insurance / retail
    payment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # cash / finance / insurance
    primary_trade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    secondary_trades: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    material_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    square_footage: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Dates
    date_entered: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    date_scheduled: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Sales & crew
    sales_rep: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_pm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_crew_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Duration
    duration_days: Mapped[int] = mapped_column(Integer, default=1)
    duration_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duration_source: Mapped[str | None] = mapped_column(String(255), nullable=True)  # "auto" or note quote

    # Flags
    permit_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    must_build: Mapped[bool] = mapped_column(Boolean, default=False)
    must_build_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    must_build_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    crew_requirement_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    crew_requirement_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    standalone_rule: Mapped[bool] = mapped_column(Boolean, default=False)
    standalone_option: Mapped[str | None] = mapped_column(String(50), nullable=True)  # saturday_build / sales_rep_managed

    # Scheduling state
    bucket: Mapped[str] = mapped_column(String(50), default=JobBucket.TO_SCHEDULE.value)
    rescheduled_count: Mapped[int] = mapped_column(Integer, default=0)
    not_built_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority_bump: Mapped[float] = mapped_column(Float, default=0.0)
    is_multi_day: Mapped[bool] = mapped_column(Boolean, default=False)
    multi_day_current: Mapped[int] = mapped_column(Integer, default=0)  # which day we're on

    # Score (last computed)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JN data
    jn_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jn_notes_raw: Mapped[str | None] = mapped_column(Text, nullable=True)  # raw notes from JN
    ai_note_scan_result: Mapped[str | None] = mapped_column(Text, nullable=True)  # Claude's extraction

    # Weather
    weather_status: Mapped[str | None] = mapped_column(String(50), nullable=True)  # clear / do_not_build / scheduler_decision
    weather_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Secondary trades tracking
    primary_complete_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    secondary_trades_status: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {trade: status}

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
