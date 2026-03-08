from __future__ import annotations

import logging

from hedge_fund.domain.exceptions import ProviderError
from hedge_fund.domain.interfaces import AiProvider
from hedge_fund.domain.models import AiAnalysisResult


class AiOrchestrator:
    def __init__(
        self,
        provider_mode: str,
        gemini: AiProvider | None,
        openai_provider: AiProvider | None,
        logger: logging.Logger,
    ) -> None:
        self.provider_mode = provider_mode
        self.gemini = gemini
        self.openai_provider = openai_provider
        self.logger = logger

    def analyze(self, payload: dict) -> AiAnalysisResult | None:
        providers = self._providers()
        failures: list[str] = []
        for provider in providers:
            if provider is None:
                continue
            try:
                return provider.analyze(payload)
            except ProviderError as exc:
                failures.append(f"{provider.name}: {exc}")
                self.logger.warning("AI provider %s failed: %s", provider.name, exc)
        return self._fallback_result(failures)

    def _providers(self) -> list[AiProvider | None]:
        if self.provider_mode == "gemini":
            return [self.gemini]
        if self.provider_mode == "openai":
            return [self.openai_provider]
        return [self.gemini, self.openai_provider]

    def _fallback_result(self, failures: list[str]) -> AiAnalysisResult | None:
        if not failures:
            return None
        return AiAnalysisResult(
            provider="fallback",
            model="none",
            recommendation="Stand aside",
            narrative="AI analysis unavailable. Review the raw bias and setup output manually.",
            caution_flags=failures,
            entry_zone=None,
            sl_rationale="Fallback response due to provider errors.",
        )
