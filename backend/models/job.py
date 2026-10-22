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
    # Other Trades — primary trade done in JN; app no longer splits by open/closed
    # secondaries (used to be primary_complete + waiting_on_trades).
    OTHER_TRADES = "other_trades"
    # Primary Completed — jobs in JN's COC/Punchlist or Job Complete (Job Review)
    # statuses. This is the review-style tab. Renamed from review_for_completion.
    PRIMARY_COMPLETED = "primary_completed"
    # Completed — JN's terminal "Completed" status. Not surfaced as a dashboard tab.
    COMPLETED = "completed"
    # Job exists in JN but moved to an untracked status (e.g., Lost, Disqualified, At Risk - Lead).
    # Hidden from main dashboard. Restored automatically if JN status moves back to tracked.
    ARCHIVED = "archived"


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
    ROOFING_REPAIR = "roofing_repair"
    SIDING = "siding"
    SIDING_REPAIR = "siding_repair"
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
    geocoded_address: Mapped[str | None] = mapped_column(String(500), nullable=True)  # address the spot was looked up for

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
    # Date ranges the customer asked us not to build: [{start, end, reason}] (see services/no_build.py)
    no_build_dates: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

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
    jn_number: Mapped[str | None] = mapped_column(String(50), nullable=True)  # JobNimbus job number (26426)
    # Siding goes on before the gutters on this job (the house's layout); normally gutters first
    siding_before_gutters: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    jn_notes_raw: Mapped[str | None] = mapped_column(Text, nullable=True)  # raw notes from JN
    ai_note_scan_result: Mapped[str | None] = mapped_column(Text, nullable=True)  # Claude's extraction

    # Weather
    weather_status: Mapped[str | None] = mapped_column(String(50), nullable=True)  # clear / do_not_build / scheduler_decision
    weather_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Secondary trades tracking
    primary_complete_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    secondary_trades_status: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {trade: status}

    # What JobNimbus has on the calendar (read every sync; JobNimbus is the source of truth).
    # jn_start_date: earliest Pending Start work order date, else the job's own start date.
    jn_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    jn_crews: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)  # crew names on that work order
    jn_pm: Mapped[str | None] = mapped_column(String(255), nullable=True)  # our PM on that work order (Luke Mroz)
    # [{number, trade, status, start, crews, internal_note, customer_note}] (see services/schedule_sync.py)
    jn_work_orders: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # A day picked on the Weekly Plan that hasn't been sent to JobNimbus yet. Kept apart from
    # bucket/date_scheduled so the JobNimbus sync never erases it and the customer emails, which
    # follow JobNimbus, don't treat a plan as a real booking.
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_pm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planned_crew_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Build days picked on the Weekly Plan card (else the suggestion below is used)
    planned_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Suggested build days from the Roofing work order's labor lines: {eff, squares, why} (services/build_days.py)
    days_estimate: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Suggested crew notes [{text, quote, source, kind}] and the ones the scheduler approved (services/crew_notes.py)
    crew_note_suggestions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    crew_notes_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    crew_notes_approved: Mapped[list | None] = mapped_column(JSON, nullable=True)
    crew_notes_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    crew_notes_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    planned_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    planned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # "Suggest builds" on the Weekly Plan (services/suggest.py): a day, crew and PM pencilled in for the
    # scheduler to Keep (copied into planned_*) or dismiss. Never sent to JobNimbus until it's kept.
    suggested_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    suggested_crew_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_pm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_why: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Push to JobNimbus (services/jn_booking.py): {date, by, work_order, work_order_status, ...}, one key
    # per finished step so a push that stopped halfway never repeats one. jn_push_error: why it stopped.
    jn_push_steps: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    jn_push_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Ready check: AI reads the notes for anything that would stop the build (services/ready_check.py).
    # ready_status: unchecked / clear / flagged (needs an answer) / ok (office said fine) / hold
    ready_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ready_flags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)  # [{issue, quote, source}]
    ready_input: Mapped[str | None] = mapped_column(Text, nullable=True)  # dated notes + work order notes
    ready_input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # input last checked
    ready_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ready_ok_quotes: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)  # flags an OK covered
    ready_decision_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ready_decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ready_decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stamped when the job was last re-analyzed by AI (note scan + score recompute)
    # If older than updated_at → job has changes that haven't been fed to AI yet
    last_ai_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
