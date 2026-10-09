import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base, get_db
from app.main import app
from app.config import settings


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    migrate_before = settings.auto_migrate
    settings.auto_migrate = False
    with TestClient(app) as test_client:
        yield test_client
    settings.auto_migrate = migrate_before
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def schedule_payload():
    return {
        "user_id": "local-user",
        "date": "2026-10-12",
        "timezone": "Asia/Kolkata",
        "start_at": "2026-10-12T09:00:00+05:30",
        "end_at": "2026-10-12T19:00:00+05:30",
        "start_location": {"latitude": 13.0, "longitude": 80.2},
        "end_location": {"latitude": 13.0, "longitude": 80.2},
        "stops": [],
        "constraints": [],
    }


@pytest.fixture
def destination():
    return {
        "title": "grocery store",
        "type": "errand",
        "location": {"latitude": 13.02, "longitude": 80.22},
        "duration_minutes": 30,
        "mandatory": True,
    }
