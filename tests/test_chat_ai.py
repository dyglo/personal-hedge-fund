import logging

import pytest

from hedge_fund.chat.ai import ChatLanguageService
from hedge_fund.config.environment import EnvironmentSettings
from hedge_fund.config.settings import Settings


@pytest.mark.parametrize(
    ("payload", "expected_intent", "expected_pair"),
    [
        ({"intent": "bias", "pair": "Gold"}, "bias", "XAUUSD"),
        ({"intent": "scan", "pair": "GBP/USD", "scope": "single"}, "scan", "GBPUSD"),
        ({"intent": "risk_size", "pair": "EURUSD", "sl_pips": 20, "risk_pct": 1}, "risk_size", "EURUSD"),
        ({"intent": "risk_exposure", "pair": "XAU", "sl_pips": 10, "lot_size": 0.5}, "risk_exposure", "XAUUSD"),
        ({"intent": "config_add_pair", "pair": "Yen"}, "config_add_pair", "USDJPY"),
        ({"intent": "session_status", "session_name": "London"}, "session_status", None),
        ({"intent": "general_question", "question": "Should I be trading right now?"}, "general_question", None),
    ],
)
def test_router_validates_provider_json(monkeypatch, payload, expected_intent, expected_pair) -> None:
    settings = Settings.load()
    env = EnvironmentSettings(database_url="sqlite://", openai_api_key="key")
    service = ChatLanguageService(settings, env, logging.getLogger("test"))

    monkeypatch.setattr(service, "_providers", lambda: [("openai", "gpt-5-mini")])
    monkeypatch.setattr(service, "_route_with_openai", lambda message, context, model: payload)

    decision = service.route("test", {"active_pair": None})

    assert decision.intent == expected_intent
    assert decision.pair == expected_pair


def test_router_uses_active_pair_context_when_pair_missing(monkeypatch) -> None:
    settings = Settings.load()
    env = EnvironmentSettings(database_url="sqlite://", openai_api_key="key")
    service = ChatLanguageService(settings, env, logging.getLogger("test"))

    monkeypatch.setattr(service, "_providers", lambda: [("openai", "gpt-5-mini")])
    monkeypatch.setattr(
        service,
        "_route_with_openai",
        lambda message, context, model: {"intent": "scan", "scope": "single"},
    )

    decision = service.route("Any setups there?", {"active_pair": "XAUUSD"})

    assert decision.intent == "scan"
    assert decision.pair == "XAUUSD"
    assert decision.scope == "single"


def test_heuristic_router_does_not_treat_plain_watching_statement_as_watchlist_query() -> None:
    settings = Settings.load()
    env = EnvironmentSettings(database_url="sqlite://", openai_api_key="key")
    service = ChatLanguageService(settings, env, logging.getLogger("test"))

    decision = service._heuristic_route("I'm watching EURUSD today.", {"active_pair": None})  # noqa: SLF001

    assert decision.intent != "config_show_pairs"
