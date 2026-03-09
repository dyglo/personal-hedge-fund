from __future__ import annotations

import logging
from datetime import date

from hedge_fund.domain.exceptions import ConfigurationError
from hedge_fund.domain.models import CalendarEvent


class TwelveDataCalendarClient:
    name = "twelvedata"
    base_url = "https://api.twelvedata.com"

    def __init__(self, api_key: str | None, timeout_seconds: float, logger: logging.Logger) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.logger = logger

    def fetch_events(self, start: date, end: date) -> list[CalendarEvent]:
        if not self.api_key:
            raise ConfigurationError("Missing TWELVEDATA_API_KEY for Twelve Data calendar requests.")
        raise ConfigurationError(
            "Twelve Data's official API currently documents earnings, dividends, splits, and IPO calendars, "
            "but not a macroeconomic calendar endpoint for forex event data. Use calendar.provider=auto or tavily."
        )
