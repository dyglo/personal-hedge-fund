import logging
from datetime import date

import pytest

from hedge_fund.config.settings import Settings
from hedge_fund.domain.models import CalendarEvent
from hedge_fund.domain.exceptions import ConfigurationError, ProviderError
from hedge_fund.integrations.calendar import TwelveDataCalendarClient, build_calendar_provider
from hedge_fund.services.calendar_service import CalendarService


def test_build_calendar_provider_uses_twelvedata_for_auto() -> None:
    settings = Settings.load()
    provider = build_calendar_provider(
        settings,
        logging.getLogger("test"),
        twelvedata_api_key="td-key",
        search_client=None,
    )

    assert provider.name == "twelvedata"


def test_build_calendar_provider_raises_for_missing_twelvedata_key() -> None:
    settings = Settings.load()

    with pytest.raises(ConfigurationError) as exc_info:
        build_calendar_provider(
            settings,
            logging.getLogger("test"),
            twelvedata_api_key=None,
            search_client=None,
        )

    assert "TWELVE_DATA_API_KEY" in str(exc_info.value)


def test_twelvedata_calendar_client_maps_corporate_calendar_events(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, path, params=None):
            calls.append((path, params))
            payloads = {
                "/earnings_calendar": {"data": [{"date": "2026-03-09", "symbol": "AAPL", "name": "Apple"}]},
                "/dividends_calendar": {"data": [{"date": "2026-03-10", "symbol": "MSFT", "company_name": "Microsoft", "amount": "0.75"}]},
                "/splits_calendar": {"data": []},
                "/ipo_calendar": {"data": [{"date": "2026-03-11", "symbol": "NEWC"}]},
            }
            return FakeResponse(payloads[path])

    monkeypatch.setattr("hedge_fund.integrations.calendar.twelvedata.httpx.Client", FakeClient)

    client = TwelveDataCalendarClient("key", 5.0, logging.getLogger("test"))
    events = client.fetch_events(date(2026, 3, 9), date(2026, 3, 11))

    assert [item.event_name for item in events] == [
        "AAPL Earnings (Apple)",
        "MSFT Dividend (Microsoft)",
        "NEWC IPO",
    ]
    assert calls[0][0] == "/earnings_calendar"
    assert calls[0][1]["start_date"] == "2026-03-09"


def test_twelvedata_calendar_client_raises_provider_error_on_http_failure(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, path, params=None):
            raise RuntimeError("boom")

    monkeypatch.setattr("hedge_fund.integrations.calendar.twelvedata.httpx.Client", FakeClient)

    client = TwelveDataCalendarClient("key", 5.0, logging.getLogger("test"))
    with pytest.raises(ProviderError):
        client.fetch_events(date(2026, 3, 9), date(2026, 3, 9))


def test_calendar_service_emits_single_twelvedata_warning() -> None:
    events = [
        CalendarEvent(date="2026-03-09", time_utc="00:00", currency="EARN", event_name="AAPL Earnings", impact="High", source="Twelve Data"),
        CalendarEvent(date="2026-03-09", time_utc="00:00", currency="DIV", event_name="MSFT Dividend", impact="Medium", source="Twelve Data"),
    ]

    warnings = CalendarService(object())._build_warnings(events, ["EURUSD"])  # noqa: SLF001

    assert len(warnings) == 1
    assert "corporate events" in warnings[0].message
