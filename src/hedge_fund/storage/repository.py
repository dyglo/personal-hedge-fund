from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from hedge_fund.domain.exceptions import PersistenceError
from hedge_fund.domain.models import AiAnalysisResult, BiasResult, SetupScanResult
from hedge_fund.storage.models import DetectedSetup, ScanRun


@dataclass
class ScanPersistencePayload:
    timestamp: object
    pairs_scanned: list[str]
    config_snapshot: dict
    biases: list[BiasResult]
    setups: list[SetupScanResult]
    ai_output: list[AiAnalysisResult]
    success: bool
    failure_metadata: dict | None = None


class ScanRepository:
    def __init__(self, session: Session, logger: logging.Logger) -> None:
        self.session = session
        self.logger = logger

    def save_scan_run(self, payload: ScanPersistencePayload) -> None:
        try:
            run = ScanRun(
                timestamp=payload.timestamp,
                pairs_scanned=payload.pairs_scanned,
                config_snapshot=payload.config_snapshot,
                ai_provider_used=payload.ai_output[0].provider if payload.ai_output else None,
                ai_output=[item.model_dump() for item in payload.ai_output],
                success=payload.success,
                failure_metadata=payload.failure_metadata,
            )
            self.session.add(run)
            self.session.flush()
            self._attach_setups(run.id, payload.biases, payload.setups)
            self.session.commit()
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            self.logger.exception("Failed to persist scan run")
            raise PersistenceError("Failed to persist scan run") from exc

    def _attach_setups(
        self,
        scan_run_id: int,
        biases: Iterable[BiasResult],
        setups: Iterable[SetupScanResult],
    ) -> None:
        bias_map = {bias.pair: bias for bias in biases}
        for setup in setups:
            bias = bias_map[setup.pair]
            row = DetectedSetup(
                scan_run_id=scan_run_id,
                pair=setup.pair,
                timeframe=setup.timeframe,
                bias=bias.bias,
                structure=bias.structure,
                key_level=bias.key_level,
                key_level_type=bias.key_level_type,
                fvg_detected=setup.fvg_detected,
                fvg_range=setup.fvg_range.model_dump() if setup.fvg_range else None,
                fib_zone_hit=setup.fib_zone_hit,
                fib_level=setup.fib_level,
                liquidity_sweep=setup.liquidity_sweep,
                sweep_level=setup.sweep_level,
                score=setup.score,
                surfaced=setup.surfaced,
                signals_summary=setup.signals_summary,
                direction=setup.direction,
            )
            self.session.add(row)
