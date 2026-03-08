from __future__ import annotations

from datetime import UTC, datetime

from hedge_fund.domain.models import AiAnalysisResult, BiasResult, SetupScanResult
from hedge_fund.integrations.ai.orchestrator import AiOrchestrator


class AiAnalyst:
    def __init__(self, orchestrator: AiOrchestrator) -> None:
        self.orchestrator = orchestrator

    def analyze(
        self,
        bias: BiasResult,
        setup: SetupScanResult,
        sessions: dict,
    ) -> AiAnalysisResult | None:
        payload = {
            "timestamp_utc": datetime.now(tz=UTC).isoformat(),
            "bias": bias.model_dump(),
            "setup": setup.model_dump(),
            "sessions": sessions,
            "instructions": {
                "news_policy": "No external news feed is available. If timing is risky, state a caution flag.",
                "reasoning_policy": "Use only provided data and do not invent missing signals.",
            },
        }
        return self.orchestrator.analyze(payload)
