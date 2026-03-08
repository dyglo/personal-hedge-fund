from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from hedge_fund.chat.agent_runtime import AgentArtifacts, AgentEventSink, AgentRuntime
from hedge_fund.chat.agent_tools import AgentToolContext
from hedge_fund.chat.ai import ChatLanguageService
from hedge_fund.chat.config_manager import ConfigManager
from hedge_fund.chat.models import ChatContextSnapshot, ChatResponse, ChatSessionState, ChatTurn, ReverseRiskCalculation, RouteDecision
from hedge_fund.chat.scratchpad import ScratchpadManager
from hedge_fund.chat.session_store import SessionStore
from hedge_fund.chat.utils import current_session_status, pip_value_per_standard_lot
from hedge_fund.config.settings import Settings
from hedge_fund.services.scan_service import RiskService, ScanService


class ReverseRiskService:
    def __init__(self, market_data, broker) -> None:
        self.market_data = market_data
        self.broker = broker

    def calculate(self, pair: str, lot_size: float, sl_pips: int) -> ReverseRiskCalculation:
        balance = self.broker.get_account_balance()
        price = self.market_data.get_price(pair)
        metadata = {} if pair == "XAUUSD" else self.broker.get_instrument_metadata(pair)
        pip_value, pip_size = pip_value_per_standard_lot(pair, price, metadata)
        risk_amount = lot_size * sl_pips * pip_value
        risk_pct = (risk_amount / balance) * 100 if balance else 0.0
        return ReverseRiskCalculation(
            pair=pair,
            account_balance=round(balance, 2),
            lot_size=lot_size,
            sl_pips=sl_pips,
            risk_amount=round(risk_amount, 2),
            risk_pct=round(risk_pct, 2),
            current_price=round(price, 5),
            pip_value_per_standard_lot=round(pip_value, 5),
            stop_distance=round(sl_pips * pip_size, 5),
        )


class ChatService:
    def __init__(
        self,
        settings: Settings,
        scan_service: ScanService,
        risk_service: RiskService,
        reverse_risk_service: ReverseRiskService,
        language: ChatLanguageService,
        config_manager: ConfigManager,
        session_store: SessionStore,
        agent_runtime: AgentRuntime | None = None,
        scratchpad_manager: ScratchpadManager | None = None,
        search_client=None,
    ) -> None:
        self.settings = settings
        self.scan_service = scan_service
        self.risk_service = risk_service
        self.reverse_risk_service = reverse_risk_service
        self.language = language
        self.config_manager = config_manager
        self.session_store = session_store
        self.agent_runtime = agent_runtime
        self.scratchpad_manager = scratchpad_manager
        self.search_client = search_client

    def process_message(
        self,
        state: ChatSessionState,
        message: str,
        authorize_mutation: Callable[[str], bool] | None = None,
        event_sink: AgentEventSink | None = None,
    ) -> ChatResponse:
        content = message.strip()
        if not content:
            return ChatResponse(session_id=state.session.session_id, message="Enter a request or use /help.")

        if content.startswith("/"):
            response = self._handle_slash_command(state, content, authorize_mutation)
            return self._record(state, content, response)

        if self.agent_runtime and self.scratchpad_manager:
            response = self._handle_agent_message(state, content, authorize_mutation, event_sink)
            return self._record(state, content, response)

        route = self.language.route(content, self._routing_context(state))
        if route.intent == "unknown":
            response = ChatResponse(
                session_id=state.session.session_id,
                route=route,
                message="I couldn’t pin that down. Ask for bias, setups, risk, sessions, or config changes.",
            )
            return self._record(state, content, response)

        if route.missing_fields:
            response = ChatResponse(
                session_id=state.session.session_id,
                route=route,
                message=self._missing_fields_message(route),
            )
            return self._record(state, content, response)

        if route.intent == "bias":
            response = self._handle_bias(state, route)
        elif route.intent == "scan":
            response = self._handle_scan(state, route)
        elif route.intent == "risk_size":
            response = self._handle_risk_size(state, route)
        elif route.intent == "risk_exposure":
            response = self._handle_risk_exposure(state, route)
        elif route.intent == "config_show_pairs":
            response = ChatResponse(
                session_id=state.session.session_id,
                route=route,
                message="Watching: " + ", ".join(self.config_manager.show_pairs()),
                metadata={"pairs": self.config_manager.show_pairs()},
            )
        elif route.intent == "config_show_risk":
            risk = self.config_manager.show_risk()
            response = ChatResponse(
                session_id=state.session.session_id,
                route=route,
                message=(
                    f"Default risk is {risk['default_risk_pct']}%, minimum RR is {risk['minimum_rr']}, "
                    f"preferred RR is {risk['preferred_rr']}."
                ),
                metadata=risk,
            )
        elif route.intent in {"config_add_pair", "config_remove_pair"}:
            response = self._handle_config_mutation(state, route, authorize_mutation)
        elif route.intent == "session_status":
            session_state = current_session_status(self.settings.trading.sessions)
            response = ChatResponse(
                session_id=state.session.session_id,
                route=route,
                message=session_state["status"],
                metadata=session_state,
            )
        else:
            answer = self.language.answer_general(content, self._answer_context(state, route))
            response = ChatResponse(
                session_id=state.session.session_id,
                route=route,
                message=answer,
            )
        return self._record(state, content, response)

    def _handle_agent_message(
        self,
        state: ChatSessionState,
        content: str,
        authorize_mutation: Callable[[str], bool] | None,
        event_sink: AgentEventSink | None,
    ) -> ChatResponse:
        scratchpad = self.scratchpad_manager.for_session(state.session.session_id)
        artifacts = AgentArtifacts()
        tool_context = AgentToolContext(
            settings=self.settings,
            state=state,
            scan_service=self.scan_service,
            risk_service=self.risk_service,
            reverse_risk_service=self.reverse_risk_service,
            config_manager=self.config_manager,
            search_client=self.search_client,
            scratchpad=scratchpad,
            artifacts=artifacts,
            authorize_mutation=authorize_mutation,
        )
        result = self.agent_runtime.run(
            user_message=content,
            system_prompt=self._agent_system_prompt(state),
            tools=tool_context.build_tools(),
            scratchpad=scratchpad,
            artifacts=artifacts,
            event_sink=event_sink,
        )
        self._refresh_settings(self.config_manager.current_settings())
        return ChatResponse(
            session_id=state.session.session_id,
            message=result.message,
            biases=artifacts.biases,
            setups=artifacts.setups,
            ai_analysis=artifacts.ai_analysis,
            risk=artifacts.risk,
            reverse_risk=artifacts.reverse_risk,
            metadata={**artifacts.metadata, **result.metadata},
        )

    def _handle_bias(self, state: ChatSessionState, route: RouteDecision) -> ChatResponse:
        pairs = self._resolve_pairs(state, route)
        biases = self.scan_service.bias_only(pairs)
        state.session.context.active_pair = pairs[0] if len(pairs) == 1 else state.session.context.active_pair
        state.session.context.last_pairs = pairs
        state.session.context.last_bias_pairs = pairs
        state.session.context.last_intent = route.intent
        return ChatResponse(
            session_id=state.session.session_id,
            route=route,
            biases=biases,
            metadata={"pairs": pairs},
        )

    def _handle_scan(self, state: ChatSessionState, route: RouteDecision) -> ChatResponse:
        pairs = self._resolve_pairs(state, route)
        bundle = self.scan_service.scan(pairs)
        threshold = route.score_threshold
        if threshold is None and route.question and "high probability" in route.question.lower():
            threshold = max(self.settings.trading.scanner.minimum_score, 7)
        if threshold is not None:
            matching_pairs = {setup.pair for setup in bundle.setups if setup.score >= threshold}
            biases = [item for item in bundle.biases if item.pair in matching_pairs]
            setups = [item for item in bundle.setups if item.pair in matching_pairs]
            ai_analysis = [item for item in bundle.ai_analysis if any(pair in item.narrative for pair in matching_pairs)] or bundle.ai_analysis
        else:
            biases = bundle.biases
            setups = bundle.setups
            ai_analysis = bundle.ai_analysis

        if len(pairs) == 1:
            state.session.context.active_pair = pairs[0]
            state.session.context.last_scan_pair = pairs[0]
        state.session.context.last_pairs = pairs
        state.session.context.last_setup_pairs = [item.pair for item in setups]
        state.session.context.last_intent = route.intent
        return ChatResponse(
            session_id=state.session.session_id,
            route=route,
            biases=biases,
            setups=setups,
            ai_analysis=ai_analysis,
            metadata={"pairs": pairs, "score_threshold": threshold},
        )

    def _handle_risk_size(self, state: ChatSessionState, route: RouteDecision) -> ChatResponse:
        calculation = self.risk_service.calculate(route.pair or "", route.risk_pct or 0, route.sl_pips or 0)
        state.session.context.active_pair = calculation.pair
        state.session.context.last_intent = route.intent
        return ChatResponse(
            session_id=state.session.session_id,
            route=route,
            risk=calculation,
        )

    def _handle_risk_exposure(self, state: ChatSessionState, route: RouteDecision) -> ChatResponse:
        calculation = self.reverse_risk_service.calculate(route.pair or "", route.lot_size or 0, route.sl_pips or 0)
        state.session.context.active_pair = calculation.pair
        state.session.context.last_intent = route.intent
        return ChatResponse(
            session_id=state.session.session_id,
            route=route,
            reverse_risk=calculation,
        )

    def _handle_config_mutation(
        self,
        state: ChatSessionState,
        route: RouteDecision,
        authorize_mutation: Callable[[str], bool] | None,
    ) -> ChatResponse:
        permission_mode = state.session.permission_mode
        pair = route.pair or ""
        if permission_mode == "plan":
            return ChatResponse(
                session_id=state.session.session_id,
                route=route,
                message="Permission mode is plan, so config changes are blocked for this session.",
            )
        if permission_mode == "default":
            if authorize_mutation is None or not authorize_mutation(f"Update config.yaml for {pair}?"):
                return ChatResponse(
                    session_id=state.session.session_id,
                    route=route,
                    message="Config change cancelled.",
                )

        settings = self.config_manager.add_pair(pair) if route.intent == "config_add_pair" else self.config_manager.remove_pair(pair)
        self._refresh_settings(settings)
        action = "Added" if route.intent == "config_add_pair" else "Removed"
        state.session.context.last_intent = route.intent
        return ChatResponse(
            session_id=state.session.session_id,
            route=route,
            message=f"{action} {pair} in config.yaml.",
            metadata={"pairs": settings.trading.pairs},
        )

    def _handle_slash_command(
        self,
        state: ChatSessionState,
        command: str,
        authorize_mutation: Callable[[str], bool] | None,
    ) -> ChatResponse:
        cmd = command.split()[0].lower()
        if cmd == "/help":
            return ChatResponse(
                session_id=state.session.session_id,
                message="Commands: /help, /clear, /status, /model, /config, /pairs, /risk, /session, /permissions, /exit, /quit",
            )
        if cmd == "/clear":
            state.session.context = ChatContextSnapshot()
            return ChatResponse(session_id=state.session.session_id, message="Cleared active conversation context.")
        if cmd == "/status":
            return ChatResponse(
                session_id=state.session.session_id,
                message=f"Session {state.session.session_id} with {len(state.session.turns)} stored turns.",
                metadata={
                    "session_id": state.session.session_id,
                    "turn_count": len(state.session.turns),
                    "active_pair": state.session.context.active_pair,
                },
            )
        if cmd == "/model":
            model = state.session.model_override or f"{self.settings.ai.provider}:{self.settings.ai.models.model_dump()}"
            return ChatResponse(session_id=state.session.session_id, message=f"Model: {model}")
        if cmd == "/config":
            pairs = ", ".join(self.config_manager.show_pairs())
            risk = self.config_manager.show_risk()
            return ChatResponse(
                session_id=state.session.session_id,
                message=(
                    f"Pairs: {pairs}. Default risk {risk['default_risk_pct']}%, "
                    f"minimum RR {risk['minimum_rr']}, preferred RR {risk['preferred_rr']}."
                ),
            )
        if cmd == "/pairs":
            return ChatResponse(session_id=state.session.session_id, message="Watching: " + ", ".join(self.config_manager.show_pairs()))
        if cmd == "/risk":
            risk = self.config_manager.show_risk()
            return ChatResponse(
                session_id=state.session.session_id,
                message=(
                    f"Default risk {risk['default_risk_pct']}%, minimum RR {risk['minimum_rr']}, "
                    f"preferred RR {risk['preferred_rr']}."
                ),
            )
        if cmd == "/session":
            session_state = current_session_status(self.settings.trading.sessions)
            return ChatResponse(session_id=state.session.session_id, message=session_state["status"], metadata=session_state)
        if cmd == "/permissions":
            return ChatResponse(
                session_id=state.session.session_id,
                message=f"Permission mode: {state.session.permission_mode}",
                metadata={"permission_mode": state.session.permission_mode},
            )
        if cmd in {"/exit", "/quit"}:
            return ChatResponse(session_id=state.session.session_id, message="Closing chat session.", should_exit=True)
        return ChatResponse(session_id=state.session.session_id, message=f"Unknown command: {cmd}")

    def _routing_context(self, state: ChatSessionState) -> dict:
        recent_turns = state.session.turns[-state.max_context_turns :]
        return {
            "active_pair": state.session.context.active_pair,
            "last_intent": state.session.context.last_intent,
            "recent_turns": [
                {"role": turn.role, "content": turn.content, "metadata": turn.metadata}
                for turn in recent_turns
            ],
            "configured_pairs": self.settings.trading.pairs,
            "default_risk_pct": self.settings.trading.risk.default_risk_pct,
        }

    def _answer_context(self, state: ChatSessionState, route: RouteDecision) -> dict:
        context = self._routing_context(state)
        context["question"] = route.question
        context["pair"] = route.pair
        return context

    def _agent_system_prompt(self, state: ChatSessionState) -> str:
        session_state = current_session_status(self.settings.trading.sessions)
        context = state.session.context
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
        prompt = (
            "You are Prophet, a concise forex trading CLI assistant. "
            "Use tools when the answer depends on live market structure, watchlist settings, session timing, risk, or live news. "
            "Use web_search for news, macro, policy, fundamentals, or event-driven questions. "
            "Use internal tools instead of web search for bias, setup, session, or risk calculations. "
            "If a tool reports an error or blocked mutation, explain it briefly and continue with the best partial answer. "
            "Keep final answers short, practical, and trader-focused.\n"
            f"Current time: {today}\n"
            f"Configured pairs: {', '.join(self.settings.trading.pairs)}\n"
            f"Active pair: {context.active_pair or 'None'}\n"
            f"Last intent: {context.last_intent or 'None'}\n"
            f"Session status: {session_state['status']}\n"
        )
        if state.session.append_system_prompt:
            prompt += state.session.append_system_prompt.strip()
        return prompt.strip()

    def _record(self, state: ChatSessionState, user_message: str, response: ChatResponse) -> ChatResponse:
        if user_message:
            self.session_store.add_turn(
                state,
                ChatTurn(role="user", content=user_message, route=response.route),
            )
        assistant_text = response.message or ""
        self.session_store.add_turn(
            state,
            ChatTurn(role="assistant", content=assistant_text, route=response.route, metadata=response.metadata),
        )
        return response

    def _resolve_pairs(self, state: ChatSessionState, route: RouteDecision) -> list[str]:
        if route.scope == "all":
            return self.settings.trading.pairs
        if route.pair:
            return [route.pair]
        if state.session.context.active_pair:
            return [state.session.context.active_pair]
        return self.settings.trading.pairs

    def _refresh_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.scan_service.settings = settings
        self.language.settings = settings
        if self.agent_runtime:
            self.agent_runtime.settings = settings

    def _missing_fields_message(self, route: RouteDecision) -> str:
        labels = {
            "pair": "a pair like XAUUSD or EURUSD",
            "sl_pips": "a stop-loss in pips",
            "lot_size": "a lot size",
        }
        wanted = [labels.get(item, item) for item in route.missing_fields]
        return "I need " + " and ".join(wanted) + " to do that."
