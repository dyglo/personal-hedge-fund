from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from hedge_fund.config.settings import SessionsConfig
from hedge_fund.services.risk_calculator import RiskCalculator
from hedge_fund.services.utils import normalize_pair as normalize_v1_pair, parse_session_time, pip_size_from_metadata


PAIR_ALIASES: dict[str, str] = {
    "GOLD": "XAUUSD",
    "XAU": "XAUUSD",
    "XAUUSD": "XAUUSD",
    "EURO": "EURUSD",
    "EURUSD": "EURUSD",
    "CABLE": "GBPUSD",
    "POUND": "GBPUSD",
    "GBPUSD": "GBPUSD",
    "YEN": "USDJPY",
    "USDJPY": "USDJPY",
}


def normalize_pair_alias(value: str | None) -> str | None:
    if not value:
        return None
    token = normalize_v1_pair(value.replace(" ", ""))
    if token in PAIR_ALIASES:
        return PAIR_ALIASES[token]
    if len(token) == 6 and token.isalpha():
        return token
    return None


def chat_root(cwd: str | Path) -> Path:
    return Path(cwd) / ".hedge_fund"


def _format_time_until(delta: timedelta) -> str:
    total_seconds = max(int(delta.total_seconds()), 0)
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def _market_closed_response(timestamp: datetime, sessions: SessionsConfig, next_open: datetime) -> dict[str, str]:
    time_until_open = _format_time_until(next_open - timestamp)
    return {
        "current_session": "Closed",
        "opens_at": next_open.strftime("%H:%M"),
        "closes_at": sessions.asia.end,
        "time_until_open": _format_time_until(next_open - timestamp),
        "status": (
            f"Market closed. Asia opens at {next_open:%H:%M} UTC "
            f"(in {_format_time_until(next_open - timestamp)})."
        ),
        "time_until_open": time_until_open,
        "status": f"Market closed. Asia opens at {next_open:%H:%M} UTC (in {time_until_open}).",
    }


def _closed_response(timestamp: datetime, next_name: str, next_start: str, next_end: str) -> dict[str, str]:
    next_open = datetime.combine(timestamp.date(), parse_session_time(next_start))
    if next_open <= timestamp:
        next_open += timedelta(days=1)

    time_until_open = _format_time_until(next_open - timestamp)
    return {
        "current_session": "Closed",
        "opens_at": next_start,
        "closes_at": next_end,
        "time_until_open": time_until_open,
        "status": f"No configured session is open now. {next_name} opens at {next_start} UTC (in {time_until_open}).",
    }


def current_session_status(sessions: SessionsConfig, now: datetime | None = None) -> dict[str, str]:
    timestamp = (now or datetime.now(tz=UTC)).astimezone(UTC)
    current_time = timestamp.timetz()
    weekday = timestamp.weekday()
    sunday_open = time(hour=22, minute=0, tzinfo=UTC)

    if weekday == 4 and current_time >= sunday_open:
        next_open = datetime.combine(timestamp.date() + timedelta(days=2), sunday_open)
        return _market_closed_response(timestamp, sessions, next_open)

    if weekday == 5:
        next_open = datetime.combine(timestamp.date() + timedelta(days=1), sunday_open)
        return _market_closed_response(timestamp, sessions, next_open)

    if weekday == 6 and current_time < sunday_open:
        next_open = datetime.combine(timestamp.date(), sunday_open)
        return _market_closed_response(timestamp, sessions, next_open)
    market_open = time(hour=22, minute=0, tzinfo=UTC)

    if weekday == 4 and current_time >= market_open:
        next_open = datetime.combine(timestamp.date() + timedelta(days=2), market_open)
        return _market_closed_response(timestamp, sessions, next_open)

    if weekday == 5:
        next_open = datetime.combine(timestamp.date() + timedelta(days=1), market_open)
        return _market_closed_response(timestamp, sessions, next_open)

    if weekday == 6 and current_time < market_open:
        next_open = datetime.combine(timestamp.date(), market_open)
        return _market_closed_response(timestamp, sessions, next_open)

    windows = {
        "Asia": sessions.asia,
        "London": sessions.london,
        "New York": sessions.new_york,
    }

    active_name = "Closed"
    next_name = "Asia"
    next_start = sessions.asia.start

    for name, window in windows.items():
        start = parse_session_time(window.start)
        end = parse_session_time(window.end)
        if start <= current_time <= end:
            active_name = name
        if current_time < start and next_name == "Asia":
            next_name = name
            next_start = window.start
            break

    if active_name != "Closed":
        active_window = windows[active_name]
        return {
            "current_session": active_name,
            "opens_at": active_window.start,
            "closes_at": active_window.end,
            "status": f"{active_name} is open now.",
        }

    return _closed_response(timestamp, next_name, next_start, windows[next_name].end)


def pip_value_per_standard_lot(pair: str, current_price: float, metadata: dict) -> tuple[float, float]:
    calculator = RiskCalculator()
    if calculator._is_xau_pair(pair):  # noqa: SLF001
        return calculator.XAU_PIP_VALUE_PER_STANDARD_LOT_USD, calculator.XAU_PIP_SIZE

    pip_size = pip_size_from_metadata(metadata)
    quote_to_usd = 1.0 if pair.endswith("USD") else current_price
    return pip_size * 100000 * quote_to_usd, pip_size
