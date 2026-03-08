from __future__ import annotations

import json
import logging

from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, OpenAI

from hedge_fund.domain.exceptions import ProviderError
from hedge_fund.domain.interfaces import AiProvider
from hedge_fund.domain.models import AiAnalysisResult


class OpenAIProvider(AiProvider):
    name = "openai"

    def __init__(self, api_key: str | None, model: str, timeout_seconds: float, logger: logging.Logger) -> None:
        self.api_key = api_key
        self.model = model
        self.logger = logger
        self.client = OpenAI(api_key=api_key, timeout=timeout_seconds)

    def analyze(self, payload: dict) -> AiAnalysisResult:
        if not self.api_key:
            raise ProviderError("Missing OPENAI_API_KEY")
        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are a disciplined forex analyst. Reason only from provided data. "
                            "Return strict JSON with keys: recommendation, narrative, caution_flags, "
                            "entry_zone, sl_rationale."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, default=str)},
                ],
                reasoning={"effort": "minimal"},
                text={"format": {"type": "json_object"}},
            )
        except AuthenticationError as exc:
            self.logger.exception("OpenAI authentication failed")
            raise ProviderError("OpenAI authentication failed") from exc
        except APITimeoutError as exc:
            self.logger.exception("OpenAI analysis timed out")
            raise ProviderError("OpenAI request timed out") from exc
        except APIConnectionError as exc:
            self.logger.exception("OpenAI connection failed")
            raise ProviderError("OpenAI connection failed") from exc
        except APIStatusError as exc:
            self.logger.exception("OpenAI returned API status error")
            raise ProviderError(f"OpenAI returned HTTP {exc.status_code}") from exc
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("OpenAI analysis failed")
            raise ProviderError(f"OpenAI request failed: {exc.__class__.__name__}") from exc

        if not response.output_text or not response.output_text.strip():
            self.logger.error("OpenAI returned an empty response body")
            raise ProviderError("OpenAI returned an empty response body")

        try:
            parsed = json.loads(response.output_text)
            return AiAnalysisResult(provider=self.name, model=self.model, **parsed)
        except (ValueError, TypeError):
            self.logger.exception("OpenAI analysis parsing failed")
            raise ProviderError("OpenAI returned invalid JSON content") from None
