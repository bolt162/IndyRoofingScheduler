import enum
from datetime import datetime, date

from sqlalchemy import String, Integer, Text, DateTime, Date, JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class PlanStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class SchedulePlan(Base):
    __tablename__ = "schedule_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_date: Mapped[date] = mapped_column(Date, index=True)
    pm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    job_ids: Mapped[list] = mapped_column(JSON, default=list)
    cluster_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=PlanStatus.DRAFT.value)
    weather_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
