import json
import logging
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from hedge_fund.chat.agent_runtime import AgentArtifacts, AgentRuntime
import hedge_fund.chat.agent_runtime as agent_runtime_module
from hedge_fund.chat.agent_models import AgentModelFactory
from hedge_fund.chat.agent_tools import AgentToolContext
from hedge_fund.chat.config_manager import ConfigManager
from hedge_fund.chat.models import ChatTurn
from hedge_fund.chat.service import ChatService, ReverseRiskService
from hedge_fund.chat.session_store import SessionStore
from hedge_fund.chat.scratchpad import ScratchpadManager
from hedge_fund.config.environment import EnvironmentSettings
from hedge_fund.config.settings import Settings
from hedge_fund.domain.models import BiasResult, RiskCalculation, SetupScanResult
from hedge_fund.services.scan_service import ScanResultBundle


class FakeLanguage:
    def __init__(self) -> None:
        self.settings = Settings.load()


class FakeScanService:
    def __init__(self, fail_bias: bool = False) -> None:
        self.settings = Settings.load()
        self.fail_bias = fail_bias

    def bias_only(self, pairs):
        if self.fail_bias:
            raise ValueError("bias unavailable")
        return [
            BiasResult(
                pair=pairs[0],
                bias="Bullish",
                structure="HH/HL",
                key_level=1.1,
                key_level_type="swing_low",
            )
        ]

    def scan(self, pairs):
        return ScanResultBundle(
            biases=self.bias_only(pairs),
            setups=[
                SetupScanResult(
                    pair=pairs[0],
                    fvg_detected=True,
                    fvg_range=None,
                    fib_zone_hit=True,
                    fib_level=0.618,
                    liquidity_sweep=True,
                    sweep_level=1.1,
                    score=8,
                    signals_summary="FVG, Fib",
                    direction="Long",
                    surfaced=True,
                )
            ],
            ai_analysis=[],
        )


class FakeRiskService:
    def calculate(self, pair: str, risk_pct: float, sl_pips: int) -> RiskCalculation:
        return RiskCalculation(
            pair=pair,
            account_balance=10000,
            risk_pct=risk_pct,
            risk_amount=100,
            sl_pips=sl_pips,
            lot_size=0.5,
            tp_1r2=1.2,
            tp_1r3=1.3,
            rr_used=3,
        )


class FakeSearchClient:
    def search(self, query: str):
        return {
            "query": query,
            "summary": "Gold is reacting to dollar weakness.",
            "results": [
                {"title": "Gold climbs", "url": "https://example.com/gold", "snippet": "Gold rose after weaker data."}
            ],
        }


class FakeMemoryRepository:
    def __init__(self) -> None:
        self.content = "- Avoid GBPUSD during BOE week"

    def get_content(self) -> str:
        return self.content

    def add_rule(self, rule: str, max_characters: int):
        self.content = f"{self.content}\n- {rule}"
        return self.content, True

    def forget_rule(self, rule: str) -> str:
        self.content = ""
        return self.content


class FakeCalendarPayload:
    def __init__(self) -> None:
        self.events = [type("Event", (), {"event_name": "CPI", "currency": "USD", "time_utc": "13:30"})()]
        self.warnings = [type("Warning", (), {"pair": "XAUUSD", "message": "USD CPI affects XAUUSD."})()]

    def model_dump(self, mode="json"):
        return {
            "view": "today",
            "provider": "fake",
            "events": [{"event_name": "CPI", "currency": "USD", "time_utc": "13:30"}],
            "warnings": [{"pair": "XAUUSD", "message": "USD CPI affects XAUUSD."}],
        }


class FakeCalendarService:
    def get_events(self, view: str, pairs: list[str]):
        return FakeCalendarPayload()


class _MarketData:
    def get_price(self, pair: str):
        return 2900.0 if pair == "XAUUSD" else 1.25


class _Broker:
    def get_account_balance(self):
        return 10000.0

    def get_instrument_metadata(self, pair: str):
        return {"pipLocation": -4}


def _config_manager(tmp_path):
    config_path = tmp_path / "config.yaml"
    repo_config = Path(__file__).resolve().parents[1] / "config.yaml"
    config_path.write_text(repo_config.read_text(encoding="utf-8"), encoding="utf-8")
    return ConfigManager(config_path)


def _state(tmp_path):
    store = SessionStore(tmp_path)
    state = store.create(
        max_context_turns=Settings.load().chat.max_context_turns,
        permission_mode="accept_edits",
        model_override=None,
        append_system_prompt=None,
    )
    return store, state


def test_agent_tool_returns_bias_payload_and_logs_scratchpad(tmp_path) -> None:
    store, state = _state(tmp_path)
    scratchpad = ScratchpadManager(tmp_path, Settings.load().agent).for_session(state.session.session_id)
    artifacts = AgentArtifacts()
    context = AgentToolContext(
        settings=Settings.load(),
        state=state,
        scan_service=FakeScanService(),
        risk_service=FakeRiskService(),
        reverse_risk_service=ReverseRiskService(_MarketData(), _Broker()),
        config_manager=_config_manager(tmp_path),
        search_client=FakeSearchClient(),
        scratchpad=scratchpad,
        artifacts=artifacts,
        memory_repository=FakeMemoryRepository(),
        calendar_service=FakeCalendarService(),
    )

    tool = next(item for item in context.build_tools() if item.name == "get_market_bias")
    payload = json.loads(tool.invoke({"pair": "Gold"}))

    assert payload["ok"] is True
    assert payload["biases"][0]["pair"] == "XAUUSD"
    entries = scratchpad.path.read_text(encoding="utf-8").splitlines()
    assert any('"type": "tool_call"' in line for line in entries)
    assert any('"type": "tool_result"' in line for line in entries)
    assert state.session.context.active_pair == "XAUUSD"


def test_agent_selects_web_search_for_news_queries(tmp_path, monkeypatch) -> None:
    service, state = _agent_service(tmp_path)

    class FakeAgent:
        def __init__(self, tools):
            self.tools = {tool.name: tool for tool in tools}

        def stream(self, payload, config=None, stream_mode=None):
            query = "gold news today"
            yield (
                "updates",
                {
                    "model": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[{"name": "web_search", "args": {"query": query}, "id": "call-1", "type": "tool_call"}],
                            )
                        ]
                    }
                },
            )
            result = self.tools["web_search"].invoke({"query": query})
            yield ("updates", {"tools": {"messages": [ToolMessage(content=result, tool_call_id="call-1")]}})
            yield ("updates", {"model": {"messages": [AIMessage(content="Gold is being driven by macro headlines.")]}})

    monkeypatch.setattr("hedge_fund.chat.agent_runtime.AgentModelFactory.candidates", lambda self: [type("C", (), {"provider": "openai", "model_name": "gpt-5-mini", "model": object()})()])
    monkeypatch.setattr("hedge_fund.chat.agent_runtime.create_agent", lambda model, tools, system_prompt: FakeAgent(tools))

    response = service.process_message(state, "Any major news on Gold today?")

    assert "macro headlines" in response.message
    assert response.metadata["web_search"]["query"] == "gold news today"


def test_agent_selects_bias_tool_for_bias_queries(tmp_path, monkeypatch) -> None:
    service, state = _agent_service(tmp_path)

    class FakeAgent:
        def __init__(self, tools):
            self.tools = {tool.name: tool for tool in tools}

        def stream(self, payload, config=None, stream_mode=None):
            yield (
                "updates",
                {
                    "model": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[{"name": "get_market_bias", "args": {"pair": "Gold"}, "id": "call-1", "type": "tool_call"}],
                            )
                        ]
                    }
                },
            )
            result = self.tools["get_market_bias"].invoke({"pair": "Gold"})
            yield ("updates", {"tools": {"messages": [ToolMessage(content=result, tool_call_id="call-1")]}})
            yield ("updates", {"model": {"messages": [AIMessage(content="Gold bias is bullish.")]}})

    monkeypatch.setattr("hedge_fund.chat.agent_runtime.AgentModelFactory.candidates", lambda self: [type("C", (), {"provider": "openai", "model_name": "gpt-5-mini", "model": object()})()])
    monkeypatch.setattr("hedge_fund.chat.agent_runtime.create_agent", lambda model, tools, system_prompt: FakeAgent(tools))

    response = service.process_message(state, "What's the bias on Gold?")

    assert response.biases[0].pair == "XAUUSD"
    assert "bullish" in response.message.lower()


def test_agent_returns_partial_result_when_max_steps_are_exceeded(tmp_path, monkeypatch) -> None:
    runtime = AgentRuntime(Settings.load(), EnvironmentSettings(database_url="sqlite://", openai_api_key="key"), logging.getLogger("test"))
    scratchpad = ScratchpadManager(tmp_path, Settings.load().agent).for_session("session123")
    artifacts = AgentArtifacts(summaries=["Bias: XAUUSD Bullish"])

    class RecursingAgent:
        def stream(self, payload, config=None, stream_mode=None):
            raise agent_runtime_module.GraphRecursionError("recursion")

    monkeypatch.setattr("hedge_fund.chat.agent_runtime.AgentModelFactory.candidates", lambda self: [type("C", (), {"provider": "openai", "model_name": "gpt-5-mini", "model": object()})()])
    monkeypatch.setattr("hedge_fund.chat.agent_runtime.create_agent", lambda model, tools, system_prompt: RecursingAgent())

    result = runtime.run("Need help", "system", [], scratchpad, artifacts)

    assert result.metadata["partial"] is True
    assert "step limit" in result.message


def test_agent_handles_tool_failure_without_crashing(tmp_path, monkeypatch) -> None:
    service, state = _agent_service(tmp_path, fail_bias=True)

    class FakeAgent:
        def __init__(self, tools):
            self.tools = {tool.name: tool for tool in tools}

        def stream(self, payload, config=None, stream_mode=None):
            yield (
                "updates",
                {
                    "model": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[{"name": "get_market_bias", "args": {"pair": "Gold"}, "id": "call-1", "type": "tool_call"}],
                            )
                        ]
                    }
                },
            )
            result = self.tools["get_market_bias"].invoke({"pair": "Gold"})
            yield ("updates", {"tools": {"messages": [ToolMessage(content=result, tool_call_id="call-1")]}})
            yield ("updates", {"model": {"messages": [AIMessage(content="Bias tool failed, but the session is still live.")]}})

    monkeypatch.setattr("hedge_fund.chat.agent_runtime.AgentModelFactory.candidates", lambda self: [type("C", (), {"provider": "openai", "model_name": "gpt-5-mini", "model": object()})()])
    monkeypatch.setattr("hedge_fund.chat.agent_runtime.create_agent", lambda model, tools, system_prompt: FakeAgent(tools))

    response = service.process_message(state, "What's the bias on Gold?")

    assert "still live" in response.message
    scratchpad_path = tmp_path / ".prophet" / "scratchpad" / f"{state.session.session_id}.jsonl"
    assert '"ok": false' in scratchpad_path.read_text(encoding="utf-8").lower()


def _agent_service(tmp_path, fail_bias: bool = False):
    settings = Settings.load()
    env = EnvironmentSettings(database_url="sqlite://", openai_api_key="key")
    config_manager = _config_manager(tmp_path)
    session_store, state = _state(tmp_path)
    service = ChatService(
        settings,
        FakeScanService(fail_bias=fail_bias),
        FakeRiskService(),
        ReverseRiskService(_MarketData(), _Broker()),
        FakeLanguage(),
        config_manager,
        session_store,
        agent_runtime=AgentRuntime(settings, env, logging.getLogger("test")),
        scratchpad_manager=ScratchpadManager(tmp_path, settings.agent),
        search_client=FakeSearchClient(),
        memory_repository=FakeMemoryRepository(),
        calendar_service=FakeCalendarService(),
    )
    return service, state


def test_agent_ignores_stream_updates_without_messages(tmp_path, monkeypatch) -> None:
    runtime = AgentRuntime(Settings.load(), EnvironmentSettings(database_url="sqlite://", openai_api_key="key"), logging.getLogger("test"))
    scratchpad = ScratchpadManager(tmp_path, Settings.load().agent).for_session("session123")
    artifacts = AgentArtifacts(summaries=["Bias: XAUUSD Bullish"])

    class SparseAgent:
        def stream(self, payload, config=None, stream_mode=None):
            yield ("updates", {"metadata": {"step": {"ignored": True}}})
            yield ("updates", {"model": {"messages": [AIMessage(content="Final answer.") ]}})

    monkeypatch.setattr("hedge_fund.chat.agent_runtime.AgentModelFactory.candidates", lambda self: [type("C", (), {"provider": "openai", "model_name": "gpt-5-mini", "model": object()})()])
    monkeypatch.setattr("hedge_fund.chat.agent_runtime.create_agent", lambda model, tools, system_prompt: SparseAgent())

    result = runtime.run("Need help", "system", [], scratchpad, artifacts)

    assert result.message == "Final answer."


def test_agent_model_factory_passes_api_keys_without_mutating_environment(monkeypatch) -> None:
    captured = {}

    class FakeGemini:
        def __init__(self, **kwargs) -> None:
            captured["gemini"] = kwargs

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            captured["openai"] = kwargs

    settings = Settings.load()
    env = EnvironmentSettings(
        database_url="sqlite://",
        gemini_api_key="gem-key",
        openai_api_key="open-key",
    )

    monkeypatch.setattr("hedge_fund.chat.agent_models.ChatGoogleGenerativeAI", FakeGemini)
    monkeypatch.setattr("hedge_fund.chat.agent_models.ChatOpenAI", FakeOpenAI)

    factory = AgentModelFactory(settings, env)
    factory._build("gemini", settings.ai.models.gemini)
    factory._build("openai", settings.ai.models.openai)

    assert captured["gemini"]["google_api_key"] == "gem-key"
    assert captured["openai"]["api_key"] == "open-key"


def test_agent_runtime_receives_recent_history_messages(tmp_path, monkeypatch) -> None:
    service, state = _agent_service(tmp_path)
    state.session.turns.extend(
        [
            ChatTurn(role="user", content="What is the current trend of EURUSD?"),
            ChatTurn(role="assistant", content="EURUSD is bullish."),
        ]
    )
    captured = {}

    class HistoryAgent:
        def stream(self, payload, config=None, stream_mode=None):
            captured["messages"] = payload["messages"]
            yield ("updates", {"model": {"messages": [AIMessage(content="Follow-up understood.")]}})

    monkeypatch.setattr("hedge_fund.chat.agent_runtime.AgentModelFactory.candidates", lambda self: [type("C", (), {"provider": "openai", "model_name": "gpt-5-mini", "model": object()})()])
    monkeypatch.setattr("hedge_fund.chat.agent_runtime.create_agent", lambda model, tools, system_prompt: HistoryAgent())

    response = service.process_message(state, "Should I enter long here?")

    assert response.message == "Follow-up understood."
    assert captured["messages"][0]["content"] == "What is the current trend of EURUSD?"
    assert captured["messages"][-1]["content"] == "Should I enter long here?"


def test_agent_tool_can_rank_watchlist_pairs(tmp_path) -> None:
    store, state = _state(tmp_path)
    scratchpad = ScratchpadManager(tmp_path, Settings.load().agent).for_session(state.session.session_id)
    artifacts = AgentArtifacts()
    context = AgentToolContext(
        settings=Settings.load(),
        state=state,
        scan_service=FakeScanService(),
        risk_service=FakeRiskService(),
        reverse_risk_service=ReverseRiskService(_MarketData(), _Broker()),
        config_manager=_config_manager(tmp_path),
        search_client=FakeSearchClient(),
        scratchpad=scratchpad,
        artifacts=artifacts,
        memory_repository=FakeMemoryRepository(),
        calendar_service=FakeCalendarService(),
    )

    tool = next(item for item in context.build_tools() if item.name == "rank_watchlist_pairs")
    payload = json.loads(tool.invoke({}))

    assert payload["ok"] is True
    assert payload["ranking"][0]["pair"] == "XAUUSD"
    assert artifacts.metadata["ranking"]


def test_agent_tool_can_access_memory_and_calendar(tmp_path) -> None:
    store, state = _state(tmp_path)
    scratchpad = ScratchpadManager(tmp_path, Settings.load().agent).for_session(state.session.session_id)
    artifacts = AgentArtifacts()
    context = AgentToolContext(
        settings=Settings.load(),
        state=state,
        scan_service=FakeScanService(),
        risk_service=FakeRiskService(),
        reverse_risk_service=ReverseRiskService(_MarketData(), _Broker()),
        config_manager=_config_manager(tmp_path),
        search_client=FakeSearchClient(),
        scratchpad=scratchpad,
        artifacts=artifacts,
        memory_repository=FakeMemoryRepository(),
        calendar_service=FakeCalendarService(),
    )

    memory_tool = next(item for item in context.build_tools() if item.name == "show_memory")
    calendar_tool = next(item for item in context.build_tools() if item.name == "get_economic_calendar")

    memory_payload = json.loads(memory_tool.invoke({}))
    calendar_payload = json.loads(calendar_tool.invoke({"view": "today"}))

    assert "BOE" in memory_payload["content"]
    assert calendar_payload["calendar"]["events"][0]["event_name"] == "CPI"
