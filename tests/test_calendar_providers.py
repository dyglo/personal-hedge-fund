import logging
from datetime import date

import pytest

from hedge_fund.config.settings import Settings
from hedge_fund.domain.exceptions import ConfigurationError
from hedge_fund.integrations.calendar import TavilyCalendarClient, build_calendar_provider


class FakeTavilySearchClient:
    api_key = "key"

    def raw_search(self, query: str):
        return {
            "answer": (
                '{"events":['
                '{"date":"2026-03-09","time_utc":"13:30","currency":"USD","event_name":"US CPI","impact":"High","forecast":"2.9%","previous":"3.0%","country":"United States"},'
                '{"date":"2026-03-09","time_utc":"09:00","currency":"EUR","event_name":"ECB President Speaks","importance":"2","forecast":null,"previous":null,"country":"Euro Area"}'
                "]}"
            ),
            "results": [],
        }


def test_tavily_calendar_client_parses_structured_answer() -> None:
    client = TavilyCalendarClient(FakeTavilySearchClient(), logging.getLogger("test"))

    events = client.fetch_events(date(2026, 3, 9), date(2026, 3, 9))

    assert len(events) == 2
    assert events[0].event_name == "ECB President Speaks"
    assert events[1].impact == "High"


def test_build_calendar_provider_uses_tavily_for_auto_when_available() -> None:
    settings = Settings.load()
    provider = build_calendar_provider(
        settings,
        logging.getLogger("test"),
        twelvedata_api_key="td-key",
        search_client=FakeTavilySearchClient(),
    )

    assert provider.name == "tavily"


def test_build_calendar_provider_raises_for_missing_auto_providers() -> None:
    settings = Settings.load()

    with pytest.raises(ConfigurationError):
        build_calendar_provider(
            settings,
            logging.getLogger("test"),
            twelvedata_api_key=None,
            search_client=None,
        )

    with pytest.raises(ConfigurationError):
        build_calendar_provider(
            settings,
            logging.getLogger("test"),
            twelvedata_api_key="td-key",
            search_client=None,
        )


def test_tavily_calendar_client_requires_search_client() -> None:
    client = TavilyCalendarClient(None, logging.getLogger("test"))

    with pytest.raises(ConfigurationError):
        client.fetch_events(date(2026, 3, 9), date(2026, 3, 9))
