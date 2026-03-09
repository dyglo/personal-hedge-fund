from __future__ import annotations

import os

from pydantic import BaseModel


class EnvironmentSettings(BaseModel):
    oanda_api_key: str | None = None
    oanda_account_id: str | None = None
    alpha_vantage_api_key: str | None = None
    finnhub_api_key: str | None = None
    tradingeconomics_api_key: str | None = None
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    tavily_api_key: str | None = None
    database_url: str

    @staticmethod
    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @classmethod
    def load(cls) -> "EnvironmentSettings":
        return cls(
            oanda_api_key=cls._clean(os.getenv("OANDA_API_KEY")),
            oanda_account_id=cls._clean(os.getenv("OANDA_ACCOUNT_ID")),
            alpha_vantage_api_key=cls._clean(os.getenv("ALPHA_VANTAGE_API_KEY")),
            finnhub_api_key=cls._clean(os.getenv("FINNHUB_API_KEY")),
            tradingeconomics_api_key=cls._clean(os.getenv("TRADINGECONOMICS_API_KEY")),
            gemini_api_key=cls._clean(os.getenv("GEMINI_API_KEY")),
            openai_api_key=cls._clean(os.getenv("OPENAI_API_KEY")),
            tavily_api_key=cls._clean(os.getenv("TAVILY_API_KEY")),
            database_url=cls._clean(os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg://postgres:postgres@db:5432/hedge_fund",
            )) or "postgresql+psycopg://postgres:postgres@db:5432/hedge_fund",
        )
