from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


BiasValue = Literal["Bullish", "Bearish", "Ranging"]
KeyLevelType = Literal["swing_high", "swing_low"]
TimeframeValue = Literal["H1", "M15"]


class Candle(BaseModel):
    pair: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class SwingPoint(BaseModel):
    index: int
    timestamp: datetime
    price: float
    kind: Literal["high", "low"]


class BiasResult(BaseModel):
    pair: str
    bias: BiasValue
    structure: str
    key_level: float
    key_level_type: KeyLevelType


class PriceRange(BaseModel):
    high: float
    low: float


class SetupScanResult(BaseModel):
    pair: str
    timeframe: TimeframeValue = "M15"
    fvg_detected: bool
    fvg_range: PriceRange | None = None
    fib_zone_hit: bool
    fib_level: float | None = None
    liquidity_sweep: bool
    sweep_level: float | None = None
    score: int = Field(ge=0, le=10)
    signals_summary: str
    direction: Literal["Long", "Short", "Neutral"] = "Neutral"
    surfaced: bool = False


class RiskCalculation(BaseModel):
    pair: str
    account_balance: float
    risk_pct: float
    risk_amount: float
    sl_pips: int
    lot_size: float
    tp_1r2: float
    tp_1r3: float
    rr_used: float


class AiAnalysisResult(BaseModel):
    provider: str
    model: str
    recommendation: Literal["Long", "Short", "Stand aside"]
    narrative: str
    caution_flags: list[str] = Field(default_factory=list)
    entry_zone: str | None = None
    sl_rationale: str | None = None


class ScanRunRecord(BaseModel):
    timestamp: datetime
    pairs_scanned: list[str]
    biases: list[BiasResult]
    setups: list[SetupScanResult]
    ai_analysis: list[AiAnalysisResult]
