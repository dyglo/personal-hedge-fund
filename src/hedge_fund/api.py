from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Annotated

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from hedge_fund.chat.command import ChatCommandRunner
from hedge_fund.chat.models import ChatResponse
from hedge_fund.chat.session_store import DatabaseSessionStore
from hedge_fund.cli.bootstrap import ApplicationContext
from hedge_fund.services.scan_service import RiskService, ScanService

app = FastAPI(title="Prophet API")


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str | None = None


class ScanRequest(BaseModel):
    pair: str | None = None


class RiskRequest(BaseModel):
    pair: str
    risk: float
    sl: int


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
    return DatabaseSessionStore(context.session_factory)


def create_scan_service(context: ApplicationContext, session: Session) -> ScanService:
    return ScanService(
        context.settings,
        context.market_data,
        context.ai,
        context.create_repository(session),
        context.logger,
    )


@app.get("/")
def read_root():
    return {"status": "ok", "app": "Prophet API"}


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    context: Annotated[ApplicationContext, Depends(get_context)],
    session: Annotated[Session, Depends(get_db_session)],
    session_store: Annotated[DatabaseSessionStore, Depends(get_chat_session_store)],
):
    runner = ChatCommandRunner(
        context,
        cwd=Path(os.getcwd()),
        session_store=session_store,
        repository=context.create_repository(session),
    )
    try:
        if request.session_id:
            try:
                state = runner.session_store.load(request.session_id)
            except FileNotFoundError:
                state = runner.session_store.create(
                    max_context_turns=context.settings.chat.max_context_turns,
                    permission_mode="default",
                    model_override=request.model,
                    append_system_prompt=None,
                )
        else:
            state = runner.session_store.create(
                max_context_turns=context.settings.chat.max_context_turns,
                permission_mode="default",
                model_override=request.model,
                append_system_prompt=None,
            )

        service = runner.build_service(state.session.model_override, state.session.append_system_prompt)
        return service.process_message(state, request.message)
    finally:
        runner.close()


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
