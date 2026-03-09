from __future__ import annotations

import logging

from hedge_fund.config.settings import Settings
from hedge_fund.domain.exceptions import ConfigurationError
from hedge_fund.integrations.calendar.tavily import TavilyCalendarClient
from hedge_fund.integrations.calendar.twelvedata import TwelveDataCalendarClient
from hedge_fund.integrations.search.tavily import TavilySearchClient


def build_calendar_provider(
    settings: Settings,
    logger: logging.Logger,
    twelvedata_api_key: str | None,
    search_client: TavilySearchClient | None,
):
    provider = settings.calendar.provider
    if provider == "tavily":
        return TavilyCalendarClient(search_client, logger)
    if provider == "twelvedata":
        return TwelveDataCalendarClient(twelvedata_api_key, settings.data.request_timeout_seconds, logger)
    if search_client and getattr(search_client, "api_key", None):
        return TavilyCalendarClient(search_client, logger)
    raise ConfigurationError(
        "Auto calendar routing requires TAVILY_API_KEY for macro event search. "
        "Twelve Data's current official API does not expose a macroeconomic calendar endpoint."
    )


__all__ = ["TwelveDataCalendarClient", "TavilyCalendarClient", "build_calendar_provider"]
