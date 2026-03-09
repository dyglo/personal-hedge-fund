from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from hedge_fund.domain.models import CalendarResponse, CalendarWarning


class CalendarService:
    def __init__(self, provider) -> None:
        self.provider = provider

    def get_events(self, view: str, pairs: list[str]) -> CalendarResponse:
        today = datetime.now(tz=UTC).date()
        if view == "week":
            start = today
            end = today + timedelta(days=6)
        else:
            start = today
            end = today
            view = "today"
        events = self.provider.fetch_events(start, end)
        warnings = self._build_warnings(events, pairs)
        return CalendarResponse(view=view, events=events, warnings=warnings, provider="tradingeconomics")

    def _build_warnings(self, events, pairs: list[str]) -> list[CalendarWarning]:
        warnings: list[CalendarWarning] = []
        for event in events:
            if event.impact != "High":
                continue
            for pair in pairs:
                if self._affects_pair(event.currency, pair):
                    warnings.append(
                        CalendarWarning(
                            pair=pair,
                            message=(
                                f"{event.currency} {event.event_name} at {event.time_utc} UTC affects {pair}. "
                                "Avoid entering 15 minutes before and after this event."
                            ),
                        )
                    )
        return warnings

    def _affects_pair(self, currency: str, pair: str) -> bool:
        if pair == "XAUUSD":
            return currency == "USD"
        return currency in pair
