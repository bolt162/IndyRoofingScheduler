import enum
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class NoteType(str, enum.Enum):
    SCHEDULING_DECISION = "scheduling_decision"
    NOT_BUILT = "not_built"
    SECONDARY_TRADE_ALERT = "secondary_trade_alert"
    WEATHER_ROLLBACK = "weather_rollback"
    STANDALONE_RULE = "standalone_rule"
    NIGHT_BEFORE_WEATHER = "night_before_weather"


class NoteLog(Base):
    __tablename__ = "note_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, index=True)
    jn_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note_type: Mapped[str] = mapped_column(String(50))
    note_text: Mapped[str] = mapped_column(Text)
    pushed_to_jn: Mapped[bool] = mapped_column(Boolean, default=False)
    template_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
