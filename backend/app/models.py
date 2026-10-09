from datetime import datetime, timezone
from sqlalchemy import String, Integer, Date, DateTime, Boolean, Float, ForeignKey, JSON, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

def now():
    return datetime.now(timezone.utc)

class Schedule(Base):
    __tablename__ = "schedules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    schedule_date: Mapped[object] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    start_location: Mapped[dict] = mapped_column(JSON)
    end_location: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="active")
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Stop(Base):
    __tablename__ = "schedule_stops"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schedule_id: Mapped[str] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(256))
    type: Mapped[str] = mapped_column(String(64), default="errand")
    location: Mapped[dict] = mapped_column(JSON)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    earliest_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fixed_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opening_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="planned")
    source: Mapped[str] = mapped_column(String(32), default="user")
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)

class ScheduleConstraint(Base):
    __tablename__ = "schedule_constraints"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schedule_id: Mapped[str] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(64))
    hardness: Mapped[str] = mapped_column(String(16), default="hard")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)

class Preference(Base):
    __tablename__ = "preferences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    key: Mapped[str] = mapped_column(String(128))
    value: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(64), default="explicit")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_preference_user_key"),)

class Routine(Base):
    __tablename__ = "routines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(128))
    weekday: Mapped[int] = mapped_column(Integer)
    stop: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Proposal(Base):
    __tablename__ = "plan_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schedule_id: Mapped[str] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    base_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    operation: Mapped[str] = mapped_column(String(32))
    proposed_stops: Mapped[list] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    conflicts: Mapped[list] = mapped_column(JSON, default=list)
    explanation_facts: Mapped[list] = mapped_column(JSON, default=list)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class PlanRevision(Base):
    __tablename__ = "plan_revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schedule_id: Mapped[str] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("schedule_id", "revision_number", name="uq_revision_schedule_number"),)
