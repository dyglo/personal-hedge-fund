from __future__ import annotations

import json
import logging

import httpx

from hedge_fund.domain.exceptions import ProviderError
from hedge_fund.domain.interfaces import AiProvider
from hedge_fund.domain.models import AiAnalysisResult


class GeminiProvider(AiProvider):
    name = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str | None, model: str, timeout_seconds: float, logger: logging.Logger) -> None:
        self.api_key = api_key
        self.model = model
        self.logger = logger
        self.timeout_seconds = timeout_seconds

    def analyze(self, payload: dict) -> AiAnalysisResult:
        pair = payload.get("bias", {}).get("pair", "unknown")
        if not self.api_key:
            raise ProviderError("Missing GEMINI_API_KEY")
        system_prompt = (
            "You are a disciplined forex analyst. Reason only from provided structured data. "
            "Do not invent signals. Return strict JSON with keys: recommendation, narrative, "
            "caution_flags, entry_zone, sl_rationale."
        )
        try:
            response = httpx.post(
                f"{self.base_url}/{self.model}:generateContent",
                params={"key": self.api_key},
                json={
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": json.dumps(payload, default=str)}],
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0,
                        "response_mime_type": "application/json",
                    },
                },
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            self.logger.exception("Gemini analysis request failed")
            raise ProviderError("Gemini request failed") from exc

        if response.status_code != 200:
            self.logger.error("Gemini returned non-200 status: %s", response.status_code)
            raise ProviderError(f"Gemini returned HTTP {response.status_code}")
        if not response.text.strip():
            self.logger.error("Gemini returned an empty response body")
            raise ProviderError("Gemini returned an empty response body")

        try:
            body = response.json()
            text = body["candidates"][0]["content"]["parts"][0]["text"]
            if not text or not text.strip():
                self.logger.error("Gemini returned empty content")
                raise ProviderError("Gemini returned empty content")
            cleaned_text = self._coerce_json_text(text)
            parsed = json.loads(cleaned_text)
            return AiAnalysisResult(provider=self.name, model=self.model, **parsed)
        except (KeyError, IndexError, ValueError, TypeError):
            self.logger.exception("Gemini analysis parsing failed for %s", pair)
            self.logger.error("Raw Gemini response for %s: %s", pair, response.text)
            raise ProviderError(f"Gemini returned invalid JSON content for {pair}") from None

    def _strip_code_fences(self, text: str) -> str:
        stripped = text.strip()
        if not stripped.startswith("```"):
            return stripped
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def _coerce_json_text(self, text: str) -> str:
        stripped = self._strip_code_fences(text)
        if stripped.startswith("{") and stripped.endswith("}"):
            return stripped

        first = stripped.find("{")
        last = stripped.rfind("}")
        if first != -1 and last != -1 and first < last:
            return stripped[first : last + 1]
        return stripped
