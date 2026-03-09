from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Protocol

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage

from hedge_fund.chat.agent_models import AgentModelFactory
from hedge_fund.chat.scratchpad import ScratchpadLogger
from hedge_fund.config.environment import EnvironmentSettings
from hedge_fund.config.settings import Settings
from hedge_fund.domain.exceptions import ProviderError
from hedge_fund.domain.models import AiAnalysisResult, BiasResult, RiskCalculation, SetupScanResult

try:
    from langgraph.errors import GraphRecursionError
except Exception:  # noqa: BLE001
    class GraphRecursionError(Exception):
        """Fallback recursion error when langgraph is unavailable."""


class AgentEventSink(Protocol):
    def update_status(self, message: str) -> None: ...

    def emit_thinking(self, message: str) -> None: ...


@dataclass
class AgentArtifacts:
    biases: list[BiasResult] = field(default_factory=list)
    setups: list[SetupScanResult] = field(default_factory=list)
    ai_analysis: list[AiAnalysisResult] = field(default_factory=list)
    risk: RiskCalculation | None = None
    reverse_risk: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    summaries: list[str] = field(default_factory=list)


@dataclass
class AgentRunResult:
    message: str
    artifacts: AgentArtifacts
    metadata: dict[str, Any]


class AgentRuntime:
    def __init__(
        self,
        settings: Settings,
        env: EnvironmentSettings,
        logger: logging.Logger,
        model_override: str | None = None,
    ) -> None:
        self.settings = settings
        self.env = env
        self.logger = logger
        self.model_override = model_override

    def run(
        self,
        user_message: str,
        system_prompt: str,
        tools: list[Any],
        scratchpad: ScratchpadLogger,
        artifacts: AgentArtifacts,
        event_sink: AgentEventSink | None = None,
        history_messages: list[dict[str, Any]] | None = None,
        stream_handler: Callable[[str], None] | None = None,
    ) -> AgentRunResult:
        failures: list[str] = []
        try:
            candidates = AgentModelFactory(self.settings, self.env, self.model_override).candidates()
        except ProviderError as exc:
            failures.append(str(exc))
            candidates = []

        for candidate in candidates:
            scratchpad.log(
                "thinking",
                {
                    "event": "provider_start",
                    "provider": candidate.provider,
                    "model": candidate.model_name,
                },
            )
            try:
                return self._run_with_candidate(
                    user_message=user_message,
                    system_prompt=system_prompt,
                    tools=tools,
                    scratchpad=scratchpad,
                    artifacts=artifacts,
                    candidate=candidate,
                    event_sink=event_sink,
                    history_messages=history_messages,
                    stream_handler=stream_handler,
                )
            except GraphRecursionError:
                self.logger.warning("Agent recursion limit reached for session")
                partial = self._partial_message(artifacts, "I hit the configured reasoning-step limit, so this is a partial result.")
                scratchpad.log(
                    "final_response",
                    {
                        "provider": candidate.provider,
                        "model": candidate.model_name,
                        "partial": True,
                        "message": partial,
                    },
                )
                return AgentRunResult(
                    message=partial,
                    artifacts=artifacts,
                    metadata={"provider": candidate.provider, "model": candidate.model_name, "partial": True},
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{candidate.provider}: {exc}")
                scratchpad.log(
                    "thinking",
                    {
                        "event": "provider_failure",
                        "provider": candidate.provider,
                        "model": candidate.model_name,
                        "error": str(exc),
                    },
                )
                self.logger.warning("Agent provider %s failed: %s", candidate.provider, exc)

        fallback = self._partial_message(artifacts, "The agent fell back after provider failures.")
        scratchpad.log("final_response", {"partial": True, "message": fallback, "failures": failures})
        return AgentRunResult(
            message=fallback,
            artifacts=artifacts,
            metadata={"provider_failures": failures, "partial": True},
        )

    def _run_with_candidate(
        self,
        user_message: str,
        system_prompt: str,
        tools: list[Any],
        scratchpad: ScratchpadLogger,
        artifacts: AgentArtifacts,
        candidate,
        event_sink: AgentEventSink | None,
        history_messages: list[dict[str, Any]] | None,
        stream_handler: Callable[[str], None] | None,
    ) -> AgentRunResult:
        agent = create_agent(
            candidate.model,
            tools=tools,
            system_prompt=system_prompt,
        )
        final_message = ""
        streamed_parts: list[str] = []
        if event_sink:
            event_sink.update_status("Thinking...")

        stream = agent.stream(
            {"messages": history_messages or [{"role": "user", "content": user_message}]},
            config={"recursion_limit": max(10, self.settings.agent.max_steps * 4)},
            stream_mode=["messages", "updates"],
        )
        for stream_mode, payload in stream:
            if stream_mode == "messages":
                text = self._stream_text(payload)
                if text:
                    streamed_parts.append(text)
                    if stream_handler:
                        stream_handler(text)
                continue
            if stream_mode != "updates":
                continue
            for update in payload.values():
                message = self._latest_message(update)
                if message is None:
                    continue
                self._handle_message(message, scratchpad, candidate.provider, candidate.model_name, event_sink)
                if isinstance(message, AIMessage) and not message.tool_calls:
                    final_message = self._coerce_text(message)

        if not final_message:
            if streamed_parts:
                final_message = "".join(streamed_parts).strip()
        if not final_message:
            final_message = self._partial_message(artifacts, "I could not complete a final answer, so here is the latest partial result.")

        scratchpad.log(
            "final_response",
            {
                "provider": candidate.provider,
                "model": candidate.model_name,
                "message": final_message,
            },
        )
        return AgentRunResult(
            message=final_message,
            artifacts=artifacts,
            metadata={"provider": candidate.provider, "model": candidate.model_name},
        )

    def _handle_message(
        self,
        message: BaseMessage,
        scratchpad: ScratchpadLogger,
        provider: str,
        model_name: str,
        event_sink: AgentEventSink | None,
    ) -> None:
        if isinstance(message, AIMessage) and message.tool_calls:
            for tool_call in message.tool_calls:
                name = tool_call.get("name", "unknown")
                scratchpad.log(
                    "thinking",
                    {
                        "event": "tool_selected",
                        "provider": provider,
                        "model": model_name,
                        "tool": name,
                        "arguments": tool_call.get("args", {}),
                    },
                )
                if event_sink:
                    event_sink.update_status(self._status_for_tool(name))
                    event_sink.emit_thinking(f"Tool selected: {name}")
            return

        if isinstance(message, ToolMessage):
            scratchpad.log(
                "thinking",
                {
                    "event": "tool_message",
                    "provider": provider,
                    "model": model_name,
                    "content": self._coerce_text(message),
                },
            )
            return

        if isinstance(message, AIMessage):
            text = self._coerce_text(message)
            if text:
                scratchpad.log(
                    "thinking",
                    {
                        "event": "finalizing",
                        "provider": provider,
                        "model": model_name,
                        "content": text,
                    },
                )
                if event_sink:
                    event_sink.update_status("Propheting...")
                    event_sink.emit_thinking("Drafting final response.")

    def _coerce_text(self, message: BaseMessage) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content.strip()
        parts: list[str] = []
        if isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
        return "\n".join(part for part in parts if part).strip()

    def _latest_message(self, update: Any) -> BaseMessage | None:
        if not isinstance(update, dict):
            return None
        messages = update.get("messages")
        if not isinstance(messages, list) or not messages:
            return None
        message = messages[-1]
        return message if isinstance(message, BaseMessage) else None

    def _stream_text(self, payload: Any) -> str:
        if not isinstance(payload, tuple) or not payload:
            return ""
        message = payload[0]
        if not isinstance(message, BaseMessage):
            return ""
        if getattr(message, "tool_calls", None):
            return ""
        if isinstance(message, ToolMessage):
            return ""
        if not isinstance(message, (AIMessage, AIMessageChunk)):
            return ""
        text = self._coerce_text(message)
        if not text:
            return ""
        stripped = text.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            return ""
        if any(token in stripped for token in ('"tool"', '"tool_call"', '"arguments"', '"result"', '"ok"')):
            return ""
        if not any(character.isalpha() for character in stripped):
            return ""
        return text

    def _partial_message(self, artifacts: AgentArtifacts, note: str) -> str:
        lines = list(artifacts.summaries[-3:])
        if not lines:
            lines.append("No completed tool results were available.")
        lines.append(note)
        return "\n".join(lines)

    def _status_for_tool(self, tool_name: str) -> str:
        mapping = {
            "get_market_bias": "Reading market structure...",
            "scan_setups": "Scanning for confluence...",
            "calculate_risk": "Calculating position size...",
            "calculate_risk_exposure": "Calculating position size...",
            "get_session_status": "Checking session...",
            "get_economic_calendar": "Checking the calendar...",
            "rank_watchlist_pairs": "Ranking watchlist setups...",
            "show_memory": "Loading trader memory...",
            "remember_rule": "Updating trader memory...",
            "forget_rule": "Updating trader memory...",
            "web_search": "Searching the web...",
        }
        return mapping.get(tool_name, "Analysing...")
