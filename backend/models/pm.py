from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class PM(Base):
    __tablename__ = "pms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    baseline_capacity: Mapped[int] = mapped_column(Integer, default=3)
    max_capacity: Mapped[int] = mapped_column(Integer, default=5)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Crew(Base):
    __tablename__ = "crews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    # Trades this crew works on: e.g., ["roofing"], ["siding"], or ["roofing", "siding"]
    # Used for trade-aware crew matching — a roofing-only crew is never assigned to a siding job.
    # Required when adding/editing via UI; backfilled from legacy specialties on first boot.
    trades: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    # Material specialties (NOT trades): slate, tpo, wood_shake, etc.
    # Optional. A roofing crew with specialties=["slate"] can do both standard asphalt
    # and the harder slate work.
    specialties: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Rank: 1 = best crew ("Michael Jordan"), higher = bench players
    # Default 999 for unranked crews — they get lowest priority in matching
    rank: Mapped[int] = mapped_column(Integer, default=999)
    # Free-form notes: "handles complex roofs, few warranties, steep pitch expert"
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
