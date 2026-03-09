from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import httpx

from hedge_fund.domain.exceptions import ConfigurationError, ProviderError
from hedge_fund.domain.models import CalendarEvent


COUNTRY_CURRENCY = {
    "United States": "USD",
    "Euro Area": "EUR",
    "Germany": "EUR",
    "France": "EUR",
    "Italy": "EUR",
    "United Kingdom": "GBP",
    "Japan": "JPY",
    "Switzerland": "CHF",
    "Australia": "AUD",
    "New Zealand": "NZD",
    "Canada": "CAD",
}


class TwelveDataCalendarClient:
    base_url = "https://api.twelvedata.com"

    def __init__(self, api_key: str | None, timeout_seconds: float, logger: logging.Logger) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.logger = logger

    def fetch_events(self, start: date, end: date) -> list[CalendarEvent]:
        if not self.api_key:
            raise ConfigurationError("Missing TWELVEDATA_API_KEY for Twelve Data calendar requests.")
        try:
            response = httpx.get(
                f"{self.base_url}/earnings_calendar",
                params={
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "apikey": self.api_key,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.exception("Twelve Data calendar request failed")
            raise ProviderError("Twelve Data calendar request failed") from exc

        rows = []
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            for key in ("data", "earnings_calendar", "earnings"):
                if isinstance(payload.get(key), list):
                    rows = payload[key]
                    break
        events = []
        for item in rows:
            event = self._coerce_event(item)
            if event is not None:
                events.append(event)
        events.sort(key=lambda item: f"{item.date}T{item.time_utc}")
        return events

    def _coerce_event(self, item: dict) -> CalendarEvent | None:
        event_date = self._parse_date(item.get("date") or item.get("earnings_date") or item.get("report_date"))
        if event_date is None:
            return None
        country = self._stringify(item.get("country"))
        currency = self._stringify(item.get("currency"))
        if not currency and country:
            currency = COUNTRY_CURRENCY.get(country)
        if not currency:
            return None
        symbol = self._stringify(item.get("symbol")) or self._stringify(item.get("ticker")) or "Unknown"
        event_name = self._stringify(item.get("event_name")) or f"{symbol} earnings"
        forecast = self._stringify(item.get("eps_estimate")) or self._stringify(item.get("revenue_estimate"))
        previous = self._stringify(item.get("eps_actual")) or self._stringify(item.get("revenue"))
        return CalendarEvent(
            date=event_date.strftime("%Y-%m-%d"),
            time_utc="00:00",
            currency=currency.upper(),
            event_name=event_name,
            impact="Medium",
            forecast=forecast,
            previous=previous,
            country=country,
            source="Twelve Data",
        )

    def _parse_date(self, value: object) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)
        except ValueError:
            return None

    def _stringify(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
