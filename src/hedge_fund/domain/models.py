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


class RuleCheck(BaseModel):
    rule: str
    passed: bool
    detail: str


class TradePlanOutput(BaseModel):
    pair: str
    direction: Literal["LONG", "SHORT"]
    entry: float
    stop_loss: float
    sl_distance: float
    tp1: float
    tp2: float
    rr_ratio_tp1: str = "1:2"
    rr_ratio_tp2: str = "1:3"
    lot_size: float
    risk_amount: float
    risk_pct: float
    tp2_reward: float
    setup_type: str
    session: str
    confluence_score: int = Field(ge=0, le=10)
    rule_checks: list[RuleCheck]
    narrative: str
    formatted_block: str


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


class SessionSummary(BaseModel):
    id: str
    started_at: datetime
    ended_at: datetime | None = None
    summary: str | None = None
    turn_count: int = 0


class SessionResumePayload(BaseModel):
    id: str
    messages: list[dict]
    summary: str | None = None
    recap: str | None = None


class CalendarEvent(BaseModel):
    date: str
    time_utc: str
    currency: str
    event_name: str
    impact: Literal["High", "Medium", "Low"]
    forecast: str | None = None
    previous: str | None = None
    country: str | None = None
    source: str | None = None


class CalendarWarning(BaseModel):
    pair: str
    message: str


class CalendarResponse(BaseModel):
    view: Literal["today", "week"]
    events: list[CalendarEvent] = Field(default_factory=list)
    warnings: list[CalendarWarning] = Field(default_factory=list)
    provider: str
