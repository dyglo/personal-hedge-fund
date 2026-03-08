from __future__ import annotations

from dataclasses import dataclass

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from hedge_fund.config.environment import EnvironmentSettings
from hedge_fund.config.settings import Settings
from hedge_fund.domain.exceptions import ProviderError


@dataclass
class AgentModelCandidate:
    provider: str
    model_name: str
    model: object


class AgentModelFactory:
    def __init__(self, settings: Settings, env: EnvironmentSettings, model_override: str | None = None) -> None:
        self.settings = settings
        self.env = env
        self.model_override = model_override

    def candidates(self) -> list[AgentModelCandidate]:
        requested = self._candidate_specs()
        candidates: list[AgentModelCandidate] = []
        failures: list[str] = []
        for provider, model_name in requested:
            try:
                candidates.append(
                    AgentModelCandidate(
                        provider=provider,
                        model_name=model_name,
                        model=self._build(provider, model_name),
                    )
                )
            except ProviderError as exc:
                failures.append(f"{provider}: {exc}")
        if candidates:
            return candidates
        raise ProviderError("; ".join(failures) or "No configured agent providers are available.")

    def _candidate_specs(self) -> list[tuple[str, str]]:
        if self.model_override:
            provider = "gemini" if "gemini" in self.model_override.lower() else "openai"
            return [(provider, self.model_override)]
        if self.settings.ai.provider == "gemini":
            return [("gemini", self.settings.ai.models.gemini)]
        if self.settings.ai.provider == "openai":
            return [("openai", self.settings.ai.models.openai)]
        return [
            ("gemini", self.settings.ai.models.gemini),
            ("openai", self.settings.ai.models.openai),
        ]

    def _build(self, provider: str, model_name: str) -> object:
        if provider == "gemini":
            if not self.env.gemini_api_key:
                raise ProviderError("Missing GEMINI_API_KEY")
            return ChatGoogleGenerativeAI(
                model=model_name,
                temperature=0,
                google_api_key=self.env.gemini_api_key,
            )

        if not self.env.openai_api_key:
            raise ProviderError("Missing OPENAI_API_KEY")
        return ChatOpenAI(
            model=model_name,
            temperature=0,
            api_key=self.env.openai_api_key,
        )
