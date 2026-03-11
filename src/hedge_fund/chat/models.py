from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from hedge_fund.domain.models import AiAnalysisResult, BiasResult, RiskCalculation, SetupScanResult


RouteIntent = Literal[
    "bias",
    "scan",
    "risk_size",
    "risk_exposure",
    "config_add_pair",
    "config_remove_pair",
    "config_show_pairs",
    "config_show_risk",
    "session_status",
    "general_question",
    "unknown",
]
CliPermissionMode = Literal["default", "plan", "accept_edits"]
ChatTurnRole = Literal["user", "assistant", "system"]


class RouteDecision(BaseModel):
    intent: RouteIntent
    scope: Literal["single", "all"] | None = None
    pair: str | None = None
    sl_pips: int | None = None
    risk_pct: float | None = None
    lot_size: float | None = None
    score_threshold: int | None = None
    session_name: str | None = None
    question: str | None = None
    missing_fields: list[str] = Field(default_factory=list)


class ChatTurn(BaseModel):
    role: ChatTurnRole
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    route: RouteDecision | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatContextSnapshot(BaseModel):
    active_pair: str | None = None
    last_pairs: list[str] = Field(default_factory=list)
    last_intent: str | None = None
    last_scan_pair: str | None = None
    last_bias_pairs: list[str] = Field(default_factory=list)
    last_setup_pairs: list[str] = Field(default_factory=list)
    pending_forget_matches: list[str] = Field(default_factory=list)
    recent_user_messages: list[str] = Field(default_factory=list)
    style_suggestion_pending: bool = False
    style_suggestion_made: bool = False
    suggested_experience_level: str | None = None
    suggestion_observed_terms: list[str] = Field(default_factory=list)


class StoredChatSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    ended_at: datetime | None = None
    summary: str | None = None
    model_override: str | None = None
    append_system_prompt: str | None = None
    permission_mode: CliPermissionMode = "default"
    turns: list[ChatTurn] = Field(default_factory=list)
    context: ChatContextSnapshot = Field(default_factory=ChatContextSnapshot)


class ChatSessionState(BaseModel):
    session: StoredChatSession
    max_context_turns: int = 10


class ReverseRiskCalculation(BaseModel):
    pair: str
    account_balance: float
    lot_size: float
    sl_pips: int
    risk_amount: float
    risk_pct: float
    current_price: float
    pip_value_per_standard_lot: float
    stop_distance: float


class ChatResponse(BaseModel):
    session_id: str
    route: RouteDecision | None = None
    message: str | None = None
    biases: list[BiasResult] = Field(default_factory=list)
    setups: list[SetupScanResult] = Field(default_factory=list)
    ai_analysis: list[AiAnalysisResult] = Field(default_factory=list)
    risk: RiskCalculation | None = None
    reverse_risk: ReverseRiskCalculation | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    should_exit: bool = False
