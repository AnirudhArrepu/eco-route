from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict

class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    label: str | None = None

class ConstraintIn(BaseModel):
    type: str
    hardness: Literal["hard", "soft"] = "hard"
    weight: float = 1.0
    parameters: dict[str, Any] = Field(default_factory=dict)

class RoutineIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    weekday: int = Field(ge=0, le=6)
    stop: "StopIn"
    active: bool = True

class StopIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    title: str
    type: str = "errand"
    location: Location
    duration_minutes: int = Field(gt=0, le=1440)
    earliest_start: datetime | None = None
    latest_start: datetime | None = None
    latest_end: datetime | None = None
    fixed_start: datetime | None = None
    opening_hours: dict[str, Any] | None = None
    priority: int = Field(default=3, ge=1, le=5)
    mandatory: bool = False
    status: str = "planned"
    source: str = "user"
    attributes: dict[str, Any] = Field(default_factory=dict)

class ScheduleCreate(BaseModel):
    user_id: str
    date: date
    timezone: str = "UTC"
    start_at: datetime
    end_at: datetime
    start_location: Location
    end_location: Location
    stops: list[StopIn] = Field(default_factory=list)
    constraints: list[ConstraintIn] = Field(default_factory=list)
    include_routines: bool = True

class AddStopRequest(BaseModel):
    user_id: str
    destination: StopIn
    constraints: list[ConstraintIn] = Field(default_factory=list)
    allow_reordering_flexible_stops: bool = True
    max_reordered_stops: int = Field(default=3, ge=0, le=8)

class ReplanRequest(BaseModel):
    user_id: str
    updates: dict[str, dict[str, Any]] = Field(default_factory=dict)
    constraints: list[ConstraintIn] = Field(default_factory=list)
    allow_reordering_flexible_stops: bool = True
    max_reordered_stops: int = Field(default=3, ge=0, le=8)
    reason: str = "User requested replanning"

class AgentRequest(BaseModel):
    user_id: str
    text: str
    schedule_id: str | None = None
    timezone: str = "UTC"

class PreferenceUpdate(BaseModel):
    value: dict[str, Any]
    confidence: float = Field(default=1.0, ge=0, le=1)
    source: str = "explicit"

class RoutineCreate(BaseModel):
    user_id: str
    routine: RoutineIn

class RoutineUpdate(BaseModel):
    user_id: str
    routine: RoutineIn

class ApproveRequest(BaseModel):
    user_id: str
    idempotency_key: str = Field(min_length=8, max_length=128)

class RejectRequest(BaseModel):
    user_id: str
    reason: str | None = None

class PreferenceIn(BaseModel):
    user_id: str
    key: str
    value: dict[str, Any]
    confidence: float = Field(default=1.0, ge=0, le=1)
    source: str = "explicit"
