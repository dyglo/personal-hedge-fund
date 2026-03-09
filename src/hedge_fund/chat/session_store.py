from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from hedge_fund.chat.models import ChatSessionState, ChatTurn, StoredChatSession
from hedge_fund.chat.utils import chat_root
from hedge_fund.domain.models import SessionResumePayload, SessionSummary
from hedge_fund.storage.chat_repository import SessionArchiveRepository
from hedge_fund.storage.models import ChatSessionRecord


class SessionNotFoundError(Exception):
    pass


class DatabaseSessionStore:
    def __init__(self, session_factory, max_stored_sessions: int = 30) -> None:
        self.session_factory = session_factory
        self.max_stored_sessions = max_stored_sessions
        self.logger = logging.getLogger("hedge_fund.chat.session_store")

    def create(self, max_context_turns: int, permission_mode: str, model_override: str | None, append_system_prompt: str | None) -> ChatSessionState:
        session = StoredChatSession(
            permission_mode=permission_mode,
            model_override=model_override,
            append_system_prompt=append_system_prompt,
        )
        state = ChatSessionState(session=session, max_context_turns=max_context_turns)
        self.save(state)
        return state

    def save(self, state: ChatSessionState) -> None:
        state.session.updated_at = datetime.now(tz=UTC)
        payload = state.model_dump_json(indent=2)
        with self.session_factory() as db:
            record = db.get(ChatSessionRecord, state.session.session_id)
            if record is None:
                record = ChatSessionRecord(
                    session_id=state.session.session_id,
                    updated_at=state.session.updated_at,
                    payload=payload,
                )
                db.add(record)
            else:
                record.updated_at = state.session.updated_at
                record.payload = payload
            db.commit()

    def load(self, session_id: str) -> ChatSessionState:
        with self.session_factory() as db:
            record = db.get(ChatSessionRecord, session_id)
            if record is None:
                raise SessionNotFoundError(session_id)
            return ChatSessionState.model_validate_json(record.payload)

    def load_latest(self) -> ChatSessionState:
        with self.session_factory() as db:
            record = (
                db.query(ChatSessionRecord)
                .order_by(ChatSessionRecord.updated_at.desc())
                .limit(1)
                .one_or_none()
            )
            if record is None:
                raise SessionNotFoundError("No saved chat sessions")
            return ChatSessionState.model_validate_json(record.payload)

    def add_turn(self, state: ChatSessionState, turn: ChatTurn) -> None:
        state.session.turns.append(turn)
        self.save(state)

    def list_recent(self) -> list[SessionSummary]:
        with self.session_factory() as db:
            return SessionArchiveRepository(db, self.logger).list_recent(self.max_stored_sessions)

    def load_resume_payload(self, session_id: str) -> SessionResumePayload:
        with self.session_factory() as db:
            payload = SessionArchiveRepository(db, self.logger).get_resume_payload(session_id)
            if payload is None:
                raise SessionNotFoundError(session_id)
            return payload

    def finalize(self, state: ChatSessionState) -> None:
        self.save(state)
        with self.session_factory() as archive_db:
            archive = SessionArchiveRepository(archive_db, self.logger)
            archive.upsert(state.session)
            archive.prune(self.max_stored_sessions)


class SessionStore:
    def __init__(self, cwd: str | Path) -> None:
        self.root = chat_root(cwd) / "chat"
        self.root.mkdir(parents=True, exist_ok=True)
        self.latest_file = self.root / "latest.txt"

    def create(self, max_context_turns: int, permission_mode: str, model_override: str | None, append_system_prompt: str | None) -> ChatSessionState:
        session = StoredChatSession(
            permission_mode=permission_mode,
            model_override=model_override,
            append_system_prompt=append_system_prompt,
        )
        state = ChatSessionState(session=session, max_context_turns=max_context_turns)
        self.save(state)
        return state

    def save(self, state: ChatSessionState) -> None:
        state.session.updated_at = datetime.now(tz=UTC)
        path = self.root / f"{state.session.session_id}.json"
        path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        self.latest_file.write_text(state.session.session_id, encoding="utf-8")

    def load(self, session_id: str) -> ChatSessionState:
        path = self.root / f"{session_id}.json"
        try:
            payload = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise SessionNotFoundError(session_id) from exc
        return ChatSessionState.model_validate_json(payload)

    def load_latest(self) -> ChatSessionState:
        try:
            session_id = self.latest_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise SessionNotFoundError("No saved chat sessions") from exc
        return self.load(session_id)

    def add_turn(self, state: ChatSessionState, turn: ChatTurn) -> None:
        state.session.turns.append(turn)
        self.save(state)

    def list_recent(self) -> list[SessionSummary]:
        raise SessionNotFoundError("Session listing is unavailable for local file storage")

    def load_resume_payload(self, session_id: str) -> SessionResumePayload:
        state = self.load(session_id)
        return SessionResumePayload(
            id=state.session.session_id,
            summary=state.session.summary,
            recap=state.session.summary,
            messages=[{"role": turn.role, "content": turn.content, "metadata": turn.metadata} for turn in state.session.turns],
        )

    def finalize(self, state: ChatSessionState) -> None:
        self.save(state)
