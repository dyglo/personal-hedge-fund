from __future__ import annotations

from abc import ABC, abstractmethod

from hedge_fund.domain.models import AiAnalysisResult, Candle


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def get_candles(self, pair: str, timeframe: str, count: int) -> list[Candle]:
        raise NotImplementedError

    @abstractmethod
    def get_price(self, pair: str) -> float:
        raise NotImplementedError


class BrokerProvider(ABC):
    @abstractmethod
    def get_account_balance(self, account_id: str) -> float:
        raise NotImplementedError

    @abstractmethod
    def get_instrument_metadata(self, pair: str, account_id: str | None = None) -> dict:
        raise NotImplementedError


class AiProvider(ABC):
    name: str

    @abstractmethod
    def analyze(self, payload: dict) -> AiAnalysisResult:
        raise NotImplementedError
