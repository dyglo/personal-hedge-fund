from __future__ import annotations

from dataclasses import dataclass

from hedge_fund.config.settings import ScannerConfig, SessionsConfig
from hedge_fund.domain.models import Candle, PriceRange, SetupScanResult
from hedge_fund.services.utils import detect_swings, within_session


@dataclass
class LiquiditySweepSignal:
    detected: bool
    level: float | None = None
    direction: str = "Neutral"


class SetupScanner:
    def __init__(self, scanner_config: ScannerConfig, sessions: SessionsConfig) -> None:
        self.scanner_config = scanner_config
        self.sessions = sessions

    def scan(self, pair: str, candles: list[Candle]) -> SetupScanResult:
        fvg = self._detect_fvg(candles)
        fib_level, fib_direction = self._detect_fib_zone(candles)
        sweep = self._detect_liquidity_sweep(candles)

        signals = []
        direction = "Neutral"
        if fvg:
            signals.append("FVG")
            direction = "Long" if candles[-3].high < candles[-1].low else "Short"
        if fib_level is not None:
            signals.append("Fib")
            direction = direction if direction != "Neutral" else fib_direction
        if sweep.detected:
            signals.append("Liquidity sweep")
            direction = direction if direction != "Neutral" else sweep.direction

        score = self._score(signals)
        surfaced = score >= self.scanner_config.minimum_score
        return SetupScanResult(
            pair=pair,
            fvg_detected=fvg is not None,
            fvg_range=fvg,
            fib_zone_hit=fib_level is not None,
            fib_level=fib_level,
            liquidity_sweep=sweep.detected,
            sweep_level=sweep.level,
            score=score,
            signals_summary=", ".join(signals) if signals else "No qualifying confluence",
            direction=direction if surfaced else "Neutral",
            surfaced=surfaced,
        )

    def _detect_fvg(self, candles: list[Candle]) -> PriceRange | None:
        for idx in range(2, len(candles)):
            c1, _, c3 = candles[idx - 2], candles[idx - 1], candles[idx]
            bullish_gap = c1.high < c3.low
            bearish_gap = c1.low > c3.high
            if not bullish_gap and not bearish_gap:
                continue
            gap_high = c3.low if bullish_gap else c1.low
            gap_low = c1.high if bullish_gap else c3.high
            gap_size = abs(gap_high - gap_low)
            if gap_size < self.scanner_config.minimum_fvg_pips * 0.0001:
                continue
            future = candles[idx + 1:]
            filled = any(item.low <= gap_low and item.high >= gap_high for item in future)
            if not filled:
                return PriceRange(high=max(gap_high, gap_low), low=min(gap_high, gap_low))
        return None

    def _detect_fib_zone(self, candles: list[Candle]) -> tuple[float | None, str]:
        swings = detect_swings(candles)
        highs = [s for s in swings if s.kind == "high"]
        lows = [s for s in swings if s.kind == "low"]
        if not highs or not lows:
            return None, "Neutral"
        last_high = highs[-1]
        last_low = lows[-1]
        direction = "Short" if last_high.index > last_low.index else "Long"
        swing_high = last_high.price
        swing_low = last_low.price
        price = candles[-1].close
        move = swing_high - swing_low
        for level in self.scanner_config.fib_levels:
            fib_price = swing_high - (move * level)
            tolerance = max(move * 0.02, 0.0002)
            if abs(price - fib_price) <= tolerance:
                return level, direction
        return None, direction

    def _detect_liquidity_sweep(self, candles: list[Candle]) -> LiquiditySweepSignal:
        recent = candles[-12:]
        for candle in recent[-4:]:
            if within_session(candle.timestamp, self.sessions.asia.start, self.sessions.asia.end) or within_session(
                candle.timestamp, self.sessions.london.start, self.sessions.london.end
            ) or within_session(candle.timestamp, self.sessions.new_york.start, self.sessions.new_york.end):
                prior = [item for item in recent if item.timestamp < candle.timestamp]
                if not prior:
                    continue
                prior_high = max(item.high for item in prior)
                prior_low = min(item.low for item in prior)
                if candle.high > prior_high and candle.close < prior_high:
                    return LiquiditySweepSignal(True, prior_high, "Short")
                if candle.low < prior_low and candle.close > prior_low:
                    return LiquiditySweepSignal(True, prior_low, "Long")
        for idx in range(1, len(recent)):
            previous, current = recent[idx - 1], recent[idx]
            if abs(previous.high - current.high) <= 0.0002 and current.close < previous.high:
                return LiquiditySweepSignal(True, previous.high, "Short")
            if abs(previous.low - current.low) <= 0.0002 and current.close > previous.low:
                return LiquiditySweepSignal(True, previous.low, "Long")
        return LiquiditySweepSignal(False)

    def _score(self, signals: list[str]) -> int:
        unique = set(signals)
        if len(unique) == 3:
            return 9
        if unique == {"FVG", "Fib"}:
            return 7
        if unique == {"FVG", "Liquidity sweep"}:
            return 8
        if unique == {"Fib", "Liquidity sweep"}:
            return 6
        return 0
