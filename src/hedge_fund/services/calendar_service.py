from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from hedge_fund.domain.exceptions import ConfigurationError
from hedge_fund.domain.models import CalendarResponse, CalendarWarning


class CalendarService:
    def __init__(self, provider) -> None:
        self.provider = provider

    def get_events(self, view: str, pairs: list[str]) -> CalendarResponse:
        if self.provider is None:
            return CalendarResponse(
                view=self._normalize_view(view),
                events=[],
                warnings=[CalendarWarning(pair="calendar", message="Prophet calendar is unavailable. Configure TWELVE_DATA_API_KEY.")],
                provider="twelvedata",
            )
        provider_name = getattr(self.provider, "name", "twelvedata")
        view = self._normalize_view(view)
        today = datetime.now(tz=UTC).date()
        if view == "week":
            start = today
            end = today + timedelta(days=6)
        else:
            start = today
            end = today
        try:
            events = self.provider.fetch_events(start, end)
        except ConfigurationError as exc:
            return CalendarResponse(
                view=view,
                events=[],
                warnings=[CalendarWarning(pair="calendar", message=f"Prophet calendar is unavailable: {exc}")],
                provider=provider_name,
            )
        except Exception as exc:  # noqa: BLE001
            return CalendarResponse(
                view=view,
                events=[],
                warnings=[CalendarWarning(pair="calendar", message=f"Prophet calendar failed to load: {exc}")],
                provider=provider_name,
            )
        warnings = self._build_warnings(events, pairs)
        return CalendarResponse(view=view, events=events, warnings=warnings, provider=provider_name)

    def _normalize_view(self, view: str) -> str:
        return "week" if view == "week" else "today"

    def _build_warnings(self, events, pairs: list[str]) -> list[CalendarWarning]:
        warnings: list[CalendarWarning] = []
        saw_twelvedata = False
        for event in events:
            if event.source == "Twelve Data":
                saw_twelvedata = True
                continue
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
        if saw_twelvedata:
            warnings.append(
                CalendarWarning(
                    pair="calendar",
                    message=(
                        "This calendar contains corporate events (earnings, dividends, splits, IPOs) from Twelve Data. "
                        "They do not map directly to forex pair-specific event risk."
                    ),
                )
            )
        return warnings

    def _affects_pair(self, currency: str, pair: str) -> bool:
        if pair == "XAUUSD":
            return currency == "USD"
        return currency in pair
