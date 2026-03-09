import logging
import asyncio
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hedge_fund.api import ChatRequest, calendar_endpoint, chat, memory_endpoint, sessions_endpoint, update_memory_endpoint, MemoryRequest
from hedge_fund.chat.models import ChatResponse, ChatTurn
from hedge_fund.chat.session_store import DatabaseSessionStore, SessionNotFoundError
from hedge_fund.cli.bootstrap import ApplicationContext
from hedge_fund.domain.exceptions import ConfigurationError
from hedge_fund.integrations.calendar import TwelveDataCalendarClient
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


def test_database_session_store_populates_archived_session_listing() -> None:
    store = DatabaseSessionStore(_session_factory())
    state = store.create(
        max_context_turns=Settings.load().chat.max_context_turns,
        permission_mode="default",
        model_override=None,
        append_system_prompt=None,
    )
    store.add_turn(state, ChatTurn(role="user", content="hello"))
    state.session.summary = "Covered EURUSD bias and entries."
    state.session.ended_at = state.session.updated_at
    store.finalize(state)

    listing = store.list_recent()
    resume_payload = store.load_resume_payload(state.session.session_id)

    assert listing[0].summary == "Covered EURUSD bias and entries."
    assert resume_payload.messages[-1]["content"] == "hello"


def test_database_session_store_only_archives_on_finalize() -> None:
    store = DatabaseSessionStore(_session_factory())
    state = store.create(
        max_context_turns=Settings.load().chat.max_context_turns,
        permission_mode="default",
        model_override=None,
        append_system_prompt=None,
    )
    store.add_turn(state, ChatTurn(role="user", content="hello"))

    assert store.list_recent() == []

    state.session.summary = "Finalized"
    state.session.ended_at = state.session.updated_at
    store.finalize(state)

    assert store.list_recent()[0].summary == "Finalized"


def test_database_session_store_raises_domain_specific_miss() -> None:
    store = DatabaseSessionStore(_session_factory())

    with pytest.raises(SessionNotFoundError) as exc_info:
        store.load("missing")

    assert str(exc_info.value) == "missing"


def test_chat_endpoint_returns_full_chat_response_and_closes_runner(monkeypatch) -> None:
    created_runners = []

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
            created_runners.append(self)

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
    assert created_runners[0].closed is True


def test_chat_endpoint_streams_sse_events(monkeypatch) -> None:
    class FakeService:
        def process_message(self, state, message, authorize_mutation=None, event_sink=None, stream_handler=None):
            assert stream_handler is not None
            stream_handler("Hello ")
            stream_handler("world")
            return ChatResponse(session_id=state.session.session_id, message="Hello world")

    class FakeRunner:
        def __init__(self, context, cwd=None, session_store=None, repository=None) -> None:
            self.session_store = session_store

        def build_service(self, model_override, append_system_prompt):
            return FakeService()

        def close(self) -> None:
            return None

    class FakeContext:
        def __init__(self) -> None:
            self.settings = Settings.load()
            self.logger = logging.getLogger("test")

        def create_repository(self, session):
            return object()

    monkeypatch.setattr("hedge_fund.api.ChatCommandRunner", FakeRunner)

    store = DatabaseSessionStore(_session_factory())
    response = chat(ChatRequest(message="Hello", stream=True), FakeContext(), object(), store)

    chunks = []

    async def collect() -> None:
        async for chunk in response.body_iterator:
            chunks.append(chunk)

    asyncio.run(collect())

    combined = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)
    assert "event: message" in combined
    assert '"delta": "Hello "' in combined
    assert "event: done" in combined


def test_session_scope_rolls_back_before_close_on_exception() -> None:
    events = []

    class FakeSession:
        def rollback(self) -> None:
            events.append("rollback")

        def close(self) -> None:
            events.append("close")

    context = ApplicationContext.__new__(ApplicationContext)
    context.create_session = lambda: FakeSession()  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        with ApplicationContext.session_scope(context):
            raise RuntimeError("boom")

    assert events == ["rollback", "close"]


def test_memory_and_calendar_endpoints_use_context_repositories() -> None:
    class FakeMemoryRepository:
        def __init__(self) -> None:
            self.content = "- Rule"

        def get_content(self):
            return self.content

        def set_content(self, content: str):
            self.content = content
            return self.content

    class FakeCalendarService:
        def get_events(self, view: str, pairs: list[str]):
            return type(
                "CalendarPayload",
                (),
                {
                    "model_dump": lambda self, mode="json": {
                        "view": view,
                        "provider": "fake",
                        "events": [{"event_name": "CPI"}],
                        "warnings": [],
                    }
                },
            )()

    context = ApplicationContext.__new__(ApplicationContext)
    context.settings = Settings.load()
    context.create_memory_repository = lambda session: FakeMemoryRepository()  # type: ignore[method-assign]
    context.calendar = object()

    memory = memory_endpoint(context, object())
    updated = update_memory_endpoint(MemoryRequest(content="- New rule"), context, object())

    monkeypatch_calendar = FakeCalendarService()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("hedge_fund.api.create_calendar_service", lambda ctx: monkeypatch_calendar)
    try:
        calendar = calendar_endpoint(context, "today", "XAUUSD")
    finally:
        monkeypatch.undo()

    assert memory["content"] == "- Rule"
    assert updated["content"] == "- New rule"
    assert calendar["events"][0]["event_name"] == "CPI"


def test_sessions_endpoint_returns_archived_listing() -> None:
    store = DatabaseSessionStore(_session_factory())
    state = store.create(
        max_context_turns=Settings.load().chat.max_context_turns,
        permission_mode="default",
        model_override=None,
        append_system_prompt=None,
    )
    state.session.summary = "Summary"
    state.session.ended_at = state.session.updated_at
    store.finalize(state)

    payload = sessions_endpoint(store)

    assert payload[0]["summary"] == "Summary"


def test_twelve_data_calendar_requires_api_key() -> None:
    client = TwelveDataCalendarClient(None, 5.0, logging.getLogger("test"))

    with pytest.raises(ConfigurationError) as exc_info:
        client.fetch_events(date(2026, 3, 9), date(2026, 3, 9))

    assert "TWELVEDATA_API_KEY" in str(exc_info.value)
