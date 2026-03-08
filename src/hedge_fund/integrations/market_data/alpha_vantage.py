from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from hedge_fund.domain.interfaces import MarketDataProvider
from hedge_fund.domain.exceptions import ProviderError
from hedge_fund.domain.models import Candle
from hedge_fund.integrations.http import HttpExecutor
from hedge_fund.services.utils import normalize_pair


class AlphaVantageAdapter(MarketDataProvider):
    name = "alpha_vantage"
    base_url = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str | None, timeout_seconds: float, logger: logging.Logger) -> None:
        self.api_key = api_key
        self.logger = logger
        self.executor = HttpExecutor(timeout_seconds, logger)

    def get_candles(self, pair: str, timeframe: str, count: int) -> list[Candle]:
        if not self.api_key:
            raise ProviderError("Missing ALPHA_VANTAGE_API_KEY")
        base, quote = normalize_pair(pair)[:3], normalize_pair(pair)[3:]
        interval = "15min" if timeframe == "M15" else "60min"
        response = self.executor.request(
            lambda: httpx.get(
                self.base_url,
                params={
                    "function": "FX_INTRADAY",
                    "from_symbol": base,
                    "to_symbol": quote,
                    "interval": interval,
                    "outputsize": "compact",
                    "apikey": self.api_key,
                },
                timeout=self.executor.timeout,
            ),
            f"Alpha Vantage candles for {pair}",
        )
        data = response.json()
        series_key = next(key for key in data.keys() if key.startswith("Time Series"))
        items = list(data[series_key].items())[:count]
        candles = []
        for timestamp, values in reversed(items):
            candles.append(
                Candle(
                    pair=normalize_pair(pair),
                    timeframe=timeframe,
                    timestamp=datetime.fromisoformat(timestamp).replace(tzinfo=UTC),
                    open=float(values["1. open"]),
                    high=float(values["2. high"]),
                    low=float(values["3. low"]),
                    close=float(values["4. close"]),
                )
            )
        return candles

    def get_price(self, pair: str) -> float:
        candles = self.get_candles(pair, "M15", 1)
        return candles[-1].close
