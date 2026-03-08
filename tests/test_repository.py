from datetime import UTC, datetime
import logging

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from hedge_fund.domain.exceptions import PersistenceError
from hedge_fund.domain.models import AiAnalysisResult, BiasResult, SetupScanResult
from hedge_fund.storage.base import Base
from hedge_fund.storage.repository import ScanPersistencePayload, ScanRepository


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_repository_saves_scan_run() -> None:
    session = _session()
    repo = ScanRepository(session, logging.getLogger("test"))
    repo.save_scan_run(
        ScanPersistencePayload(
            timestamp=datetime(2026, 3, 8, tzinfo=UTC),
            pairs_scanned=["EURUSD"],
            config_snapshot={"settings": {"foo": "bar"}},
            biases=[
                BiasResult(
                    pair="EURUSD",
                    bias="Bullish",
                    structure="HH/HL",
                    key_level=1.1,
                    key_level_type="swing_low",
                )
            ],
            setups=[
                SetupScanResult(
                    pair="EURUSD",
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
            ai_output=[
                AiAnalysisResult(
                    provider="openai",
                    model="gpt-5-mini",
                    recommendation="Long",
                    narrative="Looks good",
                    caution_flags=[],
                    entry_zone="1.10-1.11",
                    sl_rationale="Below sweep low",
                )
            ],
            success=True,
        )
    )

    assert session.execute(text("select count(*) from scan_runs")).scalar_one() == 1


def test_repository_wraps_failures() -> None:
    session = _session()
    repo = ScanRepository(session, logging.getLogger("test"))

    def explode():
        raise RuntimeError("boom")

    session.commit = explode  # type: ignore[method-assign]

    with pytest.raises(PersistenceError):
        repo.save_scan_run(
            ScanPersistencePayload(
                timestamp=datetime(2026, 3, 8, tzinfo=UTC),
                pairs_scanned=["EURUSD"],
                config_snapshot={"settings": {}},
                biases=[],
                setups=[],
                ai_output=[],
                success=True,
            )
        )
