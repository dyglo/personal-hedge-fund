import logging

import pytest

from hedge_fund.domain.exceptions import ProviderError
from hedge_fund.domain.models import AiAnalysisResult
from hedge_fund.chat.ai import ChatLanguageService
from hedge_fund.config.environment import EnvironmentSettings
from hedge_fund.config.settings import Settings
from hedge_fund.integrations.ai.gemini import GeminiProvider
from hedge_fund.integrations.ai.openai_provider import OpenAIProvider
from hedge_fund.integrations.ai.orchestrator import AiOrchestrator


class _FakeGeminiResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self.text}]}}]}


class _FakeOpenAIResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


def test_gemini_strips_markdown_code_fences(monkeypatch) -> None:
    provider = GeminiProvider("key", "gemini-3-flash-preview", 5, logging.getLogger("test"))
    fenced = """```json
{"recommendation":"Long","narrative":"Valid setup","caution_flags":[],"entry_zone":"1.10-1.11","sl_rationale":"Below sweep low"}
```"""

    monkeypatch.setattr(
        "hedge_fund.integrations.ai.gemini.httpx.post",
        lambda *args, **kwargs: _FakeGeminiResponse(200, fenced),
    )

    result = provider.analyze({"foo": "bar"})

    assert result.recommendation == "Long"
    assert result.narrative == "Valid setup"


def test_gemini_extracts_json_from_prose_wrapped_response(monkeypatch) -> None:
    provider = GeminiProvider("key", "gemini-3-flash-preview", 5, logging.getLogger("test"))
    prose = """Here is the analysis:
{"recommendation":"Short","narrative":"Sell the sweep","caution_flags":["Bias conflict"],"entry_zone":"1.3390-1.3380","sl_rationale":"Above sweep high"}
Use caution."""

    monkeypatch.setattr(
        "hedge_fund.integrations.ai.gemini.httpx.post",
        lambda *args, **kwargs: _FakeGeminiResponse(200, prose),
    )

    result = provider.analyze({"bias": {"pair": "EURUSD"}})

    assert result.recommendation == "Short"
    assert result.caution_flags == ["Bias conflict"]


def test_gemini_raises_provider_error_on_empty_body(monkeypatch) -> None:
    provider = GeminiProvider("key", "gemini-3-flash-preview", 5, logging.getLogger("test"))

    monkeypatch.setattr(
        "hedge_fund.integrations.ai.gemini.httpx.post",
        lambda *args, **kwargs: _FakeGeminiResponse(200, ""),
    )

    with pytest.raises(ProviderError):
        provider.analyze({"foo": "bar"})


def test_openai_raises_provider_error_on_empty_body() -> None:
    provider = OpenAIProvider("key", "gpt-4.1-mini", 5, logging.getLogger("test"))
    provider.client.responses.create = lambda **kwargs: _FakeOpenAIResponse("")  # type: ignore[method-assign]

    with pytest.raises(ProviderError):
        provider.analyze({"foo": "bar"})


class _FailingProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    def analyze(self, payload: dict) -> AiAnalysisResult:
        raise ProviderError(f"{self.name} failed")


class _WorkingProvider:
    name = "openai"

    def analyze(self, payload: dict) -> AiAnalysisResult:
        return AiAnalysisResult(
            provider="openai",
            model="gpt-4.1-mini",
            recommendation="Long",
            narrative="Recovered with OpenAI fallback",
            caution_flags=[],
            entry_zone="1.10-1.11",
            sl_rationale="Below sweep low",
        )


def test_orchestrator_retries_openai_after_gemini_failure() -> None:
    orchestrator = AiOrchestrator(
        "auto",
        _FailingProvider("gemini"),
        _WorkingProvider(),
        logging.getLogger("test"),
    )

    result = orchestrator.analyze({"foo": "bar"})

    assert result is not None
    assert result.provider == "openai"
    assert result.model == "gpt-4.1-mini"


def test_orchestrator_returns_single_fallback_after_all_failures() -> None:
    orchestrator = AiOrchestrator(
        "auto",
        _FailingProvider("gemini"),
        _FailingProvider("openai"),
        logging.getLogger("test"),
    )

    result = orchestrator.analyze({"foo": "bar"})

    assert result is not None
    assert result.provider == "fallback"
    assert result.recommendation == "Stand aside"


def test_chat_language_service_treats_auto_override_as_provider_fallback() -> None:
    settings = Settings.load()
    service = ChatLanguageService(
        settings,
        EnvironmentSettings(database_url="sqlite://", openai_api_key="key"),
        logging.getLogger("test"),
        model_override="auto",
    )

    assert service._providers() == [
        ("gemini", settings.ai.models.gemini),
        ("openai", settings.ai.models.openai),
    ]
