from __future__ import annotations

import logging
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hedge_fund.api import app, get_context
from hedge_fund.services.communication_styles import get_style_modifier
from hedge_fund.services.prophet_md_generator import generate_prophet_md
from hedge_fund.services.skill_detector import detect_skill_signals
from hedge_fund.config.settings import Settings
from hedge_fund.storage.base import Base
from hedge_fund.storage.chat_repository import ProphetMemoryRepository
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
            self.logger = logging.getLogger("test.adaptive")

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
    return TestClient(app)


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


def test_get_style_modifier_returns_beginner_modifier() -> None:
    assert "Beginner-friendly" in get_style_modifier("beginner")


def test_get_style_modifier_returns_professional_modifier() -> None:
    assert "Professional trader" in get_style_modifier("professional")


def test_get_style_modifier_defaults_to_intermediate_modifier() -> None:
    assert "Intermediate trader" in get_style_modifier("unknown")


def test_detect_skill_signals_returns_high_confidence_experienced_suggestion() -> None:
    result = detect_skill_signals(
        [
            "I like FVG and liquidity sweep entries.",
            "I wait for confluence and market structure confirmation.",
            "My RR and lot size read all line up.",
        ],
        current_level="beginner",
    )

    assert result["confidence"] == "high"
    assert result["suggested_level"] == "experienced"
    assert result["should_suggest"] is True


def test_detect_skill_signals_returns_beginner_suggestion_for_foundational_questions() -> None:
    result = detect_skill_signals(
        [
            "What does trend mean?",
            "Can you explain candles?",
            "What should I do here?",
        ],
        current_level="experienced",
    )

    assert result["suggested_level"] == "beginner"
    assert result["should_suggest"] is False


def test_detect_skill_signals_requires_three_messages_before_suggesting() -> None:
    result = detect_skill_signals(
        [
            "FVG liquidity sweep confluence RR",
            "market structure fibonacci retracement",
        ],
        current_level="beginner",
    )

    assert result["should_suggest"] is False


def test_detect_skill_signals_reports_low_confidence_for_mixed_low_signal_history() -> None:
    result = detect_skill_signals(
        [
            "FVG",
            "thank you for the update",
            "this sounds fine to me",
        ],
        current_level="intermediate",
    )

    assert result["confidence"] == "low"
    assert result["should_suggest"] is False


def test_patch_profile_updates_experience_level_in_database() -> None:
    client = _client()
    onboard = client.post("/api/v1/onboard", json=_payload("beginner")).json()

    response = client.patch(
        "/api/v1/profile",
        headers={"X-Device-Token": onboard["device_token"]},
        json={"experience_level": "experienced"},
    )

    assert response.status_code == 200
    assert response.json()["experience_level"] == "experienced"
    app.dependency_overrides.clear()


def test_patch_profile_returns_404_for_invalid_device_token() -> None:
    client = _client()

    response = client.patch(
        "/api/v1/profile",
        headers={"X-Device-Token": "missing-token"},
        json={"experience_level": "experienced"},
    )

    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_patch_profile_regenerates_prophet_md_when_experience_level_changes() -> None:
    client = _client()
    onboard = client.post("/api/v1/onboard", json=_payload("beginner")).json()

    response = client.patch(
        "/api/v1/profile",
        headers={"X-Device-Token": onboard["device_token"]},
        json={"experience_level": "professional"},
    )
    memory = client.get("/memory", headers={"X-Device-Token": onboard["device_token"]}).json()["content"]

    assert response.status_code == 200
    assert "Experience: professional" in memory
    assert "Treat every session independently, no revenge trading" in memory
    assert memory != generate_prophet_md(type("Profile", (), _payload("beginner"))())
    app.dependency_overrides.clear()
