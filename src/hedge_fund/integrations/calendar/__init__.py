from __future__ import annotations

import logging

from hedge_fund.config.settings import Settings
from hedge_fund.domain.exceptions import ConfigurationError
from hedge_fund.integrations.calendar.twelvedata import TwelveDataCalendarClient


def build_calendar_provider(
    settings: Settings,
    logger: logging.Logger,
    twelvedata_api_key: str | None,
    search_client=None,
):
    del search_client
    provider = "twelvedata" if settings.calendar.provider == "auto" else settings.calendar.provider
    if provider != "twelvedata":
        raise ConfigurationError("Calendar provider must be Twelve Data.")
    if not twelvedata_api_key:
        raise ConfigurationError("Missing TWELVE_DATA_API_KEY for Twelve Data calendar requests.")
    return TwelveDataCalendarClient(twelvedata_api_key, settings.data.request_timeout_seconds, logger)


__all__ = ["TwelveDataCalendarClient", "build_calendar_provider"]
