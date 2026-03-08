from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hedge_fund.chat.models import ChatSessionState, ChatTurn, StoredChatSession
from hedge_fund.chat.utils import chat_root
from hedge_fund.storage.models import ChatSessionRecord


class DatabaseSessionStore:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

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
                raise FileNotFoundError(session_id)
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
                raise FileNotFoundError("No saved chat sessions")
            return ChatSessionState.model_validate_json(record.payload)

    def add_turn(self, state: ChatSessionState, turn: ChatTurn) -> None:
        state.session.turns.append(turn)
        self.save(state)


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
        return ChatSessionState.model_validate_json(path.read_text(encoding="utf-8"))

    def load_latest(self) -> ChatSessionState:
        session_id = self.latest_file.read_text(encoding="utf-8").strip()
        return self.load(session_id)

    def add_turn(self, state: ChatSessionState, turn: ChatTurn) -> None:
        state.session.turns.append(turn)
        self.save(state)
