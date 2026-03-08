from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging

from hedge_fund.config.settings import Settings
from hedge_fund.domain.exceptions import PersistenceError
from hedge_fund.domain.models import AiAnalysisResult, BiasResult, SetupScanResult
from hedge_fund.integrations.ai.orchestrator import AiOrchestrator
from hedge_fund.integrations.market_data.orchestrator import BrokerOrchestrator, MarketDataOrchestrator
from hedge_fund.services.ai_analyst import AiAnalyst
from hedge_fund.services.bias_engine import MarketBiasEngine
from hedge_fund.services.risk_calculator import RiskCalculator
from hedge_fund.services.setup_scanner import SetupScanner
from hedge_fund.services.utils import normalize_pair
from hedge_fund.storage.repository import ScanPersistencePayload, ScanRepository


@dataclass
class ScanResultBundle:
    biases: list[BiasResult]
    setups: list[SetupScanResult]
    ai_analysis: list[AiAnalysisResult]


class ScanService:
    def __init__(
        self,
        settings: Settings,
        market_data: MarketDataOrchestrator,
        ai: AiOrchestrator,
        repository: ScanRepository,
        logger: logging.Logger,
    ) -> None:
        self.settings = settings
        self.market_data = market_data
        self.repository = repository
        self.logger = logger
        self.bias_engine = MarketBiasEngine()
        self.setup_scanner = SetupScanner(settings.trading.scanner, settings.trading.sessions)
        self.ai_analyst = AiAnalyst(ai)

    def scan(self, pairs: list[str]) -> ScanResultBundle:
        biases: list[BiasResult] = []
        setups: list[SetupScanResult] = []
        ai_analysis: list[AiAnalysisResult] = []

        for pair in pairs:
            bias_candles = self.market_data.get_candles(pair, self.settings.trading.timeframes.bias, 120)
            entry_candles = self.market_data.get_candles(pair, self.settings.trading.timeframes.entry, 160)
            bias = self.bias_engine.analyze(pair, bias_candles)
            setup = self.setup_scanner.scan(pair, entry_candles)
            biases.append(bias)
            setups.append(setup)
            if setup.surfaced:
                analysis = self.ai_analyst.analyze(
                    bias,
                    setup,
                    self.settings.trading.sessions.model_dump(),
                )
                if analysis:
                    ai_analysis.append(analysis)

        self._persist(pairs, biases, setups, ai_analysis)
        return ScanResultBundle(biases=biases, setups=setups, ai_analysis=ai_analysis)

    def bias_only(self, pairs: list[str]) -> list[BiasResult]:
        results = []
        for pair in pairs:
            candles = self.market_data.get_candles(pair, self.settings.trading.timeframes.bias, 120)
            results.append(self.bias_engine.analyze(pair, candles))
        return results

    def _persist(
        self,
        pairs: list[str],
        biases: list[BiasResult],
        setups: list[SetupScanResult],
        ai_analysis: list[AiAnalysisResult],
    ) -> None:
        payload = ScanPersistencePayload(
            timestamp=datetime.now(tz=UTC),
            pairs_scanned=pairs,
            config_snapshot={
                "settings": self.settings.model_dump(),
            },
            biases=biases,
            setups=setups,
            ai_output=ai_analysis,
            success=True,
        )
        try:
            self.repository.save_scan_run(payload)
        except PersistenceError:
            self.logger.warning("Scan result was shown but not persisted")


class RiskService:
    def __init__(
        self,
        market_data: MarketDataOrchestrator,
        broker: BrokerOrchestrator,
    ) -> None:
        self.market_data = market_data
        self.broker = broker
        self.calculator = RiskCalculator()

    def calculate(self, pair: str, risk_pct: float, sl_pips: int):
        normalized_pair = normalize_pair(pair)
        balance = self.broker.get_account_balance()
        price = self.market_data.get_price(normalized_pair)
        metadata = {}
        if normalized_pair != "XAUUSD":
            metadata = self.broker.get_instrument_metadata(normalized_pair)
        return self.calculator.calculate(normalized_pair, balance, risk_pct, sl_pips, price, metadata)
