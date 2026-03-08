import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hedge_fund.api import ChatRequest, chat
from hedge_fund.chat.models import ChatResponse, ChatTurn
from hedge_fund.chat.session_store import DatabaseSessionStore
from hedge_fund.config.settings import Settings
from hedge_fund.storage.base import Base


def _session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_database_session_store_round_trips_state_across_instances() -> None:
    factory = _session_factory()
    first = DatabaseSessionStore(factory)
    second = DatabaseSessionStore(factory)

    state = first.create(
        max_context_turns=Settings.load().chat.max_context_turns,
        permission_mode="default",
        model_override="auto",
        append_system_prompt=None,
    )
    first.add_turn(state, ChatTurn(role="user", content="hello"))

    loaded = second.load(state.session.session_id)
    latest = second.load_latest()

    assert loaded.session.session_id == state.session.session_id
    assert loaded.session.turns[-1].content == "hello"
    assert latest.session.session_id == state.session.session_id


def test_chat_endpoint_returns_full_chat_response(monkeypatch, tmp_path) -> None:
    class FakeService:
        def process_message(self, state, message):
            return ChatResponse(
                session_id=state.session.session_id,
                message="Closing chat session.",
                metadata={"view": "help_menu", "commands": [("/help", "Show the command palette")]},
                should_exit=True,
            )

    class FakeRunner:
        def __init__(self, context, cwd=None, session_store=None, repository=None) -> None:
            self.session_store = session_store
            self.closed = False

        def build_service(self, model_override, append_system_prompt):
            return FakeService()

        def close(self) -> None:
            self.closed = True

    class FakeContext:
        def __init__(self) -> None:
            self.settings = Settings.load()
            self.logger = logging.getLogger("test")

        def create_repository(self, session):
            return object()

    monkeypatch.setattr("hedge_fund.api.ChatCommandRunner", FakeRunner)

    store = DatabaseSessionStore(_session_factory())
    response = chat(ChatRequest(message="/exit"), FakeContext(), object(), store)

    assert response.should_exit is True
    assert response.metadata["view"] == "help_menu"
    assert response.message == "Closing chat session."
