from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import httpx

from hedge_fund.domain.exceptions import ConfigurationError, ProviderError
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
            raise ConfigurationError("Missing TWELVE_DATA_API_KEY for Twelve Data calendar requests.")

        events: list[CalendarEvent] = []
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            events.extend(self._fetch_endpoint(client, "earnings_calendar", start, end, "EARN", "High"))
            events.extend(self._fetch_endpoint(client, "dividends_calendar", start, end, "DIV", "Medium"))
            events.extend(self._fetch_endpoint(client, "splits_calendar", start, end, "SPLT", "Medium"))
            events.extend(self._fetch_endpoint(client, "ipo_calendar", start, end, "IPO", "High"))
        events.sort(key=lambda item: f"{item.date}T{item.time_utc}:{item.event_name}")
        return events

    def _fetch_endpoint(
        self,
        client: httpx.Client,
        endpoint: str,
        start: date,
        end: date,
        currency: str,
        impact: str,
    ) -> list[CalendarEvent]:
        params = {
            "apikey": self.api_key,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        try:
            response = client.get(f"/{endpoint}", params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            self.logger.warning("Twelve Data calendar request failed for %s: %s", endpoint, exc)
            raise ProviderError(f"Twelve Data {endpoint} request failed.") from exc

        rows = payload.get("data")
        if not isinstance(rows, list):
            return []
        events = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            event = self._coerce_event(item, endpoint, currency, impact)
            if event is not None:
                events.append(event)
        return events

    def _coerce_event(
        self,
        item: dict,
        endpoint: str,
        currency: str,
        impact: str,
    ) -> CalendarEvent | None:
        event_date = self._stringify(item.get("date")) or self._stringify(item.get("scheduled_date"))
        if not event_date:
            return None
        symbol = self._stringify(item.get("symbol")) or self._stringify(item.get("ticker")) or "UNKNOWN"
        event_name = self._event_name(endpoint, symbol, item)
        return CalendarEvent(
            date=event_date,
            time_utc=self._normalize_time(item.get("time") or item.get("scheduled_time")),
            currency=currency,
            event_name=event_name,
            impact=impact,
            forecast=self._first_value(item, "estimate", "expected", "price_range", "amount"),
            previous=self._first_value(item, "previous", "close", "reference_price"),
            country=self._stringify(item.get("exchange")) or self._stringify(item.get("country")),
            source="Twelve Data",
        )

    def _event_name(self, endpoint: str, symbol: str, item: dict) -> str:
        label = {
            "earnings_calendar": "Earnings",
            "dividends_calendar": "Dividend",
            "splits_calendar": "Split",
            "ipo_calendar": "IPO",
        }.get(endpoint, "Calendar")
        company = self._stringify(item.get("name")) or self._stringify(item.get("company_name"))
        if company:
            return f"{symbol} {label} ({company})"
        return f"{symbol} {label}"

    def _normalize_time(self, value: object) -> str:
        text = self._stringify(value)
        if not text:
            return "00:00"
        if "T" in text:
            try:
                normalized = text.replace("Z", "+00:00")
                return datetime.fromisoformat(normalized).astimezone(UTC).strftime("%H:%M")
            except Exception:  # noqa: BLE001
                pass
        parts = text.split(":")
        if len(parts) >= 2 and all(part.isdigit() for part in parts[:2]):
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        return "00:00"

    def _first_value(self, item: dict, *keys: str) -> str | None:
        for key in keys:
            value = self._stringify(item.get(key))
            if value:
                return value
        return None

    def _stringify(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
