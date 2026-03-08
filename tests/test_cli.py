from datetime import UTC, datetime
import logging
from contextlib import contextmanager

from typer.testing import CliRunner

from hedge_fund.cli.app import app
from hedge_fund.domain.models import AiAnalysisResult, BiasResult, SetupScanResult
from hedge_fund.services.scan_service import ScanResultBundle


runner = CliRunner()


class FakeScanService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def scan(self, pairs):
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
            ai_analysis=[
                AiAnalysisResult(
                    provider="openai",
                    model="gpt-5-mini",
                    recommendation="Long",
                    narrative="Trade with trend",
                    caution_flags=["Session overlap"],
                    entry_zone="1.10-1.11",
                    sl_rationale="Below sweep low",
                )
            ],
        )

    def bias_only(self, pairs):
        return [
            BiasResult(
                pair=pairs[0],
                bias="Bullish",
                structure="HH/HL",
                key_level=1.1,
                key_level_type="swing_low",
            )
        ]


class FakeRiskService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def calculate(self, pair, risk, sl):
        from hedge_fund.domain.models import RiskCalculation

        return RiskCalculation(
            pair=pair,
            account_balance=10000,
            risk_pct=risk,
            risk_amount=100,
            sl_pips=sl,
            lot_size=0.5,
            tp_1r2=1.2,
            tp_1r3=1.3,
            rr_used=3,
        )


class FakeContext:
    def __init__(self) -> None:
        self.settings = type("Settings", (), {"trading": type("Trading", (), {"pairs": ["EURUSD"]})()})()
        self.market_data = None
        self.ai = None
        self.logger = logging.getLogger("test")
        self.broker = None

    def create_session(self):
        return object()

    def create_repository(self, session):
        return None

    @contextmanager
    def session_scope(self):
        yield object()


def test_scan_command_renders_tables(monkeypatch) -> None:
    monkeypatch.setattr("hedge_fund.cli.app.ApplicationContext", FakeContext)
    monkeypatch.setattr("hedge_fund.cli.app.ScanService", FakeScanService)

    result = runner.invoke(app, ["scan", "--pair", "EURUSD"])

    assert result.exit_code == 0
    assert "Market Bias" in result.stdout
    assert "Setup Scanner" in result.stdout


def test_risk_command_renders_output(monkeypatch) -> None:
    monkeypatch.setattr("hedge_fund.cli.app.ApplicationContext", FakeContext)
    monkeypatch.setattr("hedge_fund.cli.app.RiskService", FakeRiskService)

    result = runner.invoke(app, ["risk", "--pair", "EURUSD", "--sl", "20", "--risk", "1"])

    assert result.exit_code == 0
    assert "Risk Calculation" in result.stdout
