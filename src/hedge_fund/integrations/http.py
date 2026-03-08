from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from hedge_fund.domain.exceptions import ProviderError


class HttpExecutor:
    def __init__(self, timeout_seconds: float, logger: logging.Logger) -> None:
        self.timeout = httpx.Timeout(timeout_seconds)
        self.logger = logger

    def request(self, fn: Callable[[], httpx.Response], context: str) -> httpx.Response:
        try:
            response = fn()
            response.raise_for_status()
            return response
        except (httpx.HTTPError, ValueError) as exc:
            self.logger.exception("Provider call failed: %s", context)
            raise ProviderError(context) from exc
