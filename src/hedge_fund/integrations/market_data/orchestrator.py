from __future__ import annotations

import logging
from collections.abc import Iterable

from hedge_fund.domain.exceptions import DataUnavailableError, ProviderError
from hedge_fund.domain.interfaces import BrokerProvider, MarketDataProvider


class MarketDataOrchestrator:
    def __init__(self, providers: Iterable[MarketDataProvider], logger: logging.Logger) -> None:
        self.providers = list(providers)
        self.logger = logger

    def get_candles(self, pair: str, timeframe: str, count: int):
        return self._try("get_candles", pair, timeframe, count)

    def get_price(self, pair: str):
        return self._try("get_price", pair)

    def _try(self, method: str, *args):
        failures: list[str] = []
        for provider in self.providers:
            try:
                return getattr(provider, method)(*args)
            except ProviderError as exc:
                failures.append(f"{provider.name}: {exc}")
                self.logger.warning("Provider %s failed for %s", provider.name, method)
        raise DataUnavailableError("; ".join(failures))


class BrokerOrchestrator:
    def __init__(self, broker: BrokerProvider, account_id: str | None) -> None:
        self.broker = broker
        self.account_id = account_id

    def get_account_balance(self) -> float:
        return self.broker.get_account_balance(self.account_id or "")

    def get_instrument_metadata(self, pair: str) -> dict:
        return self.broker.get_instrument_metadata(pair, self.account_id)
