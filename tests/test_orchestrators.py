import logging

import pytest

from hedge_fund.domain.exceptions import DataUnavailableError, ProviderError
from hedge_fund.integrations.market_data.orchestrator import MarketDataOrchestrator


class FailingProvider:
    name = "fail"

    def get_candles(self, pair: str, timeframe: str, count: int):
        raise ProviderError("failed")

    def get_price(self, pair: str):
        raise ProviderError("failed")


class WorkingProvider:
    name = "ok"

    def get_candles(self, pair: str, timeframe: str, count: int):
        return ["candles"]

    def get_price(self, pair: str):
        return 1.23


def test_market_data_orchestrator_falls_back() -> None:
    orchestrator = MarketDataOrchestrator([FailingProvider(), WorkingProvider()], logging.getLogger("test"))

    assert orchestrator.get_price("EURUSD") == 1.23


def test_market_data_orchestrator_raises_when_all_fail() -> None:
    orchestrator = MarketDataOrchestrator([FailingProvider()], logging.getLogger("test"))

    with pytest.raises(DataUnavailableError):
        orchestrator.get_price("EURUSD")
