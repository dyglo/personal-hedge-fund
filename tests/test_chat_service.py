from pathlib import Path

from hedge_fund.chat.config_manager import ConfigManager
from hedge_fund.chat.models import ChatSessionState, ChatTurn, ReverseRiskCalculation, RouteDecision
from hedge_fund.chat.service import ChatService, ReverseRiskService
from hedge_fund.chat.session_store import SessionStore
from hedge_fund.config.settings import Settings
from hedge_fund.domain.models import BiasResult, RiskCalculation, SetupScanResult
from hedge_fund.services.scan_service import ScanResultBundle


class FakeLanguage:
    def __init__(self, routes) -> None:
        self.routes = list(routes)
        self.settings = Settings.load()

    def route(self, message: str, context: dict):
        return self.routes.pop(0)

    def answer_general(self, message: str, context: dict) -> str:
        return "General guidance."


class FakeScanService:
    def __init__(self) -> None:
        self.settings = Settings.load()
        self.bias_calls: list[list[str]] = []
        self.scan_calls: list[list[str]] = []

    def bias_only(self, pairs):
        self.bias_calls.append(list(pairs))
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
        self.scan_calls.append(list(pairs))
        return ScanResultBundle(
            biases=[
                BiasResult(
                    pair=pairs[0],
                    bias="Bullish",
                    structure="HH/HL",
                    key_level=1.1,
                    key_level_type="swing_low",
                )
            ],
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


class FakeReverseRiskService:
    def calculate(self, pair: str, lot_size: float, sl_pips: int) -> ReverseRiskCalculation:
        return ReverseRiskCalculation(
            pair=pair,
            account_balance=10000,
            lot_size=lot_size,
            sl_pips=sl_pips,
            risk_amount=50,
            risk_pct=0.5,
            current_price=2900,
            pip_value_per_standard_lot=1.0,
            stop_distance=0.1,
        )


def _service(tmp_path, routes):
    settings = Settings.load()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(Path("config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    session_store = SessionStore(tmp_path)
    service = ChatService(
        settings,
        FakeScanService(),
        FakeRiskService(),
        FakeReverseRiskService(),
        FakeLanguage(routes),
        ConfigManager(config_path),
        session_store,
    )
    state = session_store.create(
        max_context_turns=settings.chat.max_context_turns,
        permission_mode="default",
        model_override=None,
        append_system_prompt=None,
    )
    return service, state, session_store


def test_context_carries_pair_into_follow_up_scan(tmp_path) -> None:
    routes = [
        RouteDecision(intent="bias", pair="XAUUSD", scope="single"),
        RouteDecision(intent="scan", scope="single"),
    ]
    service, state, _ = _service(tmp_path, routes)

    first = service.process_message(state, "What's the bias on Gold?")
    second = service.process_message(state, "Any setups there?")

    assert first.biases[0].pair == "XAUUSD"
    assert second.setups[0].pair == "XAUUSD"


def test_clear_resets_context_but_preserves_history(tmp_path) -> None:
    routes = [RouteDecision(intent="bias", pair="EURUSD", scope="single")]
    service, state, session_store = _service(tmp_path, routes)

    service.process_message(state, "Bias on EURUSD")
    response = service.process_message(state, "/clear")
    loaded = session_store.load_latest()

    assert response.message == "Cleared active conversation context."
    assert loaded.session.context.active_pair is None
    assert len(loaded.session.turns) >= 4


def test_plan_permission_blocks_config_mutations(tmp_path) -> None:
    routes = [RouteDecision(intent="config_add_pair", pair="USDJPY")]
    service, state, _ = _service(tmp_path, routes)
    state.session.permission_mode = "plan"

    response = service.process_message(state, "Add USDJPY to my watchlist")

    assert "blocked" in response.message


def test_default_permission_prompts_before_config_write(tmp_path) -> None:
    routes = [RouteDecision(intent="config_add_pair", pair="USDJPY")]
    service, state, _ = _service(tmp_path, routes)
    prompts = []

    response = service.process_message(
        state,
        "Add USDJPY to my watchlist",
        authorize_mutation=lambda question: prompts.append(question) or False,
    )

    assert prompts == ["Update config.yaml for USDJPY?"]
    assert response.message == "Config change cancelled."


def test_accept_edits_allows_config_write_without_prompt(tmp_path) -> None:
    routes = [RouteDecision(intent="config_add_pair", pair="USDJPY")]
    service, state, _ = _service(tmp_path, routes)
    state.session.permission_mode = "accept_edits"

    response = service.process_message(state, "Add USDJPY to my watchlist")

    assert response.message == "Added USDJPY in config.yaml."
    assert "USDJPY" in service.config_manager.show_pairs()


def test_slash_commands_cover_help_permissions_and_exit(tmp_path) -> None:
    service, state, _ = _service(tmp_path, [])

    help_response = service.process_message(state, "/help")
    permission_response = service.process_message(state, "/permissions")
    exit_response = service.process_message(state, "/exit")

    assert "/status" in help_response.message
    assert permission_response.message == "Permission mode: default"
    assert exit_response.should_exit is True


class _MarketData:
    def get_price(self, pair: str):
        return 2900.0 if pair == "XAUUSD" else 1.25


class _Broker:
    def get_account_balance(self):
        return 10000.0

    def get_instrument_metadata(self, pair: str):
        return {"pipLocation": -4}


def test_reverse_risk_service_handles_xauusd() -> None:
    result = ReverseRiskService(_MarketData(), _Broker()).calculate("XAUUSD", 0.5, 10)

    assert result.risk_amount == 5.0
    assert result.risk_pct == 0.05
