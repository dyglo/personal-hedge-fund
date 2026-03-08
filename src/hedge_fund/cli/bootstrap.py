from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy.orm import Session

from hedge_fund.config.environment import EnvironmentSettings
from hedge_fund.config.logging import configure_logging
from hedge_fund.config.settings import Settings
from hedge_fund.integrations.ai.gemini import GeminiProvider
from hedge_fund.integrations.ai.openai_provider import OpenAIProvider
from hedge_fund.integrations.ai.orchestrator import AiOrchestrator
from hedge_fund.integrations.market_data.alpha_vantage import AlphaVantageAdapter
from hedge_fund.integrations.market_data.finnhub import FinnhubAdapter
from hedge_fund.integrations.market_data.oanda import OandaAdapter
from hedge_fund.integrations.market_data.orchestrator import BrokerOrchestrator, MarketDataOrchestrator
from hedge_fund.integrations.search import TavilySearchClient
from hedge_fund.storage.migrations import run_migrations
from hedge_fund.storage.repository import ScanRepository
from hedge_fund.storage.session import build_session_factory


class ApplicationContext:
    def __init__(self) -> None:
        self.settings = Settings.load()
        self.env = EnvironmentSettings.load()
        self.logger = configure_logging(self.settings.app.log_level, self.settings.app.log_file)
        run_migrations(self.env.database_url)
        self.session_factory = build_session_factory(self.env.database_url)

        oanda = OandaAdapter(
            self.env.oanda_api_key,
            self.env.oanda_account_id,
            self.settings.data.request_timeout_seconds,
            self.logger,
        )
        alpha = AlphaVantageAdapter(
            self.env.alpha_vantage_api_key,
            self.settings.data.request_timeout_seconds,
            self.logger,
        )
        finnhub = FinnhubAdapter(self.env.finnhub_api_key, self.settings.data.request_timeout_seconds, self.logger)
        providers_by_name = {"oanda": oanda, "alpha_vantage": alpha, "finnhub": finnhub}
        ordered_providers = [providers_by_name[name] for name in self.settings.data.source_priority]

        self.market_data = MarketDataOrchestrator(ordered_providers, self.logger)
        self.broker = BrokerOrchestrator(oanda, self.env.oanda_account_id)
        self.ai = AiOrchestrator(
            self.settings.ai.provider,
            GeminiProvider(
                self.env.gemini_api_key,
                self.settings.ai.models.gemini,
                self.settings.data.request_timeout_seconds,
                self.logger,
            )
            if self.env.gemini_api_key
            else None,
            OpenAIProvider(
                self.env.openai_api_key,
                self.settings.ai.models.openai,
                self.settings.data.request_timeout_seconds,
                self.logger,
            )
            if self.env.openai_api_key
            else None,
            self.logger,
        )
        self.web_search = TavilySearchClient(
            self.env.tavily_api_key,
            self.settings.search.max_results,
            self.settings.search.search_depth,
        )

    def create_session(self) -> Session:
        return self.session_factory()

    def create_repository(self, session: Session) -> ScanRepository:
        return ScanRepository(session, self.logger)

    @contextmanager
    def session_scope(self):
        session = self.create_session()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
