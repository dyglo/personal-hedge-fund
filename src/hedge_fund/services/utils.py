from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Iterable

from hedge_fund.domain.models import Candle, SwingPoint


def normalize_pair(pair: str) -> str:
    return pair.replace("_", "").replace("/", "").replace(":", "").upper()


def to_oanda_instrument(pair: str) -> str:
    normalized = normalize_pair(pair)
    return f"{normalized[:3]}_{normalized[3:]}"


def to_finnhub_symbol(pair: str) -> str:
    return f"OANDA:{to_oanda_instrument(pair)}"


def parse_session_time(value: str) -> time:
    hours, minutes = value.split(":")
    return time(hour=int(hours), minute=int(minutes), tzinfo=UTC)


def within_session(ts: datetime, start: str, end: str) -> bool:
    current = ts.astimezone(UTC).timetz()
    start_time = parse_session_time(start)
    end_time = parse_session_time(end)
    return start_time <= current <= end_time


def pip_size_from_metadata(metadata: dict) -> float:
    pip_location = metadata.get("pipLocation", -4)
    return 10 ** int(pip_location)


def detect_swings(candles: list[Candle], window: int = 2) -> list[SwingPoint]:
    swings: list[SwingPoint] = []
    if len(candles) < (window * 2) + 1:
        return swings

    for idx in range(window, len(candles) - window):
        current = candles[idx]
        left = candles[idx - window:idx]
        right = candles[idx + 1: idx + window + 1]
        if all(current.high > candle.high for candle in left + right):
            swings.append(
                SwingPoint(
                    index=idx,
                    timestamp=current.timestamp,
                    price=current.high,
                    kind="high",
                )
            )
        if all(current.low < candle.low for candle in left + right):
            swings.append(
                SwingPoint(
                    index=idx,
                    timestamp=current.timestamp,
                    price=current.low,
                    kind="low",
                )
            )
    return swings


def most_recent(items: Iterable[SwingPoint], kind: str) -> SwingPoint | None:
    filtered = [item for item in items if item.kind == kind]
    return filtered[-1] if filtered else None
