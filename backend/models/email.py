"""
Build queue customer email state.

EmailState   — one row per job per mode ("test" / "live"): where the job is in its email
               sequence, the last weekly "builds ahead" snapshot, reschedule track, and
               suppression. Test and live progress are kept apart so test sends to Aaron
               never count as the customer having received an email.
EmailLog     — one row per send attempt (or dry run / office flag), for audit.
JobEvent     — bucket transitions observed during JN sync. Used to know when a job
               actually entered the build queue and how many builds finished this week.
"""
from datetime import datetime, date

from sqlalchemy import String, Integer, Boolean, Text, DateTime, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class EmailState(Base):
    __tablename__ = "email_states"
    __table_args__ = (UniqueConstraint("job_id", "mode", name="uq_email_state_job_mode"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, index=True)
    mode: Mapped[str] = mapped_column(String(10), default="live")  # test / live

    # When the job entered the build queue (first seen in a to_schedule status)
    entered_queue_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Sequence position: 0 = nothing sent, welcome sets it to 0 and welcome_sent=True,
    # weekly emails advance 1..8, after week 8 the rotation index advances.
    welcome_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    sequence_week: Mapped[int] = mapped_column(Integer, default=0)
    rotation_index: Mapped[int] = mapped_column(Integer, default=0)
    getting_close_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Last weekly "builds ahead" number we showed (or would have shown) the customer
    last_jobs_ahead: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Last customer email that counts toward the one-per-week limit
    # (reschedule emails do not count)
    last_counted_email_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Reschedule handling
    reschedule_track: Mapped[bool] = mapped_column(Boolean, default=False)
    reschedule_count_seen: Mapped[int] = mapped_column(Integer, default=0)
    original_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reschedule_pending_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # "You're scheduled" fun email: when we first saw the job scheduled, and whether it went
    scheduled_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scheduled_email_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Long-wait alerts to Greg and the rep: last week number alerted (10, 12, 14...)
    long_wait_alert_week: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Suppression: commercial, complaint, unsubscribed, manual pause
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)
    suppressed_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    template: Mapped[str] = mapped_column(String(100))
    recipient: Mapped[str | None] = mapped_column(String(500), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mode: Mapped[str] = mapped_column(String(20))  # off / test / live / dry_run
    # sent / failed / skipped / dry_run / office_flag
    result: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ProductClassification(Base):
    """
    A shingle product that wasn't in the built-in table (products.py). It is researched
    automatically, then held for office approval. Only approved rows are used in emails;
    until then the customer gets the no-rating Week 2 version.
    """
    __tablename__ = "product_classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_key: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    raw_text: Mapped[str] = mapped_column(Text)              # as it appeared on the material order
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    impact_class: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 4 / 3 / None = no rating
    composition: Mapped[str | None] = mapped_column(String(30), nullable=True)  # oxidized / polymer_modified
    # new -> pending_review -> approved / rejected; research_failed retries
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of {url, title}
    research_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TeamContact(Base):
    """
    Reps and PMs whose contact info can appear in emails. JobNimbus only stores the rep's
    name, so phone/email live here. Only active people are ever named in an email; a job
    whose rep isn't listed (or has left) falls back to the office number.
    """
    __tablename__ = "team_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    jn_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # as JobNimbus shows it
    display_name: Mapped[str] = mapped_column(String(255))  # how customers see it
    role: Mapped[str] = mapped_column(String(20), default="rep")  # rep / pm / ops / owner
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, index=True)
    from_bucket: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_bucket: Mapped[str] = mapped_column(String(50))
    primary_trade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
