from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hedge_fund.storage.base import Base


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    pairs_scanned: Mapped[list[str]] = mapped_column(JSON)
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    ai_provider_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_output: Mapped[list[dict]] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    failure_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    setups: Mapped[list["DetectedSetup"]] = relationship(
        back_populates="scan_run",
        cascade="all, delete-orphan",
    )


class ChatSessionRecord(Base):
    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[str] = mapped_column(Text)


class DetectedSetup(Base):
    __tablename__ = "detected_setups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), index=True)
    pair: Mapped[str] = mapped_column(String(20), index=True)
    timeframe: Mapped[str] = mapped_column(String(10))
    bias: Mapped[str] = mapped_column(String(20))
    structure: Mapped[str] = mapped_column(String(20))
    key_level: Mapped[float] = mapped_column(Float)
    key_level_type: Mapped[str] = mapped_column(String(20))
    fvg_detected: Mapped[bool] = mapped_column(Boolean)
    fvg_range: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fib_zone_hit: Mapped[bool] = mapped_column(Boolean)
    fib_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidity_sweep: Mapped[bool] = mapped_column(Boolean)
    sweep_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[int] = mapped_column(Integer, index=True)
    surfaced: Mapped[bool] = mapped_column(Boolean)
    signals_summary: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(String(20))

    scan_run: Mapped[ScanRun] = relationship(back_populates="setups")
