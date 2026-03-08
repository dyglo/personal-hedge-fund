from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from hedge_fund.domain.interfaces import MarketDataProvider
from hedge_fund.domain.exceptions import ProviderError
from hedge_fund.domain.models import Candle
from hedge_fund.integrations.http import HttpExecutor
from hedge_fund.services.utils import normalize_pair, to_finnhub_symbol


class FinnhubAdapter(MarketDataProvider):
    name = "finnhub"
    base_url = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str | None, timeout_seconds: float, logger: logging.Logger) -> None:
        self.api_key = api_key
        self.logger = logger
        self.executor = HttpExecutor(timeout_seconds, logger)

    def get_candles(self, pair: str, timeframe: str, count: int) -> list[Candle]:
        if not self.api_key:
            raise ProviderError("Missing FINNHUB_API_KEY")
        resolution = "15" if timeframe == "M15" else "60"
        to_ts = int(datetime.now(tz=UTC).timestamp())
        lookback = 60 * count * (15 if timeframe == "M15" else 60)
        from_ts = to_ts - lookback
        response = self.executor.request(
            lambda: httpx.get(
                f"{self.base_url}/forex/candle",
                params={
                    "symbol": to_finnhub_symbol(pair),
                    "resolution": resolution,
                    "from": from_ts,
                    "to": to_ts,
                    "token": self.api_key,
                },
                timeout=self.executor.timeout,
            ),
            f"Finnhub candles for {pair}",
        )
        payload = response.json()
        return [
            Candle(
                pair=normalize_pair(pair),
                timeframe=timeframe,
                timestamp=datetime.fromtimestamp(ts, tz=UTC),
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=float(volume),
            )
            for ts, open_, high, low, close, volume in zip(
                payload.get("t", []),
                payload.get("o", []),
                payload.get("h", []),
                payload.get("l", []),
                payload.get("c", []),
                payload.get("v", []),
            )
        ][-count:]

    def get_price(self, pair: str) -> float:
        if not self.api_key:
            raise ProviderError("Missing FINNHUB_API_KEY")
        response = self.executor.request(
            lambda: httpx.get(
                f"{self.base_url}/quote",
                params={"symbol": to_finnhub_symbol(pair), "token": self.api_key},
                timeout=self.executor.timeout,
            ),
            f"Finnhub quote for {pair}",
        )
        return float(response.json()["c"])
