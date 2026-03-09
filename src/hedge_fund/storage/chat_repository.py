from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from hedge_fund.chat.models import ChatTurn, StoredChatSession
from hedge_fund.domain.exceptions import PersistenceError
from hedge_fund.domain.models import SessionResumePayload, SessionSummary
from hedge_fund.storage.models import ProphetMemoryRecord, SessionArchiveRecord


MEMORY_RECORD_ID = "default"


class SessionArchiveRepository:
    def __init__(self, session: Session, logger: logging.Logger) -> None:
        self.session = session
        self.logger = logger

    def upsert(self, chat_session: StoredChatSession) -> None:
        try:
            record = self.session.get(SessionArchiveRecord, chat_session.session_id)
            messages = self._serialize_turns(chat_session.turns)
            if record is None:
                record = SessionArchiveRecord(
                    id=chat_session.session_id,
                    started_at=chat_session.created_at,
                    ended_at=chat_session.ended_at,
                    summary=chat_session.summary,
                    messages=messages,
                )
                self.session.add(record)
            else:
                record.started_at = chat_session.created_at
                record.ended_at = chat_session.ended_at
                record.summary = chat_session.summary
                record.messages = messages
            self.session.commit()
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            self.logger.exception("Failed to persist archived session")
            raise PersistenceError("Failed to persist archived session") from exc

    def list_recent(self, limit: int) -> list[SessionSummary]:
        records = (
            self.session.query(SessionArchiveRecord)
            .order_by(SessionArchiveRecord.started_at.desc())
            .limit(limit)
            .all()
        )
        return [
            SessionSummary(
                id=record.id,
                started_at=record.started_at,
                ended_at=record.ended_at,
                summary=record.summary,
                turn_count=len(self._deserialize_turns(record.messages)),
            )
            for record in records
        ]

    def get_resume_payload(self, session_id: str) -> SessionResumePayload | None:
        record = self.session.get(SessionArchiveRecord, session_id)
        if record is None:
            return None
        turns = self._deserialize_turns(record.messages)
        recap = self._build_recap(record, turns)
        return SessionResumePayload(
            id=record.id,
            messages=[{"role": turn.role, "content": turn.content, "metadata": turn.metadata} for turn in turns],
            summary=record.summary,
            recap=recap,
        )

    def prune(self, max_stored: int) -> None:
        stale_ids = [
            row[0]
            for row in self.session.query(SessionArchiveRecord.id)
            .order_by(SessionArchiveRecord.started_at.desc())
            .offset(max_stored)
            .all()
        ]
        if not stale_ids:
            return
        try:
            self.session.query(SessionArchiveRecord).filter(
                SessionArchiveRecord.id.in_(stale_ids)
            ).delete(synchronize_session=False)
            self.session.commit()
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            self.logger.exception("Failed to prune archived sessions")
            raise PersistenceError("Failed to prune archived sessions") from exc

    def _serialize_turns(self, turns: list[ChatTurn]) -> str:
        return json.dumps([turn.model_dump(mode="json") for turn in turns], ensure_ascii=True)

    def _deserialize_turns(self, payload: str) -> list[ChatTurn]:
        try:
            raw = json.loads(payload or "[]")
        except ValueError:
            return []
        return [ChatTurn.model_validate(item) for item in raw]

    def _build_recap(self, record: SessionArchiveRecord, turns: list[ChatTurn]) -> str:
        when = record.started_at.astimezone(UTC).strftime("%a %b %d").replace(" 0", " ")
        summary = record.summary or "No summary saved."
        last_assistant = next((turn.content for turn in reversed(turns) if turn.role == "assistant" and turn.content), "")
        if last_assistant:
            return f"Resuming session from {when}. {summary} Last response: {last_assistant}"
        return f"Resuming session from {when}. {summary}"


class ProphetMemoryRepository:
    def __init__(self, session: Session, logger: logging.Logger) -> None:
        self.session = session
        self.logger = logger

    def get_content(self) -> str:
        record = self.session.get(ProphetMemoryRecord, MEMORY_RECORD_ID)
        return record.content if record else ""

    def set_content(self, content: str) -> str:
        now = datetime.now(tz=UTC)
        try:
            record = self.session.get(ProphetMemoryRecord, MEMORY_RECORD_ID)
            if record is None:
                record = ProphetMemoryRecord(id=MEMORY_RECORD_ID, content=content, updated_at=now)
                self.session.add(record)
            else:
                record.content = content
                record.updated_at = now
            self.session.commit()
            return record.content
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            self.logger.exception("Failed to persist PROPHET memory")
            raise PersistenceError("Failed to persist PROPHET memory") from exc

    def add_rule(self, rule: str, max_characters: int) -> tuple[str, bool]:
        content = self.get_content().strip()
        lines = [line for line in content.splitlines() if line.strip()]
        bullet = rule.strip()
        if not bullet:
            return content, True
        normalized = (bullet[2:] if bullet.startswith("- ") else bullet).strip()
        normalized_key = normalized.lower()
        existing = {
            ((line[2:] if line.startswith("- ") else line).strip().lower())
            for line in lines
        }
        entry = f"- {normalized}"
        if normalized_key not in existing:
            lines.append(entry)
        updated = "\n".join(lines)
        if len(updated) > max_characters:
            return content, False
        return self.set_content(updated), True

    def forget_rule(self, rule: str) -> str:
        target = rule.strip().lower()
        lines = [line for line in self.get_content().splitlines() if line.strip()]
        kept = []
        for line in lines:
            normalized = line[2:] if line.startswith("- ") else line
            if normalized.strip().lower() == target:
                continue
            kept.append(line)
        return self.set_content("\n".join(kept))
