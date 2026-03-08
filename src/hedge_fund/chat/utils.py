from __future__ import annotations

from datetime import UTC, datetime
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


def current_session_status(sessions: SessionsConfig, now: datetime | None = None) -> dict[str, str]:
    timestamp = (now or datetime.now(tz=UTC)).astimezone(UTC)
    current_time = timestamp.timetz()
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

    return {
        "current_session": "Closed",
        "opens_at": next_start,
        "closes_at": windows[next_name].end,
        "status": f"No configured session is open now. {next_name} opens at {next_start} UTC.",
    }


def pip_value_per_standard_lot(pair: str, current_price: float, metadata: dict) -> tuple[float, float]:
    calculator = RiskCalculator()
    if calculator._is_xau_pair(pair):  # noqa: SLF001
        return calculator.XAU_PIP_VALUE_PER_STANDARD_LOT_USD, calculator.XAU_PIP_SIZE

    pip_size = pip_size_from_metadata(metadata)
    quote_to_usd = 1.0 if pair.endswith("USD") else current_price
    return pip_size * 100000 * quote_to_usd, pip_size
