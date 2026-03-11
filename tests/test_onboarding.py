from __future__ import annotations

import logging
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hedge_fund.api import app, get_context
from hedge_fund.config.settings import Settings
from hedge_fund.services.prophet_md_generator import generate_prophet_md
from hedge_fund.storage.base import Base
from hedge_fund.storage.chat_repository import ProphetMemoryRepository
from hedge_fund.storage.models import UserProfileRecord  # noqa: F401
from hedge_fund.storage.profile_repository import UserProfileRepository


def _client():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine)

    class FakeContext:
        def __init__(self) -> None:
            self.settings = Settings.load()
            self.logger = logging.getLogger("test.onboarding")

        @contextmanager
        def session_scope(self):
            session = SessionLocal()
            try:
                yield session
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        def create_user_profile_repository(self, session):
            return UserProfileRepository(session, self.logger)

        def create_memory_repository(self, session, device_token=None):
            return ProphetMemoryRepository(session, self.logger, device_token=device_token)

    context = FakeContext()
    app.dependency_overrides[get_context] = lambda: context
    client = TestClient(app)
    return client


def _payload(experience_level: str = "beginner") -> dict:
    return {
        "display_name": "Tafar",
        "experience_level": experience_level,
        "watchlist": ["XAUUSD", "EURUSD"],
        "account_balance": 10000,
        "risk_pct": 1.0,
        "min_rr": "1:2",
        "sessions": ["London", "New York"],
    }


def test_onboard_valid_payload_creates_profile_and_returns_preview() -> None:
    client = _client()

    response = client.post("/api/v1/onboard", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert len(body["device_token"]) == 36
    assert body["display_name"] == "Tafar"
    assert body["prophet_md_preview"].startswith("# PROPHET - My Trading Rules")
    assert "Welcome to Prophet" in body["message"]
    app.dependency_overrides.clear()


def test_onboard_missing_required_field_returns_422() -> None:
    client = _client()

    response = client.post("/api/v1/onboard", json={key: value for key, value in _payload().items() if key != "display_name"})

    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_duplicate_onboarding_creates_distinct_profiles() -> None:
    client = _client()

    first = client.post("/api/v1/onboard", json=_payload()).json()
    second = client.post("/api/v1/onboard", json=_payload()).json()

    assert first["device_token"] != second["device_token"]
    app.dependency_overrides.clear()


def test_profile_lookup_returns_profile_for_valid_device_token() -> None:
    client = _client()
    onboard = client.post("/api/v1/onboard", json=_payload()).json()

    response = client.get("/api/v1/profile", headers={"X-Device-Token": onboard["device_token"]})

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Tafar"
    assert body["watchlist"] == ["XAUUSD", "EURUSD"]
    app.dependency_overrides.clear()


def test_profile_lookup_returns_404_for_invalid_device_token() -> None:
    client = _client()

    response = client.get("/api/v1/profile", headers={"X-Device-Token": "missing-token"})

    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_generate_prophet_md_adds_beginner_rule() -> None:
    result = generate_prophet_md(SimpleNamespace(**_payload("beginner")))

    assert "Review H1 structure before every session" in result


def test_generate_prophet_md_adds_professional_rule() -> None:
    result = generate_prophet_md(SimpleNamespace(**_payload("professional")))

    assert "Treat every session independently, no revenge trading" in result


def test_generate_prophet_md_stays_plain_text() -> None:
    result = generate_prophet_md(SimpleNamespace(**_payload("intermediate")))

    assert "```" not in result
    assert '{"' not in result
