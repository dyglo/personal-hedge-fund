from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime

import httpx

from hedge_fund.domain.exceptions import ProviderError
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


class TradingEconomicsCalendarClient:
    base_url = "https://api.tradingeconomics.com"

    def __init__(self, api_key: str | None, timeout_seconds: float, logger: logging.Logger) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.logger = logger

    def fetch_events(self, start: date, end: date) -> list[CalendarEvent]:
        params = {
            "c": self.api_key or "guest:guest",
            "f": "json",
        }
        url = f"{self.base_url}/calendar/country/All/{start.isoformat()}/{end.isoformat()}"
        try:
            response = httpx.get(url, params=params, timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.exception("TradingEconomics calendar request failed")
            raise ProviderError("TradingEconomics calendar request failed") from exc

        events = []
        for item in payload or []:
            event = self._coerce_event(item)
            if event is not None:
                events.append(event)
        events.sort(key=lambda item: f"{item.date}T{item.time_utc}")
        return events

    def _coerce_event(self, item: dict) -> CalendarEvent | None:
        event_dt = self._parse_datetime(item.get("Date") or item.get("ReferenceDate"))
        if event_dt is None:
            return None
        currency = self._resolve_currency(item)
        if not currency:
            return None
        impact = self._resolve_impact(item.get("Importance"))
        return CalendarEvent(
            date=event_dt.strftime("%Y-%m-%d"),
            time_utc=event_dt.strftime("%H:%M"),
            currency=currency,
            event_name=str(item.get("Event") or item.get("Category") or "Unknown event").strip(),
            impact=impact,
            forecast=self._stringify(item.get("Forecast")),
            previous=self._stringify(item.get("Previous")),
            country=self._stringify(item.get("Country")),
            source="TradingEconomics",
        )

    def _parse_datetime(self, value: object) -> datetime | None:
        if not value:
            return None
        if isinstance(value, str):
            match = re.search(r"/Date\((\d+)", value)
            if match:
                return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=UTC)
            cleaned = value.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(cleaned)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        return None

    def _resolve_currency(self, item: dict) -> str | None:
        currency = self._stringify(item.get("Currency"))
        if currency:
            return currency.upper()
        country = self._stringify(item.get("Country"))
        if country:
            mapped = COUNTRY_CURRENCY.get(country)
            if mapped:
                return mapped
        event_name = self._stringify(item.get("Event")) or ""
        if "fed" in event_name.lower() or "fomc" in event_name.lower() or "cpi" in event_name.lower():
            return "USD"
        return None

    def _resolve_impact(self, value: object) -> str:
        if isinstance(value, str):
            lowered = value.lower()
            if "high" in lowered or lowered == "3":
                return "High"
            if "medium" in lowered or lowered == "2":
                return "Medium"
            return "Low"
        if isinstance(value, (int, float)):
            if value >= 3:
                return "High"
            if value >= 2:
                return "Medium"
        return "Low"

    def _stringify(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
