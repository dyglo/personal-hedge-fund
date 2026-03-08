from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from hedge_fund.chat.command import ChatCommandRunner
from hedge_fund.chat.models import ChatResponse
from hedge_fund.cli.bootstrap import ApplicationContext

app = FastAPI(title="Prophet API")

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str | None = None

class ChatApiResponse(BaseModel):
    message: str
    session_id: str
    metadata: dict[str, Any] | None = None

# Global context to avoid re-initializing everything on every request
_context: ApplicationContext | None = None

def get_context() -> ApplicationContext:
    global _context
    if _context is None:
        _context = ApplicationContext()
    return _context

@app.get("/")
def read_root():
    return {"status": "ok", "app": "Prophet API"}

@app.post("/chat", response_model=ChatApiResponse)
def chat(request: ChatRequest):
    context = get_context()
    cwd = Path(os.getcwd())
    runner = ChatCommandRunner(context, cwd=cwd)
    
    # We want to use the session store
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
    
    service = runner._build_service(state.session.model_override, state.session.append_system_prompt)
    
    # Process the message
    # We don't have interactive confirmation in API mode
    response: ChatResponse = service.process_message(state, request.message)
    
    return ChatApiResponse(
        message=response.message or "",
        session_id=state.session.session_id,
        metadata=response.metadata
    )

class ScanRequest(BaseModel):
    pair: str | None = None

class RiskRequest(BaseModel):
    pair: str
    risk: float
    sl: int

from hedge_fund.services.scan_service import RiskService, ScanService

@app.post("/scan")
def scan_endpoint(request: ScanRequest):
    context = get_context()
    service = ScanService(
        context.settings,
        context.market_data,
        context.ai,
        context.repository,
        context.logger,
    )
    pairs = [request.pair] if request.pair else context.settings.trading.pairs
    return service.scan(pairs)

@app.post("/bias")
def bias_endpoint(request: ScanRequest):
    context = get_context()
    service = ScanService(
        context.settings,
        context.market_data,
        context.ai,
        context.repository,
        context.logger,
    )
    pairs = [request.pair] if request.pair else context.settings.trading.pairs
    return service.bias_only(pairs)

@app.post("/risk")
def risk_endpoint(request: RiskRequest):
    context = get_context()
    service = RiskService(context.market_data, context.broker)
    return service.calculate(request.pair, request.risk, request.sl)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
