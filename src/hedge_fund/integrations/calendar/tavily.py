from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime

from hedge_fund.domain.exceptions import ConfigurationError, ProviderError
from hedge_fund.domain.models import CalendarEvent
from hedge_fund.integrations.search.tavily import TavilySearchClient


class TavilyCalendarClient:
    name = "tavily"

    def __init__(self, search_client: TavilySearchClient | None, logger: logging.Logger) -> None:
        self.search_client = search_client
        self.logger = logger

    def fetch_events(self, start: date, end: date) -> list[CalendarEvent]:
        if self.search_client is None:
            raise ConfigurationError("Missing Tavily search client for macro calendar requests.")
        try:
            payload = self.search_client.raw_search(self._query(start, end))
        except ProviderError as exc:
            raise ConfigurationError("Missing TAVILY_API_KEY for Tavily calendar requests.") from exc

        answer = payload.get("answer") if isinstance(payload, dict) else None
        rows = self._extract_rows(answer)
        events = [event for item in rows if (event := self._coerce_event(item)) is not None]
        events.sort(key=lambda item: f"{item.date}T{item.time_utc}")
        return events

    def _query(self, start: date, end: date) -> str:
        return (
            "Return a JSON object only. "
            f"Find macroeconomic calendar events between {start.isoformat()} and {end.isoformat()} UTC "
            "that materially affect forex pairs or gold. "
            "Focus on releases like CPI, inflation, NFP, FOMC, rate decisions, GDP, PMI, retail sales, employment, and central bank events. "
            "Use the schema {\"events\":[{\"date\":\"YYYY-MM-DD\",\"time_utc\":\"HH:MM\",\"currency\":\"USD\",\"event_name\":\"US CPI\",\"impact\":\"High|Medium|Low\",\"forecast\":null,\"previous\":null,\"country\":\"United States\"}]}. "
            "If a value is unknown, use null. Do not include equities earnings, dividends, splits, or IPOs. No prose."
        )

    def _extract_rows(self, answer: object) -> list[dict]:
        if not isinstance(answer, str):
            return []
        text = answer.strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except ValueError:
            match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
            if not match:
                self.logger.warning("Tavily calendar answer was not valid JSON")
                return []
            try:
                payload = json.loads(match.group(1))
            except ValueError:
                self.logger.warning("Tavily calendar answer contained unparseable JSON")
                return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("events"), list):
            return [item for item in payload["events"] if isinstance(item, dict)]
        return []

    def _coerce_event(self, item: dict) -> CalendarEvent | None:
        event_date = self._parse_date(item.get("date"))
        event_time = self._parse_time(item.get("time_utc") or item.get("time"))
        currency = self._stringify(item.get("currency"))
        event_name = self._stringify(item.get("event_name") or item.get("event"))
        if event_date is None or not currency or not event_name:
            return None
        return CalendarEvent(
            date=event_date.strftime("%Y-%m-%d"),
            time_utc=event_time,
            currency=currency.upper(),
            event_name=event_name,
            impact=self._impact(item.get("impact") or item.get("importance")),
            forecast=self._stringify(item.get("forecast")),
            previous=self._stringify(item.get("previous")),
            country=self._stringify(item.get("country")),
            source="Tavily",
        )

    def _parse_date(self, value: object) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)
        except ValueError:
            return None

    def _parse_time(self, value: object) -> str:
        text = self._stringify(value)
        if not text:
            return "00:00"
        match = re.match(r"^(\d{1,2}):(\d{2})", text)
        if not match:
            return "00:00"
        return f"{int(match.group(1)):02d}:{match.group(2)}"

    def _impact(self, value: object) -> str:
        text = (self._stringify(value) or "Medium").lower()
        if text in {"3", "high", "high impact"}:
            return "High"
        if text in {"1", "low", "low impact"}:
            return "Low"
        return "Medium"

    def _stringify(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
