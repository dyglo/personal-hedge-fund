from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from hedge_fund.domain.exceptions import ConfigurationError


class AppConfig(BaseModel):
    log_level: str = "INFO"
    log_file: str = "logs/app.log"


class AiModelsConfig(BaseModel):
    gemini: str
    openai: str


class AiConfig(BaseModel):
    provider: Literal["gemini", "openai", "auto"]
    models: AiModelsConfig


class TimeframesConfig(BaseModel):
    bias: str
    entry: str


class RiskDefaultsConfig(BaseModel):
    default_risk_pct: float = Field(gt=0)
    minimum_rr: float = Field(ge=1)
    preferred_rr: float = Field(ge=1)


class SessionWindowConfig(BaseModel):
    start: str
    end: str


class SessionsConfig(BaseModel):
    asia: SessionWindowConfig
    london: SessionWindowConfig
    new_york: SessionWindowConfig


class ScannerConfig(BaseModel):
    minimum_score: int = Field(ge=0, le=10)
    fib_levels: list[float]
    minimum_fvg_pips: float = Field(gt=0)


class TradingConfig(BaseModel):
    pairs: list[str]
    timeframes: TimeframesConfig
    risk: RiskDefaultsConfig
    sessions: SessionsConfig
    scanner: ScannerConfig


class DataConfig(BaseModel):
    source_priority: list[str]
    request_timeout_seconds: float = Field(gt=0)


class ChatConfig(BaseModel):
    max_context_turns: int = Field(ge=1, le=50)
    response_timeout_seconds: float = Field(gt=0)
    show_intent_debug: bool = False


class SessionPersistenceConfig(BaseModel):
    max_stored: int = Field(default=30, ge=1, le=200)
    auto_summary: bool = True


class ContextRetentionConfig(BaseModel):
    max_history_turns: int = Field(default=20, ge=1, le=100)


class StreamingConfig(BaseModel):
    enabled: bool = True
    fallback_on_error: bool = True


class MemoryConfig(BaseModel):
    max_characters: int = Field(default=2000, ge=100, le=10000)


class CalendarConfig(BaseModel):
    provider: Literal["auto", "twelvedata", "tavily"] = "auto"
    default_view: Literal["today", "week"] = "today"


class AgentConfig(BaseModel):
    max_steps: int = Field(default=6, ge=1, le=20)
    show_thinking: bool = False
    scratchpad_enabled: bool = True
    scratchpad_path: str = ".prophet/scratchpad/"


class SearchConfig(BaseModel):
    provider: Literal["tavily"] = "tavily"
    max_results: int = Field(default=5, ge=1, le=10)
    search_depth: Literal["basic", "advanced"] = "basic"


class Settings(BaseModel):
    app: AppConfig
    ai: AiConfig
    trading: TradingConfig
    data: DataConfig
    chat: ChatConfig
    sessions: SessionPersistenceConfig = Field(default_factory=SessionPersistenceConfig)
    context: ContextRetentionConfig = Field(default_factory=ContextRetentionConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    calendar: CalendarConfig = Field(default_factory=CalendarConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> "Settings":
        file_path = Path(path)
        try:
            content = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
            return cls.model_validate(content)
        except FileNotFoundError as exc:
            raise ConfigurationError(f"Missing config file: {file_path}") from exc
        except ValidationError as exc:
            raise ConfigurationError(f"Invalid config.yaml: {exc}") from exc
