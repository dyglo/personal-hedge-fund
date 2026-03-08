from __future__ import annotations

from hedge_fund.domain.models import BiasResult, Candle
from hedge_fund.services.utils import detect_swings


class MarketBiasEngine:
    def analyze(self, pair: str, candles: list[Candle]) -> BiasResult:
        swings = detect_swings(candles, window=1)
        highs = [s for s in swings if s.kind == "high"]
        lows = [s for s in swings if s.kind == "low"]

        if len(highs) >= 2 and len(lows) >= 2:
            last_high, prev_high = highs[-1], highs[-2]
            last_low, prev_low = lows[-1], lows[-2]
            if last_high.price > prev_high.price and last_low.price > prev_low.price:
                return BiasResult(
                    pair=pair,
                    bias="Bullish",
                    structure="HH/HL",
                    key_level=last_low.price,
                    key_level_type="swing_low",
                )
            if last_high.price < prev_high.price and last_low.price < prev_low.price:
                return BiasResult(
                    pair=pair,
                    bias="Bearish",
                    structure="LH/LL",
                    key_level=last_high.price,
                    key_level_type="swing_high",
                )

        last_candle = candles[-1]
        return BiasResult(
            pair=pair,
            bias="Ranging",
            structure="Range",
            key_level=last_candle.close,
            key_level_type="swing_high",
        )
