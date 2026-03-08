from datetime import UTC, datetime, timedelta

from hedge_fund.config.settings import ScannerConfig, SessionsConfig, SessionWindowConfig
from hedge_fund.domain.models import Candle
from hedge_fund.services.setup_scanner import SetupScanner


def _candle(ts: datetime, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        pair="EURUSD",
        timeframe="M15",
        timestamp=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def test_setup_scanner_scores_two_signal_setup() -> None:
    sessions = SessionsConfig(
        asia=SessionWindowConfig(start="00:00", end="06:59"),
        london=SessionWindowConfig(start="07:00", end="11:59"),
        new_york=SessionWindowConfig(start="12:00", end="16:59"),
    )
    scanner = SetupScanner(
        ScannerConfig(minimum_score=6, fib_levels=[0.5, 0.618, 0.705, 0.786], minimum_fvg_pips=1),
        sessions,
    )
    start = datetime(2026, 3, 8, 7, 0, tzinfo=UTC)
    candles = [
        _candle(start + timedelta(minutes=15 * i), *values)
        for i, values in enumerate(
            [
                (1.1000, 1.1010, 1.0990, 1.1005),
                (1.1005, 1.1050, 1.1000, 1.1040),
                (1.1040, 1.1030, 1.0980, 1.0990),
                (1.0990, 1.1080, 1.1005, 1.1070),
                (1.1070, 1.1060, 1.1010, 1.1020),
                (1.1020, 1.1090, 1.1030, 1.1080),
                (1.1080, 1.1070, 1.1025, 1.1030),
                (1.1030, 1.1100, 1.1065, 1.1090),
                (1.1090, 1.1110, 1.1030, 1.1040),
                (1.1040, 1.1120, 1.1000, 1.1012),
                (1.1012, 1.1014, 1.0990, 1.1008),
                (1.1008, 1.1040, 1.1004, 1.1032),
            ]
        )
    ]

    result = scanner.scan("EURUSD", candles)

    assert result.fib_zone_hit is True
    assert result.liquidity_sweep is True
    assert result.score >= 6
    assert result.surfaced is True


def test_setup_scanner_detects_unfilled_fvg() -> None:
    sessions = SessionsConfig(
        asia=SessionWindowConfig(start="00:00", end="06:59"),
        london=SessionWindowConfig(start="07:00", end="11:59"),
        new_york=SessionWindowConfig(start="12:00", end="16:59"),
    )
    scanner = SetupScanner(
        ScannerConfig(minimum_score=6, fib_levels=[0.5, 0.618, 0.705, 0.786], minimum_fvg_pips=1),
        sessions,
    )
    start = datetime(2026, 3, 8, 7, 0, tzinfo=UTC)
    candles = [
        _candle(start + timedelta(minutes=15 * i), *values)
        for i, values in enumerate(
            [
                (1.1000, 1.1010, 1.0990, 1.1005),
                (1.1005, 1.1020, 1.1000, 1.1010),
                (1.1010, 1.1050, 1.1030, 1.1045),
                (1.1045, 1.1060, 1.1040, 1.1050),
            ]
        )
    ]

    result = scanner.scan("EURUSD", candles)

    assert result.fvg_detected is True
    assert result.fvg_range is not None
