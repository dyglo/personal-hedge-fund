from datetime import UTC, datetime

from hedge_fund.chat.utils import current_session_status, normalize_pair_alias
from hedge_fund.config.settings import SessionWindowConfig, SessionsConfig


def test_pair_alias_normalization() -> None:
    cases = {
        "Gold": "XAUUSD",
        "XAU": "XAUUSD",
        "XAU/USD": "XAUUSD",
        "Euro": "EURUSD",
        "EUR/USD": "EURUSD",
        "Cable": "GBPUSD",
        "Pound": "GBPUSD",
        "GBP/USD": "GBPUSD",
        "Yen": "USDJPY",
        "USD/JPY": "USDJPY",
    }

    for raw, expected in cases.items():
        assert normalize_pair_alias(raw) == expected


def _sessions() -> SessionsConfig:
    return SessionsConfig(
        asia=SessionWindowConfig(start="22:00", end="06:00"),
        london=SessionWindowConfig(start="07:00", end="15:00"),
        new_york=SessionWindowConfig(start="13:00", end="21:00"),
    )


def test_session_status_reports_closed_on_saturday() -> None:
    status = current_session_status(
        _sessions(),
        datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
    )

    assert status["current_session"] == "Closed"
    assert status["opens_at"] == "22:00"
    assert status["time_until_open"] == "1d 12h"
    assert "Market closed." in status["status"]


def test_session_status_reports_closed_on_friday_after_close() -> None:
    status = current_session_status(
        _sessions(),
        datetime(2026, 3, 13, 22, 30, tzinfo=UTC),
    )

    assert status["current_session"] == "Closed"
    assert status["opens_at"] == "22:00"
    assert status["time_until_open"] == "1d 23h 30m"
    assert "Market closed." in status["status"]


def test_session_status_reports_closed_on_sunday_before_open() -> None:
    status = current_session_status(
        _sessions(),
        datetime(2026, 3, 15, 21, 0, tzinfo=UTC),
    )

    assert status["current_session"] == "Closed"
    assert status["opens_at"] == "22:00"
    assert status["time_until_open"] == "1h"
    assert "Market closed." in status["status"]


def test_session_status_reports_time_until_open_on_weekday_off_hours() -> None:
    status = current_session_status(
        _sessions(),
        datetime(2026, 3, 10, 21, 30, tzinfo=UTC),
    )

    assert status["current_session"] == "Closed"
    assert status["opens_at"] == "22:00"
    assert status["time_until_open"] == "30m"
    assert "Asia opens at 22:00 UTC (in 30m)." in status["status"]
