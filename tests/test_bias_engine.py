from datetime import UTC, datetime, timedelta

from hedge_fund.services.bias_engine import MarketBiasEngine
from hedge_fund.domain.models import Candle


def _candle(ts: datetime, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        pair="EURUSD",
        timeframe="H1",
        timestamp=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def test_bias_engine_detects_bullish_structure() -> None:
    start = datetime(2026, 3, 8, tzinfo=UTC)
    candles = [
        _candle(start + timedelta(hours=i), *values)
        for i, values in enumerate(
            [
                (1.0, 1.01, 0.99, 1.0),
                (1.0, 1.03, 1.0, 1.02),
                (1.02, 1.02, 0.98, 0.99),
                (0.99, 1.05, 1.0, 1.04),
                (1.04, 1.03, 1.0, 1.01),
                (1.01, 1.06, 1.02, 1.05),
                (1.05, 1.04, 1.01, 1.03),
                (1.03, 1.08, 1.03, 1.07),
                (1.07, 1.06, 1.03, 1.04),
            ]
        )
    ]

    result = MarketBiasEngine().analyze("EURUSD", candles)

    assert result.bias == "Bullish"
    assert result.structure == "HH/HL"
    assert result.key_level_type == "swing_low"
