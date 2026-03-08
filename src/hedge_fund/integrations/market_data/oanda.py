from __future__ import annotations

import logging
from datetime import datetime

import httpx

from hedge_fund.domain.interfaces import BrokerProvider, MarketDataProvider
from hedge_fund.domain.exceptions import ProviderError
from hedge_fund.domain.models import Candle
from hedge_fund.integrations.http import HttpExecutor
from hedge_fund.services.utils import normalize_pair, to_oanda_instrument


class OandaAdapter(MarketDataProvider, BrokerProvider):
    name = "oanda"
    base_url = "https://api-fxpractice.oanda.com/v3"

    def __init__(
        self,
        api_key: str | None,
        account_id: str | None,
        timeout_seconds: float,
        logger: logging.Logger,
    ) -> None:
        self.api_key = api_key
        self.account_id = account_id
        self.logger = logger
        self.executor = HttpExecutor(timeout_seconds, logger)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError("Missing OANDA_API_KEY")
        return {"Authorization": f"Bearer {self.api_key}"}

    def get_candles(self, pair: str, timeframe: str, count: int) -> list[Candle]:
        instrument = to_oanda_instrument(pair)
        response = self.executor.request(
            lambda: httpx.get(
                f"{self.base_url}/instruments/{instrument}/candles",
                headers=self._headers(),
                params={"price": "M", "granularity": timeframe, "count": count},
                timeout=self.executor.timeout,
            ),
            f"OANDA candles for {pair}",
        )
        payload = response.json()
        candles: list[Candle] = []
        for item in payload.get("candles", []):
            if not item.get("complete", True):
                continue
            mid = item["mid"]
            candles.append(
                Candle(
                    pair=normalize_pair(pair),
                    timeframe=timeframe,
                    timestamp=datetime.fromisoformat(item["time"].replace("Z", "+00:00")),
                    open=float(mid["o"]),
                    high=float(mid["h"]),
                    low=float(mid["l"]),
                    close=float(mid["c"]),
                    volume=float(item.get("volume", 0)),
                )
            )
        return candles

    def get_price(self, pair: str) -> float:
        instrument = to_oanda_instrument(pair)
        account_id = self.account_id or ""
        response = self.executor.request(
            lambda: httpx.get(
                f"{self.base_url}/accounts/{account_id}/pricing",
                headers=self._headers(),
                params={"instruments": instrument},
                timeout=self.executor.timeout,
            ),
            f"OANDA price for {pair}",
        )
        prices = response.json().get("prices", [])
        return float(prices[0]["closeoutAsk"])

    def get_account_balance(self, account_id: str) -> float:
        if not account_id:
            raise ProviderError("Missing OANDA_ACCOUNT_ID")
        response = self.executor.request(
            lambda: httpx.get(
                f"{self.base_url}/accounts/{account_id}/summary",
                headers=self._headers(),
                timeout=self.executor.timeout,
            ),
            "OANDA account summary",
        )
        return float(response.json()["account"]["balance"])

    def get_instrument_metadata(self, pair: str, account_id: str | None = None) -> dict:
        instrument = to_oanda_instrument(pair)
        path_account_id = account_id or self.account_id or ""
        response = self.executor.request(
            lambda: httpx.get(
                f"{self.base_url}/accounts/{path_account_id}/instruments",
                headers=self._headers(),
                params={"instruments": instrument},
                timeout=self.executor.timeout,
            ),
            f"OANDA instrument metadata for {pair}",
        )
        instruments = response.json().get("instruments", [])
        if instruments:
            return instruments[0]
        return {"name": instrument, "pipLocation": -4, "displayPrecision": 5}
