from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from hedge_fund.domain.exceptions import PersistenceError
from hedge_fund.storage.models import UserProfileRecord


class UserProfileRepository:
    def __init__(self, session: Session, logger: logging.Logger) -> None:
        self.session = session
        self.logger = logger

    def create(
        self,
        *,
        device_token: str,
        display_name: str,
        experience_level: str,
        watchlist: list[str],
        account_balance: float,
        risk_pct: float,
        min_rr: str,
        sessions: list[str],
        prophet_md: str,
    ) -> UserProfileRecord:
        now = datetime.now(tz=UTC)
        record = UserProfileRecord(
            device_token=device_token,
            display_name=display_name,
            experience_level=experience_level,
            watchlist=watchlist,
            account_balance=account_balance,
            risk_pct=risk_pct,
            min_rr=min_rr,
            sessions=sessions,
            prophet_md=prophet_md,
            created_at=now,
            updated_at=now,
        )
        try:
            self.session.add(record)
            self.session.commit()
            self.session.refresh(record)
            return record
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            self.logger.exception("Failed to create user profile")
            raise PersistenceError("Failed to create user profile") from exc

    def get_by_device_token(self, device_token: str) -> UserProfileRecord | None:
        return (
            self.session.query(UserProfileRecord)
            .filter(UserProfileRecord.device_token == device_token)
            .one_or_none()
        )
