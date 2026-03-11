from __future__ import annotations

import json
import os
from pathlib import Path
from queue import Empty, Queue
from threading import Lock
from threading import Thread
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from hedge_fund.chat.command import ChatCommandRunner
from hedge_fund.chat.ai import ChatLanguageService
from hedge_fund.chat.agent_runtime import AgentEventSink
from hedge_fund.chat.models import ChatResponse, ChatTurn
from hedge_fund.chat.session_store import DatabaseSessionStore, SessionNotFoundError
from hedge_fund.cli.bootstrap import ApplicationContext
from hedge_fund.services.calendar_service import CalendarService
from hedge_fund.services.scan_service import RiskService, ScanService

app = FastAPI(title="Prophet API")


class ClientChatMessage(BaseModel):
    role: str
    content: str
    metadata: dict = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str | None = None
    stream: bool = False
    history: list[ClientChatMessage] = Field(default_factory=list)
    messages: list[ClientChatMessage] = Field(default_factory=list)


class ScanRequest(BaseModel):
    pair: str | None = None


class RiskRequest(BaseModel):
    pair: str
    risk: float
    sl: int


class MemoryRequest(BaseModel):
    content: str


_context: ApplicationContext | None = None
_context_lock = Lock()


def get_context() -> ApplicationContext:
    global _context
    if _context is None:
        with _context_lock:
            if _context is None:
                _context = ApplicationContext()
    return _context


def get_db_session(context: Annotated[ApplicationContext, Depends(get_context)]):
    with context.session_scope() as session:
        yield session


def get_chat_session_store(context: Annotated[ApplicationContext, Depends(get_context)]) -> DatabaseSessionStore:
    language = ChatLanguageService(
        context.settings,
        context.env,
        context.logger,
    )
    return DatabaseSessionStore(
        context.session_factory,
        max_stored_sessions=context.settings.sessions.max_stored,
        summary_generator=language.summarize_session,
    )


def create_scan_service(context: ApplicationContext, session: Session) -> ScanService:
    return ScanService(
        context.settings,
        context.market_data,
        context.ai,
        context.create_repository(session),
        context.logger,
    )


def create_calendar_service(context: ApplicationContext) -> CalendarService:
    return CalendarService(context.calendar)


def _sync_request_history(state, request: ChatRequest) -> None:
    request_history = request.history or request.messages
    if not request_history:
        return
    turns = [ChatTurn(role=item.role, content=item.content, metadata=item.metadata) for item in request_history]
    if turns and turns[-1].role == "user" and turns[-1].content.strip() == request.message.strip():
        turns = turns[:-1]
    state.session.turns = turns


def _load_or_create_state(
    request: ChatRequest,
    context: ApplicationContext,
    session_store: DatabaseSessionStore,
) -> object:
    if request.session_id:
        try:
            return session_store.load(request.session_id)
        except SessionNotFoundError:
            pass
    return session_store.create(
        max_context_turns=context.settings.chat.max_context_turns,
        permission_mode="default",
        model_override=request.model,
        append_system_prompt=None,
    )


def _is_streamable_message_by_settings(settings, message: str) -> bool:
    if not getattr(settings, "streaming", None):
        return True
    if not settings.streaming.enabled:
        return False
    lowered = message.strip().lower()
    if not lowered or lowered.startswith("/"):
        return False
    if any(phrase in lowered for phrase in ("trade plan", "plan this trade", "generate a plan")):
        return True
    if "entry" in lowered and ("stop" in lowered or "stop loss" in lowered):
        return True
    blocked_terms = (
        "scan",
        "bias",
        "lot size",
        "risk",
        "calendar",
        "event",
        "news today",
        "rank",
        "best setup",
        "focus on",
        "compare",
    )
    return not any(term in lowered for term in blocked_terms)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class StreamingAgentEventSink(AgentEventSink):
    def __init__(self, queue: Queue[tuple[str, object]]) -> None:
        self.queue = queue

    def update_status(self, message: str) -> None:
        self.queue.put(("step", {"message": message}))

    def emit_reasoning(self, message: str) -> None:
        self.queue.put(("reasoning", {"message": message}))


@app.get("/")
def read_root():
    return {"status": "ok", "app": "Prophet API"}


@app.post("/chat")
def chat(
    request: ChatRequest,
    context: Annotated[ApplicationContext, Depends(get_context)],
    session: Annotated[Session, Depends(get_db_session)],
    session_store: Annotated[DatabaseSessionStore, Depends(get_chat_session_store)],
):
    state = _load_or_create_state(request, context, session_store)

    _sync_request_history(state, request)
    should_stream = request.stream and _is_streamable_message_by_settings(context.settings, request.message)
    if not should_stream:
        runner = ChatCommandRunner(
            context,
            cwd=Path(os.getcwd()),
            session_store=session_store,
            repository=context.create_repository(session),
        )
        service = runner.build_service(state.session.model_override, state.session.append_system_prompt)
        try:
            return service.process_message(state, request.message)
        finally:
            runner.close()

    def event_stream():
        queue: Queue[tuple[str, object]] = Queue()

        def worker() -> None:
            worker_runner = None
            try:
                with context.session_scope() as worker_session:
                    worker_runner = ChatCommandRunner(
                        context,
                        cwd=Path(os.getcwd()),
                        session_store=session_store,
                        repository=context.create_repository(worker_session),
                    )
                    worker_service = worker_runner.build_service(
                        state.session.model_override,
                        state.session.append_system_prompt,
                    )
                    response = worker_service.process_message(
                        state,
                        request.message,
                        event_sink=StreamingAgentEventSink(queue),
                        stream_handler=lambda chunk: queue.put(("chunk", chunk)),
                    )
                queue.put(("response", response.model_dump(mode="json")))
            except Exception as exc:  # noqa: BLE001
                queue.put(("error", str(exc)))
            finally:
                if worker_runner is not None:
                    worker_runner.close()
                queue.put(("done", None))

        Thread(target=worker, daemon=True).start()
        while True:
            try:
                kind, payload = queue.get(timeout=0.1)
            except Empty:
                continue
            if kind == "chunk":
                yield _sse("message", {"delta": payload})
                continue
            if kind == "step":
                yield _sse("step", payload if isinstance(payload, dict) else {})
                continue
            if kind == "reasoning":
                yield _sse("reasoning", payload if isinstance(payload, dict) else {})
                continue
            if kind == "response":
                yield _sse("done", payload if isinstance(payload, dict) else {})
                continue
            if kind == "error":
                yield _sse("error", {"message": payload})
                continue
            if kind == "done":
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/scan")
def scan_endpoint(
    request: ScanRequest,
    context: Annotated[ApplicationContext, Depends(get_context)],
    session: Annotated[Session, Depends(get_db_session)],
):
    service = create_scan_service(context, session)
    pairs = [request.pair] if request.pair else context.settings.trading.pairs
    return service.scan(pairs)


@app.post("/bias")
def bias_endpoint(
    request: ScanRequest,
    context: Annotated[ApplicationContext, Depends(get_context)],
    session: Annotated[Session, Depends(get_db_session)],
):
    service = create_scan_service(context, session)
    pairs = [request.pair] if request.pair else context.settings.trading.pairs
    return service.bias_only(pairs)


@app.post("/risk")
def risk_endpoint(
    request: RiskRequest,
    context: Annotated[ApplicationContext, Depends(get_context)],
):
    service = RiskService(context.market_data, context.broker)
    return service.calculate(request.pair, request.risk, request.sl)


@app.get("/sessions")
def sessions_endpoint(
    session_store: Annotated[DatabaseSessionStore, Depends(get_chat_session_store)],
):
    return [item.model_dump(mode="json") for item in session_store.list_recent()]


@app.post("/sessions/resume/{session_id}")
def resume_session_endpoint(
    session_id: str,
    session_store: Annotated[DatabaseSessionStore, Depends(get_chat_session_store)],
):
    return session_store.load_resume_payload(session_id).model_dump(mode="json")


@app.get("/memory")
def memory_endpoint(
    context: Annotated[ApplicationContext, Depends(get_context)],
    session: Annotated[Session, Depends(get_db_session)],
):
    return {"content": context.create_memory_repository(session).get_content()}


@app.post("/memory")
def update_memory_endpoint(
    request: MemoryRequest,
    context: Annotated[ApplicationContext, Depends(get_context)],
    session: Annotated[Session, Depends(get_db_session)],
):
    content = context.create_memory_repository(session).set_content(request.content)
    return {"content": content}


@app.get("/calendar")
def calendar_endpoint(
    context: Annotated[ApplicationContext, Depends(get_context)],
    view: str = "today",
    pair: str | None = None,
):
    service = create_calendar_service(context)
    pairs = [pair] if pair else context.settings.trading.pairs
    return service.get_events(view, pairs).model_dump(mode="json")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
