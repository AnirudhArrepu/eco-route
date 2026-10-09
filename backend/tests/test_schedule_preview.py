from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base
from app.schemas import ScheduleCreate, SchedulePreview
from app.service import create_schedule, get_schedule_timeline, preview_schedule


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def schedule_payload(stops):
    day = date.today() + timedelta(days=1)
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).replace(hour=9)
    end = start.replace(hour=18)
    return {
        "user_id": "preview-user",
        "date": day.isoformat(),
        "timezone": "UTC",
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "start_location": {"latitude": 13.0, "longitude": 80.2, "label": "home"},
        "end_location": {"latitude": 13.0, "longitude": 80.2, "label": "home"},
        "stops": stops,
        "constraints": [],
        "include_routines": False,
    }


def test_preview_returns_timeline_and_best_feasible_deadline_order(db_session):
    day = schedule_payload([])["date"]
    payload = schedule_payload([
        {"id": "late", "title": "later stop", "location": {"latitude": 13.03, "longitude": 80.23}, "duration_minutes": 20, "latest_start": f"{day}T17:00:00+00:00"},
        {"id": "early", "title": "early appointment", "location": {"latitude": 13.01, "longitude": 80.21}, "duration_minutes": 20, "latest_end": f"{day}T10:30:00+00:00"},
    ])
    result = preview_schedule(db_session, SchedulePreview.model_validate(payload), 100)
    assert result["feasible"]
    assert [stop["id"] for stop in result["stops"]] == ["early", "late"]
    assert result["timeline"][0]["start_at"] < result["timeline"][1]["start_at"]
    assert result["metrics"]["return_arrival_at"]


def test_create_schedule_persists_optimized_order_and_route_metrics(db_session):
    day = schedule_payload([])["date"]
    payload = schedule_payload([
        {"id": "late", "title": "later stop", "location": {"latitude": 13.03, "longitude": 80.23}, "duration_minutes": 20},
        {"id": "early", "title": "early appointment", "location": {"latitude": 13.01, "longitude": 80.21}, "duration_minutes": 20, "latest_end": f"{day}T10:30:00+00:00"},
    ])
    schedule = create_schedule(db_session, ScheduleCreate.model_validate(payload))
    saved = db_session.scalars(select(models.Stop).where(models.Stop.schedule_id == schedule.id).order_by(models.Stop.order_index)).all()
    assert [stop.id for stop in saved] == ["early", "late"]
    assert schedule.planning_metrics["distance_km"] > 0
    assert schedule.planning_timeline[0]["title"] == "early appointment"
    timeline = get_schedule_timeline(db_session, schedule.id, "preview-user")
    assert timeline["revision"] == 1
    assert timeline["timeline"][0]["title"] == "early appointment"


def test_preview_returns_deadline_conflicts_when_no_order_is_feasible(db_session):
    day = schedule_payload([])["date"]
    payload = schedule_payload([
        {"id": "impossible", "title": "impossible stop", "location": {"latitude": 13.02, "longitude": 80.22}, "duration_minutes": 60, "latest_end": f"{day}T09:01:00+00:00"},
    ])
    result = preview_schedule(db_session, SchedulePreview.model_validate(payload), 100)
    assert not result["feasible"]
    assert any(conflict["constraint_type"] == "latest_end" for conflict in result["conflicts"])
